import numpy as np
import pandas as pd
import pytest

from stale_quotes import config
from stale_quotes.staleness import CachedFairValue, cost_points, detect_stale_quotes, option_bbo

BASE = pd.Timestamp("2026-10-07 14:00", tz="UTC")
COST = 0.025 + 1.00 / 50  # half a 0.05 tick + $1 fee on a 50x contract
CALL, PUT = 1, 2


def at(ns):
    return BASE + pd.Timedelta(ns, "ns")


def linear_fair(mid, F0, F1, K, T, is_call):
    """Stand-in for black76.fair_value: delta of +0.5 (call) / -0.5 (put)."""
    return mid + (0.5 if is_call else -0.5) * (F1 - F0), None


OPTIONS = pd.DataFrame({
    "instrument_id": [CALL, PUT],
    "strike_price": [7000.0, 7000.0],
    "instrument_class": ["C", "P"],
    "expiration": [pd.Timestamp("2026-10-07 20:00", tz="UTC")] * 2,
    "unit_of_measure_qty": [50.0, 50.0],
})


def quotes(*rows):
    """rows: (ns, instrument_id, bid, ask[, action])."""
    records = []
    for seq, (ns, iid, bid, ask, *action) in enumerate(rows):
        records.append({
            "ts_event": at(ns), "instrument_id": iid, "action": action[0] if action else "A",
            "sequence": seq, "bid_px_00": bid, "ask_px_00": ask, "bid_sz_00": 3, "ask_sz_00": 4,
        })
    return pd.DataFrame(records)


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


def detect(ev, q, options=OPTIONS.iloc[[0]], **kw):
    return detect_stale_quotes(ev, q, options, fair_value=linear_fair, **kw)


def test_cost_is_half_tick_plus_fee():
    assert cost_points(50) == pytest.approx(COST)


def test_stale_ask_until_repriced():
    q = quotes(
        (0, CALL, 9.9, 10.1),
        (150, CALL, 9.9, 10.2),   # still below fair - cost: window continues
        (180, CALL, 10.4, 10.2),  # bid moves (crossed, ask unchanged): still stale
        (200, CALL, 10.4, 10.6),  # ask re-priced: reaction
    )
    r = detect(events((100, 7000.0, 7001.0, 1000)), q).iloc[0]
    assert r.status == "stale" and r.side == "ask"
    assert r.fair == pytest.approx(10.5)
    assert r.edge == pytest.approx(10.5 - 10.1 - COST)
    assert r.edge_usd == pytest.approx(r.edge * 50)
    assert r.quote_size == 4
    assert r.start == at(100) and r.resolution == at(200)
    assert r.duration_ns == 100 and not r.censored


def test_stale_bid_after_down_move():
    r = detect(events((100, 7000.0, 6999.0, 1000)), quotes((0, CALL, 9.9, 10.1), (300, CALL, 9.4, 9.6))).iloc[0]
    assert r.status == "stale" and r.side == "bid"
    assert r.edge == pytest.approx(9.9 - 9.5 - COST)
    assert r.duration_ns == 200


def test_put_moves_against_the_future():
    r = detect(events((100, 7000.0, 7001.0, 1000)), quotes((0, PUT, 9.9, 10.1)), OPTIONS.iloc[[1]]).iloc[0]
    assert r.status == "stale" and r.side == "bid"


def test_small_move_within_costs_is_not_stale():
    # fair = 10.125: ask 10.1 is not below 10.125 - 0.045
    r = detect(events((100, 7000.0, 7000.25, 1000)), quotes((0, CALL, 9.9, 10.1))).iloc[0]
    assert r.status == "not_stale" and r.side is None and pd.isna(r.start)


def test_edge_must_exceed_cost_exactly():
    # dF chosen so ask sits just inside / just outside fair - cost
    inside = 2 * (0.1 + COST) - 1e-6
    outside = 2 * (0.1 + COST) + 1e-6
    q = quotes((0, CALL, 9.9, 10.1))
    assert detect(events((100, 7000.0, 7000.0 + inside, 1000)), q).status[0] == "not_stale"
    assert detect(events((100, 7000.0, 7000.0 + outside, 1000)), q).status[0] == "stale"


def test_censored_at_observation_end():
    q = quotes((0, CALL, 9.9, 10.1), (600, CALL, 10.4, 10.6))
    r = detect(events((100, 7000.0, 7001.0, 500)), q).iloc[0]
    assert r.censored and pd.isna(r.resolution)
    assert r.window_end == at(500) and r.duration_ns == 400  # lower bound


def test_window_falls_back_to_next_event():
    q = quotes((0, CALL, 9.9, 10.1), (600, CALL, 10.4, 10.6))
    r = detect(events((100, 7000.0, 7001.0), (400, 7001.0, 7001.25)), q)
    assert r.window_end[0] == at(400) and r.censored[0]
    assert r.window_end[1] == at(400 + config.MAX_WINDOW_NS)


def test_window_never_passes_expiry():
    opts = OPTIONS.iloc[[0]].assign(expiration=at(300))
    r = detect(events((100, 7000.0, 7001.0, 1000)), quotes((0, CALL, 9.9, 10.1)), opts).iloc[0]
    assert r.window_end == at(300) and r.censored
    assert detect(events((300, 7000.0, 7001.0, 1000)), quotes((0, CALL, 9.9, 10.1)), opts).status[0] == "expired"


def test_pulled_quote_ends_window():
    q = quotes((0, CALL, 9.9, 10.1), (250, CALL, 9.9, np.nan))
    r = detect(events((100, 7000.0, 7001.0, 1000)), q).iloc[0]
    assert r.resolution == at(250)


def test_update_at_t0_is_post_move():
    q = quotes((0, CALL, 9.9, 10.1), (100, CALL, 10.4, 10.6))
    r = detect(events((100, 7000.0, 7001.0, 1000)), q).iloc[0]
    assert r.ask == 10.1 and r.status == "stale"
    assert r.resolution == at(100) and r.duration_ns == 0


def test_ineligible_pairs():
    ev = events((100, 7000.0, 7001.0, 1000))
    assert detect(ev, quotes((200, CALL, 9.9, 10.1))).status[0] == "no_quote"
    assert detect(ev, quotes((0, CALL, 10.1, 9.9))).status[0] == "invalid_quote"
    assert detect(ev, quotes((0, CALL, np.nan, 10.1))).status[0] == "invalid_quote"
    assert detect(events((100, 7000.0, 7000.0, 1000)), quotes((0, CALL, 9.9, 10.1))).status[0] == "no_move"
    r = detect_stale_quotes(ev, quotes((0, CALL, 9.9, 10.1)), OPTIONS.iloc[[0]],
                            fair_value=lambda *a: (np.nan, "low_vega")).iloc[0]
    assert r.status == "low_vega" and pd.isna(r.side)


def test_trades_skipped_and_same_timestamp_collapsed():
    q = quotes(
        (0, CALL, 9.0, 9.2),
        (0, CALL, 9.9, 10.1),           # same ts_event: last state wins
        (50, CALL, 1.0, 2.0, "T"),      # trade record: ignored
    )
    book = option_bbo(q)
    assert len(book) == 1 and book.loc[0, "bid"] == 9.9
    assert detect(events((100, 7000.0, 7001.0, 1000)), q).ask[0] == 10.1


def test_only_selected_events():
    ev = events((100, 7000.0, 7001.0, 1000), (2000, 7001.0, 7002.0, 3000)).assign(selected=[True, False])
    assert detect(ev, quotes((0, CALL, 9.9, 10.1))).event_id.tolist() == [0]


def test_one_row_per_event_and_option():
    q = quotes((0, CALL, 9.9, 10.1), (0, PUT, 9.9, 10.1))
    r = detect(events((100, 7000.0, 7001.0, 1000), (2000, 7001.0, 7000.75, 3000)), q, OPTIONS)
    assert len(r) == 4
    assert set(zip(r.event_id, r.instrument_id)) == {(0, 1), (1, 1), (0, 2), (1, 2)}


def test_cached_fair_value_ignores_time_to_expiry():
    calls = []
    fn = CachedFairValue(lambda *a: calls.append(a) or (1.0, None))
    fn(10.0, 7000.0, 7001.0, 7000.0, 0.001, True)
    fn(10.0, 7000.0, 7001.0, 7000.0, 0.002, True)
    fn(10.0, 7000.0, 7001.0, 7000.0, 0.002, False)
    assert len(calls) == 2


def test_black76_fair_value_does_not_depend_on_expiry():
    """Justifies CachedFairValue; runs once #5 (black76.py) is merged."""
    black76 = pytest.importorskip("stale_quotes.black76")
    for T in (1 / 365 / 24, 3 / 365 / 24):
        mid = black76.price(7000.0, 7010.0, T, 0.15, True)
        values = [
            black76.fair_value(mid, 7000.0, 7002.0, 7010.0, T * s, True, use_gamma=True)[0]
            for s in (0.5, 1.0, 2.0)
        ]
        assert max(values) - min(values) < 1e-6
