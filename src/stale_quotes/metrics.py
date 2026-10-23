"""Results for research questions 1-3: reaction latency, opportunity rate,
stale-window duration and edge, split by move size, moneyness and time of day.

Inputs
- ``stale``: the table from `staleness.detect_stale_quotes`, one row per
  (futures event, option).
- ``latency``: the table from `reaction_latency` below, same keys.

Definitions
- Reaction latency (RQ1): time from the futures move ``t0`` to the option's
  first top-of-book *price* change (bid or ask) relative to its last quote
  before ``t0``. Size-only updates do not count. ``directional_latency_ns`` only
  counts a change that moves the mid the way delta says it should (calls with
  the future, puts against it). Updates stamped exactly ``t0`` count, with
  latency 0; their share is reported because the futures and options engines
  run on separate clocks (issue #1).
- Censoring: like `staleness`, a pair is only followed until the event's
  ``observation_end`` (next futures move, 10 ms horizon or data gap) or
  expiry. A pair with no reaction by then is right-censored, so latency and
  duration quantiles come from a Kaplan-Meier estimate rather than from the
  uncensored rows only, which would bias them down.
- Opportunity rate (RQ2): share of eligible futures events (at least one option
  with a valid ``stale``/``not_stale`` verdict) with one or more stale options.
- Edge: ``staleness.edge`` is already net of half an option tick and the flat
  fee. ``capacity_usd = edge_usd * quote_size`` is the most a taker could have
  made on the displayed size.
"""

from __future__ import annotations

import argparse
from datetime import date, time
from pathlib import Path

import numpy as np
import pandas as pd

from stale_quotes import config

FUTURES_TICK = 0.25

KEYS = ["event_id", "instrument_id"]

# abs(move) in ES ticks. Midpoints move in half ticks; #4 calls < 1 "sub_tick",
# 1 "single_tick" and > 1 "multi_tick".
MOVE_BINS = [0, 0.75, 1.25, 2.25, 4.25, np.inf]
MOVE_LABELS = ["<1", "1", "1.5-2", "2.5-4", ">4"]

# Signed distance out of the money in index points at t0 (strike - F for calls,
# F - strike for puts). Strikes are 5 points apart, so "ATM" is the nearest one.
MONEYNESS_BINS = [-np.inf, -7.5, -2.5, 2.5, 7.5, 17.5, np.inf]
MONEYNESS_LABELS = ["ITM >7.5", "ITM 2.5-7.5", "ATM", "OTM 2.5-7.5", "OTM 7.5-17.5", "OTM >17.5"]

# Session buckets in STUDY_TZ (New York), left-closed.
SESSION_BUCKETS = [
    ("open", time(9, 30), time(10, 0)),
    ("morning", time(10, 0), time(12, 0)),
    ("midday", time(12, 0), time(14, 0)),
    ("afternoon", time(14, 0), time(15, 30)),
    ("close", time(15, 30), time(16, 0)),
]
SESSION_LABELS = [b[0] for b in SESSION_BUCKETS]

QUANTILES = (0.1, 0.25, 0.5, 0.75, 0.9)


# ---------------------------------------------------------------------------
# Reaction latency
# ---------------------------------------------------------------------------


def _ns(values) -> np.ndarray:
    return pd.DatetimeIndex(values).tz_convert("UTC").as_unit("ns").asi8


def _next_true(mask: np.ndarray) -> np.ndarray:
    """out[k] = smallest k' >= k with mask[k'], or len(mask) if none."""
    n = len(mask)
    idx = np.where(mask, np.arange(n), n)
    return np.minimum.accumulate(idx[::-1])[::-1] if n else idx


def _next_beyond(x: np.ndarray, greater: bool) -> np.ndarray:
    """out[k] = first k' > k with x[k'] > x[k] (or < if not greater), else len(x).

    Monotonic-stack "next greater element". NaNs never qualify and are never
    waited on, so they cannot block earlier entries.
    """
    n = len(x)
    out = np.full(n, n, dtype=np.int64)
    stack: list[int] = []
    for k in range(n):
        v = x[k]
        if v != v:  # NaN
            continue
        while stack and (v > x[stack[-1]] if greater else v < x[stack[-1]]):
            out[stack.pop()] = k
        stack.append(k)
    return out


def reaction_latency(
    events: pd.DataFrame,
    bbo: pd.DataFrame,
    options: pd.DataFrame,
    max_window_ns: int = 10_000_000,
) -> pd.DataFrame:
    """One row per (event, option): time until the option quote first re-prices.

    events:  needs ``t0``, ``price_before``, ``price_after``; optional
             ``event_id``, ``observation_end``, ``selected`` (issue #4).
    bbo:     option top of book, one row per update: ``instrument_id``,
             ``ts_event``, ``bid``, ``ask`` (`staleness.option_bbo`).
    options: ``instrument_id``, ``strike_price``, ``instrument_class``,
             ``expiration``.
    """
    if "selected" in events.columns:
        events = events[events["selected"].astype(bool)]
    events = events.reset_index(drop=True)
    ids = events["event_id"].to_numpy() if "event_id" in events.columns else events.index.to_numpy()
    t0 = _ns(events["t0"])
    if "observation_end" in events.columns:
        obs = events["observation_end"]
        end = np.where(obs.isna().to_numpy(), t0 + max_window_ns, _ns(obs.fillna(events["t0"])))
    else:
        end = t0 + max_window_ns
    f0 = events["price_before"].to_numpy(float)
    f1 = events["price_after"].to_numpy(float)
    dF = np.sign(f1 - f0)

    frames = []
    for opt in options.itertuples(index=False):
        book = bbo[bbo["instrument_id"] == opt.instrument_id].sort_values("ts_event", kind="stable")
        # A sentinel row at +inf time keeps every index lookup in range.
        ts = np.r_[_ns(book["ts_event"]), np.iinfo(np.int64).max]
        bid = np.r_[book["bid"].to_numpy(float), np.nan]
        ask = np.r_[book["ask"].to_numpy(float), np.nan]
        valid = np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (bid < ask)
        mid = np.where(valid, (bid + ask) / 2, np.nan)

        def same(x):
            prev = np.r_[np.nan, x[:-1]]
            return (x == prev) | (np.isnan(x) & np.isnan(prev))

        changed = ~(same(bid) & same(ask))
        changed[-1] = True  # sentinel
        first_change = np.r_[_next_true(changed), len(ts) - 1]
        up, down = _next_beyond(mid, True), _next_beyond(mid, False)
        up[up == len(ts)] = len(ts) - 1
        down[down == len(ts)] = len(ts) - 1

        is_call = opt.instrument_class == "C"
        expected = dF * (1 if is_call else -1)  # sign the mid should move
        expiry = _ns([opt.expiration])[0]
        stop = np.minimum(end, expiry)
        j = np.searchsorted(ts[:-1], t0, side="left") - 1  # last update strictly before t0
        has_pre = j >= 0
        jj = np.maximum(j, 0)

        def resolve(k):
            t = ts[k]
            reacted = t < stop
            return np.where(reacted, t - t0, stop - t0), ~reacted

        lat, cens = resolve(first_change[jj + 1])
        k_dir = np.where(expected > 0, up[jj], np.where(expected < 0, down[jj], len(ts) - 1))
        dlat, dcens = resolve(k_dir)

        status = np.where(~has_pre, "no_quote", np.where(~valid[jj], "invalid_quote",
                          np.where(t0 >= expiry, "expired", np.where(dF == 0, "no_move", "ok"))))
        frames.append(pd.DataFrame({
            "event_id": ids,
            "instrument_id": opt.instrument_id,
            "strike_price": float(opt.strike_price),
            "instrument_class": opt.instrument_class,
            "t0": t0,
            "price_before": f0,
            "price_after": f1,
            "latency_status": status,
            "latency_ns": lat,
            "latency_censored": cens,
            "directional_latency_ns": dlat,
            "directional_censored": dcens,
        }))
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if len(out):
        ok = out["latency_status"] == "ok"
        for c in ["latency_ns", "directional_latency_ns"]:
            out[c] = out[c].where(ok).astype("Int64")
        for c in ["latency_censored", "directional_censored"]:
            out[c] = out[c].where(ok).astype("boolean")
        out["t0"] = pd.to_datetime(out["t0"].to_numpy(), utc=True)
    return out


# ---------------------------------------------------------------------------
# Buckets
# ---------------------------------------------------------------------------


def otm_points(strike, F, instrument_class) -> np.ndarray:
    strike, F = np.asarray(strike, float), np.asarray(F, float)
    return np.where(np.asarray(instrument_class) == "C", strike - F, F - strike)


def session_bucket(t0) -> pd.Categorical:
    local = pd.DatetimeIndex(t0).tz_convert(config.STUDY_TZ)
    minutes = local.hour * 60 + local.minute + local.second / 60
    labels = np.full(len(local), None, dtype=object)
    for name, start, stop in SESSION_BUCKETS:
        lo, hi = start.hour * 60 + start.minute, stop.hour * 60 + stop.minute
        labels[(minutes >= lo) & (minutes < hi)] = name
    return pd.Categorical(labels, categories=SESSION_LABELS, ordered=True)


def annotate(table: pd.DataFrame) -> pd.DataFrame:
    """Add move size, moneyness and session columns to a stale or latency table."""
    out = table.copy()
    out["move_ticks"] = (out["price_after"] - out["price_before"]) / FUTURES_TICK
    out["abs_move_ticks"] = out["move_ticks"].abs()
    out["move_bucket"] = pd.cut(out["abs_move_ticks"], MOVE_BINS, labels=MOVE_LABELS)
    out["otm_points"] = otm_points(out["strike_price"], out["price_before"], out["instrument_class"])
    out["moneyness"] = pd.cut(out["otm_points"], MONEYNESS_BINS, labels=MONEYNESS_LABELS)
    out["session"] = session_bucket(out["t0"])
    return out


# ---------------------------------------------------------------------------
# Survival analysis
# ---------------------------------------------------------------------------


def kaplan_meier(durations, censored) -> pd.DataFrame:
    """Kaplan-Meier survival S(t) = P(duration > t) with right-censoring.

    Returns one row per distinct event time: ``time``, ``at_risk``, ``events``,
    ``survival``.
    """
    d = np.asarray(durations, dtype=float)
    c = np.asarray(censored, dtype=bool)
    keep = np.isfinite(d)
    d, c = d[keep], c[keep]
    if d.size == 0:
        return pd.DataFrame(columns=["time", "at_risk", "events", "survival"])
    times, inv = np.unique(d, return_inverse=True)
    deaths = np.bincount(inv, weights=~c, minlength=len(times))
    leaving = np.bincount(inv, minlength=len(times))
    at_risk = len(d) - np.r_[0, np.cumsum(leaving)[:-1]]
    surv = np.cumprod(1 - deaths / at_risk)
    km = pd.DataFrame({"time": times, "at_risk": at_risk, "events": deaths.astype(int), "survival": surv})
    return km[km["events"] > 0].reset_index(drop=True)


def km_quantiles(durations, censored, qs=QUANTILES) -> dict[str, float]:
    """Smallest t with 1 - S(t) >= q. NaN when censoring stops the curve short of q."""
    km = kaplan_meier(durations, censored)
    out = {}
    for q in qs:
        hit = km.loc[1 - km["survival"] >= q - 1e-12, "time"]
        out[f"p{round(q * 100)}"] = float(hit.iloc[0]) if len(hit) else np.nan
    return out


# ---------------------------------------------------------------------------
# Summary tables
# ---------------------------------------------------------------------------


def _groups(df: pd.DataFrame, by):
    if by is None:
        yield "all", df
    else:
        yield from df.groupby(by, observed=True)


def latency_summary(latency: pd.DataFrame, by=None, directional: bool = False) -> pd.DataFrame:
    """RQ1: KM latency quantiles in microseconds, per group."""
    col, cens = ("directional_latency_ns", "directional_censored") if directional else ("latency_ns", "latency_censored")
    ok = latency[latency["latency_status"] == "ok"]
    rows = []
    for key, g in _groups(ok, by):
        d = g[col].to_numpy(dtype=float, na_value=np.nan)
        c = g[cens].to_numpy(dtype=bool, na_value=True)
        q = km_quantiles(d, c)
        rows.append({
            "group": key, "pairs": len(g), "censored_share": c.mean(),
            "zero_latency_share": ((d == 0) & ~c).mean(),
            **{f"{k}_us": v / 1e3 for k, v in q.items()},
        })
    return _frame(rows, by)


def _event_key(df: pd.DataFrame) -> list[str]:
    """event_id restarts every day, so pooled tables key events by date too."""
    return ["trading_date", "event_id"] if "trading_date" in df.columns else ["event_id"]


def opportunity_summary(stale: pd.DataFrame, by=None) -> pd.DataFrame:
    """RQ2: how often a futures move leaves at least one option stale after costs."""
    judged = stale[stale["status"].isin(["stale", "not_stale"])].copy()
    judged["is_stale"] = judged["status"] == "stale"
    rows = []
    for key, g in _groups(judged, by):
        per_event = g.groupby(_event_key(g))["is_stale"].any()
        rows.append({
            "group": key,
            "events": len(per_event),
            "stale_events": int(per_event.sum()),
            "event_rate": per_event.mean(),
            "pairs": len(g),
            "stale_pairs": int(g["is_stale"].sum()),
            "pair_rate": g["is_stale"].mean(),
        })
    return _frame(rows, by)


def edge_summary(stale: pd.DataFrame, by=None) -> pd.DataFrame:
    """Edge after costs on stale pairs: points, $ per contract, $ on displayed size."""
    s = stale[stale["status"] == "stale"].copy()
    s["capacity_usd"] = s["edge_usd"] * s["quote_size"].astype(float)
    rows = []
    for key, g in _groups(s, by):
        rows.append({
            "group": key,
            "stale_pairs": len(g),
            "mean_edge_pts": g["edge"].mean(),
            "median_edge_pts": g["edge"].median(),
            "p90_edge_pts": g["edge"].quantile(0.9),
            "median_edge_usd": g["edge_usd"].median(),
            "median_quote_size": g["quote_size"].astype(float).median(),
            "total_capacity_usd": g["capacity_usd"].sum(),
        })
    return _frame(rows, by)


def duration_summary(stale: pd.DataFrame, by=None) -> pd.DataFrame:
    """RQ3: how long stale quotes survive (KM quantiles in microseconds)."""
    s = stale[stale["status"] == "stale"]
    rows = []
    for key, g in _groups(s, by):
        d = g["duration_ns"].to_numpy(dtype=float, na_value=np.nan)
        c = g["censored"].to_numpy(dtype=bool)
        rows.append({
            "group": key, "stale_pairs": len(g), "censored_share": c.mean(),
            **{f"{k}_us": v / 1e3 for k, v in km_quantiles(d, c).items()},
        })
    return _frame(rows, by)


def status_summary(stale: pd.DataFrame, by=None) -> pd.DataFrame:
    """Share of pairs per staleness status (stale, not_stale, no_quote, black76
    failures such as below_intrinsic or low_vega). Split by moneyness or session
    to see whether the pairs that drop out are concentrated somewhere."""
    if by is None:
        counts = stale["status"].value_counts().to_frame("all").T
        counts.index.name = "group"
    else:
        counts = pd.crosstab(stale[by], stale["status"])
    shares = counts.div(counts.sum(axis=1), axis=0)
    shares.insert(0, "pairs", counts.sum(axis=1))
    return shares


def _frame(rows, by) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    name = by if isinstance(by, str) else "group"
    return df.rename(columns={"group": name}).set_index(name)


SPLITS = {"overall": None, "move": "move_bucket", "moneyness": "moneyness", "session": "session"}


def build_tables(stale: pd.DataFrame, latency: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Every results table, keyed ``<measure>_<split>`` (e.g. ``latency_moneyness``)."""
    stale, latency = annotate(stale), annotate(latency)
    tables = {}
    for split, by in SPLITS.items():
        tables[f"latency_{split}"] = latency_summary(latency, by)
        tables[f"directional_latency_{split}"] = latency_summary(latency, by, directional=True)
        tables[f"opportunity_{split}"] = opportunity_summary(stale, by)
        tables[f"edge_{split}"] = edge_summary(stale, by)
        tables[f"duration_{split}"] = duration_summary(stale, by)
        tables[f"status_{split}"] = status_summary(stale, by)
    return tables


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _ax(ax):
    if ax is None:
        import matplotlib.pyplot as plt

        _, ax = plt.subplots(figsize=(7, 4))
    return ax


LEGEND_TITLES = {"move_bucket": "move (ES ticks)", "moneyness": "moneyness (pts)", "session": "session (ET)"}


def plot_km(table: pd.DataFrame, duration_col: str, censored_col: str, by: str,
            ax=None, cdf: bool = False, title: str = ""):
    """Step plot of KM survival (or 1 - S as a CDF) per group, x in microseconds (log)."""
    ax = _ax(ax)
    for key, g in table.groupby(by, observed=True):
        km = kaplan_meier(g[duration_col].to_numpy(dtype=float, na_value=np.nan),
                          g[censored_col].to_numpy(dtype=bool, na_value=True))
        if km.empty:
            continue
        t = np.r_[km["time"].iloc[0], km["time"]] / 1e3
        s = np.r_[1.0, km["survival"]]
        ax.step(np.maximum(t, 1e-3), 1 - s if cdf else s, where="post", label=f"{key} (n={len(g):,})")
    ax.set_xscale("log")
    ax.set_xlabel("microseconds after futures move")
    ax.set_ylabel("share reacted" if cdf else "share still stale")
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, title=LEGEND_TITLES.get(by, by))
    ax.set_title(title)
    return ax


def plot_latency(latency: pd.DataFrame, by: str = "moneyness", ax=None):
    ok = annotate(latency)
    ok = ok[ok["latency_status"] == "ok"]
    return plot_km(ok, "latency_ns", "latency_censored", by, ax=ax, cdf=True,
                   title="Option reaction latency (Kaplan-Meier)")


def plot_survival(stale: pd.DataFrame, by: str = "move_bucket", ax=None):
    s = annotate(stale)
    s = s[s["status"] == "stale"]
    return plot_km(s, "duration_ns", "censored", by, ax=ax, title="Stale-window survival")


def plot_rate(table: pd.DataFrame, column: str = "event_rate", ax=None, title: str = ""):
    """Bar chart of one column of a summary table (e.g. ``opportunity_move``)."""
    ax = _ax(ax)
    ax.bar(table.index.astype(str), table[column])
    ax.set_ylabel(column.replace("_", " "))
    ax.set_xlabel(table.index.name)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title(title)
    return ax


def plot_edge(stale: pd.DataFrame, ax=None):
    ax = _ax(ax)
    s = annotate(stale)
    s = s[s["status"] == "stale"]
    for key, g in s.groupby("move_bucket", observed=True):
        ax.hist(g["edge"], bins=40, histtype="step", label=f"{key} (n={len(g):,})")
    ax.axvline(0, color="grey", lw=0.8)
    ax.set_xlabel("edge after costs (option points)")
    ax.set_ylabel("stale pairs")
    ax.legend(fontsize=8, title="move (ES ticks)")
    ax.set_title("Edge of stale quotes")
    return ax


def save_figures(stale: pd.DataFrame, latency: pd.DataFrame, tables: dict, out_dir) -> list:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from pathlib import Path

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plots = {
        "latency_by_moneyness": lambda ax: plot_latency(latency, "moneyness", ax),
        "latency_by_session": lambda ax: plot_latency(latency, "session", ax),
        "survival_by_move": lambda ax: plot_survival(stale, "move_bucket", ax),
        "survival_by_moneyness": lambda ax: plot_survival(stale, "moneyness", ax),
        "opportunity_rate_by_move": lambda ax: plot_rate(tables["opportunity_move"], ax=ax,
                                                         title="Futures moves leaving a stale option"),
        "edge_by_move": lambda ax: plot_edge(stale, ax),
    }
    paths = []
    for name, draw in plots.items():
        fig, ax = plt.subplots(figsize=(7, 4))
        draw(ax)
        fig.tight_layout()
        path = out_dir / f"{name}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# Running on cached data
# ---------------------------------------------------------------------------


def compute_for_date(
    trading_date: date,
    events_path: Path,
    raw_dir: Path = config.RAW_DIR,
    instruments_path: Path | None = None,
    schema: str = "mbp-1",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stale-quote (#6) and reaction-latency tables for one date from the cache."""
    import databento as db

    from stale_quotes import staleness

    instruments_path = instruments_path or config.PROCESSED_DIR / "instruments.parquet"
    meta = pd.read_parquet(instruments_path)
    options = meta[(meta["trading_date"] == pd.Timestamp(trading_date)) & meta["role"].isin(["call", "put"])]
    if options.empty:
        raise FileNotFoundError(f"no options for {trading_date} in {instruments_path}; run scripts/download.py")
    quotes = db.DBNStore.from_file(raw_dir / schema / f"{trading_date:%Y%m%d}" / "options.dbn.zst").to_df()
    events = pd.read_parquet(events_path)
    stale = staleness.detect_stale_quotes(events, quotes, options)
    latency = reaction_latency(events, staleness.option_bbo(quotes), options)
    return stale, latency


def load_processed(processed_dir: Path = config.PROCESSED_DIR, dates=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pool the per-date ``stale/`` and ``latency/`` parquet files written by `run`."""
    out = []
    for kind in ["stale", "latency"]:
        frames = []
        for path in sorted((Path(processed_dir) / kind).glob("*.parquet")):
            d = pd.Timestamp(path.stem)
            if dates is not None and d.date() not in set(dates):
                continue
            frames.append(pd.read_parquet(path).assign(trading_date=d))
        if not frames:
            raise FileNotFoundError(f"no {kind} files in {processed_dir}; run scripts/run_study.py")
        out.append(pd.concat(frames, ignore_index=True))
    return out[0], out[1]


def write_results(stale: pd.DataFrame, latency: pd.DataFrame, results_dir: Path) -> dict[str, pd.DataFrame]:
    """Write every summary table (CSV) and figure (PNG) under ``results_dir``."""
    tables = build_tables(stale, latency)
    (results_dir / "tables").mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(results_dir / "tables" / f"{name}.csv")
    save_figures(stale, latency, tables, results_dir / "figures")
    return tables


def run(dates, events: str, processed_dir: Path = config.PROCESSED_DIR,
        results_dir: Path = config.ROOT_DIR / "results", recompute: bool = False) -> dict[str, pd.DataFrame]:
    """Per-date stale and latency tables (cached in ``processed_dir``), then pooled results."""
    for trading_date in dates:
        paths = {k: Path(processed_dir) / k / f"{trading_date:%Y%m%d}.parquet" for k in ["stale", "latency"]}
        if recompute or not all(p.exists() for p in paths.values()):
            stale, latency = compute_for_date(trading_date, Path(events.format(date=trading_date.isoformat())))
            for kind, table in zip(["stale", "latency"], [stale, latency]):
                paths[kind].parent.mkdir(parents=True, exist_ok=True)
                table.to_parquet(paths[kind], index=False)
        print(f"{trading_date}: {paths['stale'].name} ready")
    stale, latency = load_processed(processed_dir, dates)
    return write_results(stale, latency, Path(results_dir))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Latency, opportunity, duration and edge results (issue #7).")
    parser.add_argument("--dates", nargs="+", type=date.fromisoformat, default=config.STUDY_DATES)
    parser.add_argument("--events", default="issue4_report/{date}/events.parquet",
                        help="events parquet path with a {date} placeholder (YYYY-MM-DD)")
    parser.add_argument("--results-dir", type=Path, default=config.ROOT_DIR / "results")
    parser.add_argument("--recompute", action="store_true", help="ignore cached per-date tables")
    args = parser.parse_args(argv)
    tables = run(args.dates, args.events, results_dir=args.results_dir, recompute=args.recompute)
    for name in ["opportunity_move", "duration_move", "latency_moneyness"]:
        print(f"\n{name}\n{tables[name].to_string()}")
    print(f"\nwrote {args.results_dir}/tables and {args.results_dir}/figures")


if __name__ == "__main__":
    main()
