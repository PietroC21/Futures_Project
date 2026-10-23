import numpy as np
import pandas as pd
import pytest

from stale_quotes import metrics
from stale_quotes.metrics import (
    annotate,
    build_tables,
    duration_summary,
    edge_summary,
    kaplan_meier,
    km_quantiles,
    latency_summary,
    opportunity_summary,
    reaction_latency,
    save_figures,
)

BASE = pd.Timestamp("2026-10-07 14:00", tz="UTC")  # 10:00 ET
CALL, PUT = 1, 2
OPTIONS = pd.DataFrame({
    "instrument_id": [CALL, PUT],
    "strike_price": [7000.0, 7000.0],
    "instrument_class": ["C", "P"],
    "expiration": [pd.Timestamp("2026-10-07 20:00", tz="UTC")] * 2,
    "unit_of_measure_qty": [50.0, 50.0],
})


def at(ns):
    return BASE + pd.Timedelta(ns, "ns")


def bbo(*rows):
    """rows: (ns, instrument_id, bid, ask)."""
    return pd.DataFrame([{"ts_event": at(ns), "instrument_id": i, "bid": b, "ask": a} for ns, i, b, a in rows])


def events(*rows):
    """rows: (t0_ns, F0, F1[, observation_end_ns])."""
    data = {
        "event_id": range(len(rows)),
        "t0": [at(r[0]) for r in rows],
        "price_before": [r[1] for r in rows],
        "price_after": [r[2] for r in rows],
    }
    if all(len(r) > 3 for r in rows):
        data["observation_end"] = [at(r[3]) for r in rows]
    return pd.DataFrame(data)


def latency(ev, book, options=OPTIONS.iloc[[0]], **kw):
    return reaction_latency(ev, book, options, **kw)


# --- helpers -----------------------------------------------------------------


def test_next_true():
    out = metrics._next_true(np.array([False, True, False, False, True, False]))
    assert out.tolist() == [1, 1, 4, 4, 4, 6]


def test_next_beyond_skips_nans():
    x = np.array([1.0, np.nan, 0.5, 2.0, 1.5])
    assert metrics._next_beyond(x, True).tolist() == [3, 5, 3, 5, 5]
    assert metrics._next_beyond(x, False).tolist() == [2, 5, 5, 4, 5]


# --- reaction latency --------------------------------------------------------


def test_latency_ignores_size_only_updates():
    book = bbo((0, CALL, 10.0, 10.2), (150, CALL, 10.0, 10.2), (180, CALL, 10.1, 10.3))
    r = latency(events((100, 7000.0, 7000.25, 10_000)), book).iloc[0]
    assert r.latency_status == "ok"
    assert r.latency_ns == 80 and not r.latency_censored
    assert r.directional_latency_ns == 80 and not r.directional_censored


def test_directional_latency_waits_for_the_right_sign():
    book = bbo(
        (0, CALL, 10.0, 10.2),
        (130, CALL, 9.95, 10.2),   # call mid falls after an up move: wrong way
        (170, CALL, 10.05, 10.25),  # mid above the pre-move mid: reaction
    )
    r = latency(events((100, 7000.0, 7000.25, 10_000)), book).iloc[0]
    assert r.latency_ns == 30
    assert r.directional_latency_ns == 70


def test_put_reacts_against_the_future():
    book = bbo((0, PUT, 10.0, 10.2), (120, PUT, 9.9, 10.1))
    r = latency(events((100, 7000.0, 7000.25, 10_000)), book, OPTIONS.iloc[[1]]).iloc[0]
    assert r.directional_latency_ns == 20 and not r.directional_censored


def test_update_at_t0_has_zero_latency():
    book = bbo((0, CALL, 10.0, 10.2), (100, CALL, 10.1, 10.3))
    r = latency(events((100, 7000.0, 7000.25, 10_000)), book).iloc[0]
    assert r.latency_ns == 0 and not r.latency_censored


def test_latency_censored_at_observation_end():
    book = bbo((0, CALL, 10.0, 10.2), (600, CALL, 10.1, 10.3))
    r = latency(events((100, 7000.0, 7000.25, 400)), book).iloc[0]
    assert r.latency_censored and r.latency_ns == 300


def test_latency_censored_without_observation_end_uses_max_window():
    book = bbo((0, CALL, 10.0, 10.2))
    r = latency(events((100, 7000.0, 7000.25)), book, max_window_ns=1_000).iloc[0]
    assert r.latency_censored and r.latency_ns == 1_000


def test_latency_statuses():
    book = bbo((50, CALL, 10.2, 10.0))  # crossed
    ev = events((10, 7000.0, 7000.25, 1000), (100, 7000.0, 7000.25, 1000), (200, 7000.0, 7000.0, 1000))
    r = latency(ev, book)
    assert r["latency_status"].tolist() == ["no_quote", "invalid_quote", "invalid_quote"]
    assert r["latency_ns"].isna().all()
    book = bbo((0, CALL, 10.0, 10.2))
    assert latency(events((200, 7000.0, 7000.0, 1000)), book).iloc[0].latency_status == "no_move"
    late = events((0, 7000.0, 7000.25))
    late["t0"] = pd.Timestamp("2026-10-07 20:00:01", tz="UTC")
    assert latency(late, bbo((-1, CALL, 10.0, 10.2))).iloc[0].latency_status == "expired"


def test_option_without_quotes_is_no_quote():
    r = latency(events((100, 7000.0, 7000.25, 1000)), bbo((0, PUT, 10.0, 10.2)))
    assert r.iloc[0].latency_status == "no_quote"


def test_unselected_events_dropped():
    ev = events((100, 7000.0, 7000.25, 1000), (200, 7000.0, 7000.25, 1000))
    ev["selected"] = [True, False]
    assert len(latency(ev, bbo((0, CALL, 10.0, 10.2)))) == 1


# --- buckets -----------------------------------------------------------------


def test_annotate_buckets():
    t = pd.DataFrame({
        "t0": [at(0), pd.Timestamp("2026-10-07 13:45", tz="UTC"), pd.Timestamp("2026-10-07 19:45", tz="UTC")],
        "price_before": [7001.0, 7001.0, 7001.0],
        "price_after": [7001.25, 7000.0, 7003.0],
        "strike_price": [7000.0, 7010.0, 7010.0],
        "instrument_class": ["C", "C", "P"],
    })
    a = annotate(t)
    assert a["move_bucket"].astype(str).tolist() == ["1", "2.5-4", ">4"]
    assert a["otm_points"].tolist() == [-1.0, 9.0, -9.0]
    assert a["moneyness"].astype(str).tolist() == ["ATM", "OTM 7.5-17.5", "ITM >7.5"]
    assert a["session"].astype(str).tolist() == ["morning", "open", "close"]


# --- survival ----------------------------------------------------------------


def test_kaplan_meier_with_censoring():
    km = kaplan_meier([1, 2, 2, 3, 4], [False, True, False, False, True])
    assert km["time"].tolist() == [1, 2, 3]
    assert km["at_risk"].tolist() == [5, 4, 2]
    assert km["survival"].tolist() == pytest.approx([0.8, 0.6, 0.3])


def test_km_quantiles_match_empirical_without_censoring():
    d = np.arange(1, 11)
    q = km_quantiles(d, np.zeros(10, bool), qs=(0.1, 0.5, 0.9))
    assert q == {"p10": 1.0, "p50": 5.0, "p90": 9.0}


def test_km_quantile_nan_when_censoring_cuts_curve():
    q = km_quantiles([1, 5, 5, 5], [False, True, True, True], qs=(0.25, 0.5))
    assert q["p25"] == 1.0 and np.isnan(q["p50"])


# --- summaries ---------------------------------------------------------------


def stale_table():
    """Two events x two options, in the shape staleness.detect_stale_quotes returns."""
    rows = [
        # event, option, class, F0, F1, status, side, edge, size, duration, censored
        (0, CALL, "C", 7000.0, 7000.25, "stale", "ask", 0.02, 3, 400, False),
        (0, PUT, "P", 7000.0, 7000.25, "not_stale", None, None, None, None, False),
        (1, CALL, "C", 7000.0, 7001.5, "stale", "ask", 0.10, 5, 900, True),
        (1, PUT, "P", 7000.0, 7001.5, "stale", "bid", 0.06, 2, 600, False),
        (2, CALL, "C", 7000.0, 7000.25, "no_quote", None, None, None, None, False),
    ]
    df = pd.DataFrame(rows, columns=["event_id", "instrument_id", "instrument_class", "price_before",
                                     "price_after", "status", "side", "edge", "quote_size",
                                     "duration_ns", "censored"])
    df["strike_price"] = 7000.0
    df["t0"] = at(0)
    df["edge_usd"] = df["edge"] * 50
    df["duration_ns"] = df["duration_ns"].astype("Int64")
    return df


def test_opportunity_counts_events_once():
    s = annotate(stale_table())
    o = opportunity_summary(s).loc["all"]
    assert o.events == 2 and o.stale_events == 2 and o.event_rate == 1.0
    assert o.pairs == 4 and o.stale_pairs == 3
    by = opportunity_summary(s, "instrument_class")
    assert by.loc["P", "event_rate"] == 0.5


def test_edge_summary_capacity():
    e = edge_summary(stale_table()).loc["all"]
    assert e.stale_pairs == 3
    assert e.median_edge_pts == pytest.approx(0.06)
    assert e.total_capacity_usd == pytest.approx(50 * (0.02 * 3 + 0.10 * 5 + 0.06 * 2))


def test_duration_summary_uses_km():
    d = duration_summary(stale_table()).loc["all"]
    assert d.stale_pairs == 3 and d.censored_share == pytest.approx(1 / 3)
    assert d.p50_us == pytest.approx(0.6)  # 400 ns, 600 ns observed; 900 ns censored
    assert np.isnan(d.p90_us)


def test_latency_summary_quantiles_in_us():
    book = bbo((0, CALL, 10.0, 10.2), (1_100, CALL, 10.1, 10.3), (3_100, CALL, 10.2, 10.4))
    ev = events((100, 7000.0, 7000.25, 50_000), (2_100, 7000.0, 7000.25, 50_000))
    s = latency_summary(annotate(latency(ev, book))).loc["all"]
    assert s.pairs == 2 and s.censored_share == 0
    assert s.p50_us == pytest.approx(1.0)


def test_build_tables_and_figures(tmp_path):
    book = bbo((0, CALL, 10.0, 10.2), (0, PUT, 10.0, 10.2), (500, CALL, 10.1, 10.3), (700, PUT, 9.9, 10.1))
    lat = reaction_latency(events((100, 7000.0, 7000.25, 50_000), (200, 7000.0, 7001.5, 50_000)), book, OPTIONS)
    tables = build_tables(stale_table(), lat)
    assert {"latency_moneyness", "opportunity_move", "duration_session", "edge_overall"} <= tables.keys()
    paths = save_figures(annotate(stale_table()), lat, tables, tmp_path)
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)


# --- end to end with staleness (PR #16) ---------------------------------------


def test_end_to_end_with_staleness():
    staleness = pytest.importorskip("stale_quotes.staleness")
    quotes = pd.DataFrame([
        {"ts_event": at(ns), "instrument_id": CALL, "action": "A", "sequence": k,
         "bid_px_00": b, "ask_px_00": a, "bid_sz_00": 3, "ask_sz_00": 4}
        for k, (ns, b, a) in enumerate([(0, 9.9, 10.1), (300, 10.4, 10.6)])
    ])
    ev = events((100, 7000.0, 7001.0, 10_000))
    linear = lambda mid, F0, F1, K, T, c: (mid + 0.5 * (F1 - F0), None)
    stale = staleness.detect_stale_quotes(ev, quotes, OPTIONS.iloc[[0]], fair_value=linear)
    lat = reaction_latency(ev, staleness.option_bbo(quotes), OPTIONS.iloc[[0]])
    tables = build_tables(stale, lat)
    assert tables["opportunity_overall"].loc["all", "event_rate"] == 1.0
    assert tables["duration_overall"].loc["all", "p50_us"] == pytest.approx(0.2)
    assert tables["latency_overall"].loc["all", "p50_us"] == pytest.approx(0.2)


def test_status_summary_shares():
    s = metrics.status_summary(stale_table())
    assert s.loc["all", "pairs"] == 5
    assert s.loc["all", "stale"] == pytest.approx(0.6)
    by = metrics.status_summary(stale_table(), "instrument_class")
    assert by.loc["C", "no_quote"] == pytest.approx(1 / 3)


def test_events_keyed_by_date_when_pooled():
    a, b = stale_table(), stale_table()
    b.loc[b["event_id"] == 0, "status"] = "not_stale"  # same event_id, other day, nothing stale
    pooled = pd.concat([a.assign(trading_date="d1"), b.assign(trading_date="d2")], ignore_index=True)
    o = opportunity_summary(pooled).loc["all"]
    assert o.events == 4 and o.stale_events == 3


def test_load_processed_and_write_results(tmp_path):
    book = bbo((0, CALL, 10.0, 10.2), (0, PUT, 10.0, 10.2), (500, CALL, 10.1, 10.3))
    lat = reaction_latency(events((100, 7000.0, 7000.25, 50_000), (200, 7000.0, 7001.5, 50_000)), book, OPTIONS)
    for kind, table in [("stale", stale_table()), ("latency", lat)]:
        (tmp_path / kind).mkdir()
        table.to_parquet(tmp_path / kind / "20261007.parquet", index=False)
    stale, latency_ = metrics.load_processed(tmp_path)
    assert (stale["trading_date"] == pd.Timestamp("2026-10-07")).all() and len(latency_) == 4
    tables = metrics.write_results(stale, latency_, tmp_path / "results")
    assert (tmp_path / "results" / "tables" / "opportunity_move.csv").exists()
    assert len(list((tmp_path / "results" / "figures").glob("*.png"))) == 6
    assert tables["opportunity_overall"].loc["all", "events"] == 2
