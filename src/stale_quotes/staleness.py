"""Flag economically stale 0DTE option quotes after ES futures moves.

For every futures event and selected option, the quote standing in the book
when the future moved is compared with the option's post-move fair value.

Definitions (README, Method: stale test)

- Pre-move state: the option's last top-of-book update strictly before the
  event time ``t0``. Its mid is the input to fair value; its bid and ask are the
  quotes being tested. Both sides must be present and uncrossed.
- Fair value: Black-76 shift of the pre-move mid by the futures move
  (``price_before`` -> ``price_after``), from `black76.fair_value`.
- Cost: ``OPTION_TICK / 2 + FEE_PER_CONTRACT_USD / multiplier`` (see config.py
  for the flat taker-fee assumption).
- Stale ask: ``ask < fair - cost`` (buying it beats fair value after costs).
  Stale bid: ``bid > fair + cost`` (selling into it does).
- Start: the stale window begins at ``t0``, the futures move's exchange
  timestamp: from then on the standing quote is mispriced.
- Reaction: the option has reacted at its first top-of-book update after
  ``t0`` whose quote on the stale side no longer violates the threshold
  (re-priced to ``ask >= fair - cost`` / ``bid <= fair + cost``, or pulled
  entirely). Updates that leave the stale side stale (size changes, moves on the
  other side, re-quotes that are still too cheap/rich) do not end the window.
  The window ends at that update's ``ts_event`` (the resolution time).
- Overlap: fair value is only defined for this move, so the window is censored
  at the event's ``observation_end`` (the next futures price move, the issue #4
  horizon or the end of continuous data), and never runs past expiry. A window
  still open then is reported with ``censored=True`` and its duration is a lower
  bound. Each (event, option) pair is judged on its own, so a quote left stale
  across several futures moves appears once per move.
- Several updates with one ``ts_event`` are collapsed to the last one; trade
  records are skipped because their book state is the pre-trade one.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from stale_quotes import config

# fair_value(mid, F0, F1, K, T, is_call) -> (fair, reason); reason is None if valid.
FairValueFn = Callable[[float, float, float, float, float, bool], tuple[float, str | None]]

RESULT_COLUMNS = [
    "event_id", "instrument_id", "strike_price", "instrument_class", "t0",
    "price_before", "price_after", "bid", "ask", "mid", "fair", "cost",
    "status", "side", "edge", "edge_usd", "quote_size",
    "start", "resolution", "window_end", "duration_ns", "censored",
]


def black76_fair_value(mid, F0, F1, K, T, is_call):
    """Fair value from #5's `black76.fair_value`, with the configured gamma term."""
    try:
        from stale_quotes import black76
    except ImportError as exc:  # pragma: no cover - until #5 is merged
        raise ImportError("staleness needs black76.py from issue #5 (PR #14)") from exc
    fair, _, reason = black76.fair_value(mid, F0, F1, K, T, is_call, use_gamma=config.USE_GAMMA)
    return fair, reason


class CachedFairValue:
    """Memoise a fair-value function on (mid, F0, F1, K, is_call).

    With r = 0 a Black-76 price depends on T only through sigma * sqrt(T),
    which the pre-move mid pins down, so delta, gamma and the fair value are
    the same for every T > 0. Mids and futures prices sit on tick grids, so
    the same inputs recur many times a day.
    """

    def __init__(self, fn: FairValueFn):
        self.fn = fn
        self.cache: dict[tuple, tuple[float, str | None]] = {}

    def __call__(self, mid, F0, F1, K, T, is_call):
        key = (mid, F0, F1, K, is_call)
        if key not in self.cache:
            self.cache[key] = self.fn(mid, F0, F1, K, T, is_call)
        return self.cache[key]


def cost_points(multiplier: float) -> float:
    """Round-trip-free cost of taking one contract, in option price points."""
    return config.OPTION_TICK / 2 + config.FEE_PER_CONTRACT_USD / multiplier


def _ns(values) -> np.ndarray:
    """Epoch nanoseconds of tz-aware timestamps (NaT -> min int64)."""
    return pd.DatetimeIndex(values).tz_convert("UTC").as_unit("ns").asi8


def option_bbo(quotes: pd.DataFrame) -> pd.DataFrame:
    """Top-of-book state of each option after every quote update.

    Takes the frame `DBNStore.to_df()` returns for `mbp-1`.
    """
    q = quotes[quotes["action"] != "T"]
    keys = ["instrument_id", "ts_event"] + (["sequence"] if "sequence" in q.columns else [])
    q = q.sort_values(keys, kind="stable").drop_duplicates(["instrument_id", "ts_event"], keep="last")
    return q.rename(columns={
        "bid_px_00": "bid", "ask_px_00": "ask", "bid_sz_00": "bid_size", "ask_sz_00": "ask_size",
    })[["instrument_id", "ts_event", "bid", "ask", "bid_size", "ask_size"]].reset_index(drop=True)


def _window_ends(events: pd.DataFrame, t0: np.ndarray, max_window_ns: int) -> np.ndarray:
    if "observation_end" in events.columns:
        end = _ns(events["observation_end"])
        missing = events["observation_end"].isna().to_numpy()
        return np.where(missing, t0 + max_window_ns, end)
    order = np.argsort(t0, kind="stable")
    following = np.full(len(t0), np.iinfo(np.int64).max)
    following[order[:-1]] = t0[order[1:]]
    return np.minimum(following, t0 + max_window_ns)


def detect_stale_quotes(
    events: pd.DataFrame,
    quotes: pd.DataFrame,
    options: pd.DataFrame,
    fair_value: FairValueFn | None = None,
    max_window_ns: int = config.MAX_WINDOW_NS,
) -> pd.DataFrame:
    """One row per (event, option) with the stale-quote outcome.

    events:  futures moves; needs ``t0``, ``price_before``, ``price_after`` and
             optionally ``event_id``, ``observation_end`` and ``selected``
             (issue #4's ``events.parquet``).
    quotes:  option ``mbp-1`` records (``DBNStore.to_df()``).
    options: one row per option: ``instrument_id``, ``strike_price``,
             ``instrument_class`` ('C'/'P'), ``expiration``, ``unit_of_measure_qty``.

    ``status`` is ``stale``, ``not_stale`` or why the pair is not eligible:
    ``no_quote``, ``invalid_quote``, ``expired``, ``no_move`` or a fair-value
    reason from black76 (``below_intrinsic``, ``low_vega``, ...).
    """
    if "selected" in events.columns:
        events = events[events["selected"].astype(bool)]
    events = events.reset_index(drop=True)
    event_ids = events["event_id"].to_numpy() if "event_id" in events.columns else events.index.to_numpy()
    t0 = _ns(events["t0"])
    window_end = _window_ends(events, t0, max_window_ns)
    f0 = events["price_before"].to_numpy(float)
    f1 = events["price_after"].to_numpy(float)
    fair_fn = CachedFairValue(fair_value or black76_fair_value)
    bbo = option_bbo(quotes)

    out = {c: [] for c in RESULT_COLUMNS}
    for opt in options.itertuples(index=False):
        book = bbo[bbo["instrument_id"] == opt.instrument_id]
        ts = _ns(book["ts_event"])
        bid, ask = book["bid"].to_numpy(float), book["ask"].to_numpy(float)
        bid_size, ask_size = book["bid_size"].to_numpy(), book["ask_size"].to_numpy()
        expiry = _ns([opt.expiration])[0]
        cost = cost_points(opt.unit_of_measure_qty)
        is_call = opt.instrument_class == "C"
        strike = float(opt.strike_price)
        pre = np.searchsorted(ts, t0, side="left") - 1  # last update strictly before t0
        end = np.minimum(window_end, expiry)
        stop = np.searchsorted(ts, end, side="left")  # updates in [t0, end)

        for i in range(len(t0)):
            row = dict.fromkeys(RESULT_COLUMNS)
            row.update(
                event_id=event_ids[i], instrument_id=opt.instrument_id, strike_price=strike,
                instrument_class=opt.instrument_class, t0=t0[i], price_before=f0[i],
                price_after=f1[i], cost=cost, window_end=end[i], censored=False,
            )
            j = pre[i]
            if j >= 0:
                row.update(bid=bid[j], ask=ask[j])
            status = _evaluate(row, j, bid, ask, t0[i], expiry, fair_fn, strike, is_call, cost)
            row["status"] = status
            if status == "stale":
                stale_ask = row["side"] == "ask"
                row["quote_size"] = (ask_size if stale_ask else bid_size)[j]
                row["edge_usd"] = row["edge"] * opt.unit_of_measure_qty
                after = (ask if stale_ask else bid)[j + 1 : stop[i]]
                with np.errstate(invalid="ignore"):
                    still = after < row["fair"] - cost if stale_ask else after > row["fair"] + cost
                reacted = np.flatnonzero(~still)
                row["start"] = t0[i]
                if reacted.size:
                    row["resolution"] = ts[j + 1 + reacted[0]]
                    row["duration_ns"] = row["resolution"] - t0[i]
                else:
                    row["censored"] = True
                    row["duration_ns"] = end[i] - t0[i]
            for c in RESULT_COLUMNS:
                out[c].append(row[c])

    result = pd.DataFrame(out, columns=RESULT_COLUMNS)
    for c in ["t0", "start", "resolution", "window_end"]:
        ns = pd.array(result[c], dtype="Int64").to_numpy(dtype="int64", na_value=np.iinfo(np.int64).min)
        result[c] = pd.to_datetime(ns, utc=True)
    result["duration_ns"] = result["duration_ns"].astype("Int64")
    return result


def _evaluate(row, j, bid, ask, t0, expiry, fair_fn, strike, is_call, cost) -> str:
    """Fill fair value, side and edge for one pair and return its status."""
    if j < 0:
        return "no_quote"
    b, a = bid[j], ask[j]
    if not (np.isfinite(b) and np.isfinite(a) and 0 < b < a):
        return "invalid_quote"
    if t0 >= expiry:
        return "expired"
    if row["price_after"] == row["price_before"]:
        return "no_move"
    mid = (a + b) / 2
    T = (expiry - t0) / 1e9 / (365 * 24 * 3600)
    fair, reason = fair_fn(mid, row["price_before"], row["price_after"], strike, T, is_call)
    row.update(mid=mid, fair=fair)
    if reason:
        return reason
    if a < fair - cost:
        row.update(side="ask", edge=fair - a - cost)
        return "stale"
    if b > fair + cost:
        row.update(side="bid", edge=b - fair - cost)
        return "stale"
    return "not_stale"


# ---------------------------------------------------------------------------
# Running on cached data
# ---------------------------------------------------------------------------


def detect_for_date(
    trading_date: date,
    events_path: Path,
    raw_dir: Path = config.RAW_DIR,
    instruments_path: Path | None = None,
    schema: str = "mbp-1",
) -> pd.DataFrame:
    """Stale-quote table for one date from the download cache and an events file."""
    import databento as db

    instruments_path = instruments_path or config.PROCESSED_DIR / "instruments.parquet"
    meta = pd.read_parquet(instruments_path)
    options = meta[(meta["trading_date"] == pd.Timestamp(trading_date)) & meta["role"].isin(["call", "put"])]
    if options.empty:
        raise FileNotFoundError(f"no options for {trading_date} in {instruments_path}; run scripts/download.py")
    quotes = db.DBNStore.from_file(raw_dir / schema / f"{trading_date:%Y%m%d}" / "options.dbn.zst").to_df()
    return detect_stale_quotes(pd.read_parquet(events_path), quotes, options)


def summarize(result: pd.DataFrame) -> pd.DataFrame:
    """Counts per status and, for stale pairs, side, edge and duration."""
    stale = result[result["status"] == "stale"]
    return pd.Series({
        "pairs": len(result),
        **result["status"].value_counts().add_prefix("status_").to_dict(),
        "stale_ask": (stale["side"] == "ask").sum(),
        "stale_bid": (stale["side"] == "bid").sum(),
        "censored": stale["censored"].sum(),
        "median_edge": stale["edge"].median(),
        "median_duration_us": stale.loc[~stale["censored"], "duration_ns"].median() / 1e3,
    }).to_frame("value")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Detect stale 0DTE option quotes after ES futures moves.")
    parser.add_argument("--dates", nargs="+", type=date.fromisoformat, default=config.STUDY_DATES)
    parser.add_argument("--events", required=True,
                        help="events parquet path with a {date} placeholder (YYYY-MM-DD), "
                             "e.g. issue4_report/{date}/events.parquet")
    parser.add_argument("--out-dir", type=Path, default=config.PROCESSED_DIR / "stale")
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for trading_date in args.dates:
        result = detect_for_date(trading_date, Path(args.events.format(date=trading_date.isoformat())))
        path = args.out_dir / f"{trading_date:%Y%m%d}.parquet"
        result.to_parquet(path, index=False)
        print(f"{trading_date}: wrote {path}")
        print(summarize(result).to_string())


if __name__ == "__main__":
    main()
