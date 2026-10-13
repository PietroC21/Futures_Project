"""Pick the ES futures contract, the 0DTE option expiry and near-the-money strikes.

For a trading date the selection is fully determined by Databento instrument
definitions plus one futures price, so no symbols are entered by hand:

1. Download the day's definitions for ES futures and every ES option root.
2. Keep the options on an ES outright whose expiration falls on the trading
   date and settles after the cash open (PM-settled, i.e. tradeable 0DTE).
   If several roots qualify, keep the one with the most listed contracts.
3. The underlying is the future named in those options' definitions.
4. Sample the underlying's price at the reference time and take the
   `n_strikes` listed strikes closest to it, keeping both the call and put.

The pure logic (`select_instruments` and helpers) works on the DataFrame that
`DBNStore.to_df()` returns, so it can be tested without network access.

    python -m stale_quotes.instruments 2026-10-07 2026-10-08
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd

from stale_quotes import config

QUARTER_CODES = {3: "H", 6: "M", 9: "U", 12: "Z"}
ES_OUTRIGHT_PATTERN = r"^ES[HMUZ]\d$"
# AM-settled quarterly options stop trading at 08:30 CT; anything expiring
# after this is PM-settled and trades through the session we study.
PM_SETTLEMENT_AFTER = time(9, 0)

METADATA_COLUMNS = [
    "instrument_id",
    "raw_symbol",
    "instrument_class",
    "security_type",
    "asset",
    "underlying",
    "underlying_id",
    "strike_price",
    "expiration",
    "activation",
    "unit_of_measure_qty",
    "display_factor",
    "min_price_increment",
    "tick_rule",
    "currency",
    "exchange",
    "group",
]


class InstrumentsUnavailable(Exception):
    """The instruments needed for a trading date do not exist or have no data."""


# ---------------------------------------------------------------------------
# Futures roll calendar
# ---------------------------------------------------------------------------


def third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(4 - first.weekday()) % 7 + 14)


def roll_date(year: int, month: int) -> date:
    """CME ES roll date: the Thursday 8 days before the contract expires."""
    return third_friday(year, month) - timedelta(days=8)


def lead_future_symbol(trading_date: date) -> str:
    """Raw symbol (e.g. ``ESZ6``) of the ES contract that is lead on a date.

    Liquidity moves to the next quarterly contract on the roll date.
    """
    year, month = trading_date.year, trading_date.month
    month = 3 * ((month - 1) // 3 + 1)  # first quarterly month on/after `month`
    while trading_date >= roll_date(year, month):
        month += 3
        if month > 12:
            year, month = year + 1, 3
    return f"ES{QUARTER_CODES[month]}{year % 10}"


# ---------------------------------------------------------------------------
# Selection from definitions (pure)
# ---------------------------------------------------------------------------


def clean_definitions(definitions: pd.DataFrame) -> pd.DataFrame:
    """Latest definition per instrument, with deleted instruments removed.

    Databento repeats definitions during the day, and the frame is indexed by
    ``ts_recv``; this keeps the last version of each ``instrument_id``.
    """
    df = definitions.reset_index() if "ts_recv" in definitions.index.names else definitions
    df = df.sort_values("ts_recv", kind="stable").drop_duplicates("instrument_id", keep="last")
    df = df[df["security_update_action"] != "D"]
    return df.reset_index(drop=True)


def zero_dte_options(definitions: pd.DataFrame, trading_date: date) -> pd.DataFrame:
    """Options on an ES outright that expire on `trading_date` after the cash open.

    When more than one option root expires that day, the root with the most
    listed contracts is kept so the result is always a single series.
    """
    df = clean_definitions(definitions)
    options = df[
        df["instrument_class"].isin(["C", "P"])
        & df["underlying"].str.match(ES_OUTRIGHT_PATTERN)
    ]
    expiry = options["expiration"].dt.tz_convert(config.EXCHANGE_TZ)
    same_day = options[
        (expiry.dt.date == trading_date) & (expiry.dt.time > PM_SETTLEMENT_AFTER)
    ]
    if same_day.empty:
        raise InstrumentsUnavailable(f"no PM-settled ES option series expires on {trading_date}")

    counts = same_day.groupby("asset").size()
    best = sorted(counts.index, key=lambda asset: (-counts[asset], asset))[0]
    series = same_day[same_day["asset"] == best]
    if series["underlying_id"].nunique() != 1:
        raise InstrumentsUnavailable(f"{best} options on {trading_date} reference several futures")
    return series


def underlying_future(definitions: pd.DataFrame, options: pd.DataFrame) -> pd.Series:
    """Definition row of the future that `options` settle into."""
    df = clean_definitions(definitions)
    underlying_id = options["underlying_id"].iloc[0]
    future = df[(df["instrument_class"] == "F") & (df["instrument_id"] == underlying_id)]
    if future.empty:
        symbol = options["underlying"].iloc[0]
        raise InstrumentsUnavailable(f"no definition for underlying future {symbol} ({underlying_id})")
    return future.iloc[0]


def nearest_strikes(strikes: Iterable[float], reference_price: float, n: int) -> list[float]:
    """The `n` strikes closest to `reference_price`, ascending.

    Ties in distance go to the lower strike, so the result is deterministic.
    """
    ranked = sorted(set(strikes), key=lambda k: (abs(k - reference_price), k))
    return sorted(ranked[:n])


@dataclass
class InstrumentSelection:
    """Everything downstream code needs to request and price one study date."""

    trading_date: date
    lead_future: str
    underlying: pd.Series
    series: str
    expiration: pd.Timestamp
    reference_time: pd.Timestamp | None
    reference_price: float
    atm_strike: float
    options: pd.DataFrame

    @property
    def underlying_is_lead(self) -> bool:
        return self.underlying["raw_symbol"] == self.lead_future

    @property
    def strikes(self) -> list[float]:
        return sorted(self.options["strike_price"].unique())

    @property
    def instrument_ids(self) -> list[int]:
        return [int(self.underlying["instrument_id"])] + self.options["instrument_id"].astype(int).tolist()

    @property
    def raw_symbols(self) -> list[str]:
        return [self.underlying["raw_symbol"]] + self.options["raw_symbol"].tolist()

    def request_params(
        self,
        schema: str = "mbp-1",
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> dict:
        """Keyword arguments for ``client.timeseries.get_range``.

        Instruments are requested by ``instrument_id``, which is unambiguous.
        The window defaults to regular trading hours, capped at the expiry.
        """
        start = start or _at(self.trading_date, config.RTH_START)
        end = end or min(_at(self.trading_date, config.RTH_END), self.expiration)
        return {
            "dataset": config.DATASET,
            "schema": schema,
            "stype_in": "instrument_id",
            "symbols": self.instrument_ids,
            "start": start,
            "end": end,
        }

    def to_frame(self) -> pd.DataFrame:
        """One row per selected instrument, underlying first, with metadata."""
        rows = pd.concat(
            [self.underlying.to_frame().T, self.options], ignore_index=True
        )
        rows = rows[[c for c in METADATA_COLUMNS if c in rows.columns]]
        rows.insert(0, "trading_date", pd.Timestamp(self.trading_date))
        rows.insert(1, "role", ["underlying"] + self.options["instrument_class"].map({"C": "call", "P": "put"}).tolist())
        rows["series"] = self.series
        rows["lead_future"] = self.lead_future
        rows["reference_time"] = self.reference_time
        rows["reference_price"] = self.reference_price
        rows["atm_strike"] = self.atm_strike
        return rows.infer_objects()

    def summary(self) -> str:
        lead = "" if self.underlying_is_lead else f" (lead is {self.lead_future})"
        return (
            f"{self.trading_date}: underlying {self.underlying['raw_symbol']}{lead}, "
            f"series {self.series} expiring {self.expiration.tz_convert(config.STUDY_TZ):%H:%M %Z}, "
            f"F={self.reference_price:g}, ATM {self.atm_strike:g}, "
            f"strikes {self.strikes[0]:g}-{self.strikes[-1]:g} "
            f"({len(self.strikes)} strikes, {len(self.options)} options)"
        )


def select_instruments(
    definitions: pd.DataFrame,
    trading_date: date,
    reference_price: float | Callable[[str], float],
    n_strikes: int = config.N_STRIKES,
    reference_time: pd.Timestamp | None = None,
) -> InstrumentSelection:
    """Select the underlying future and near-the-money 0DTE calls and puts.

    `reference_price` is the futures price defining at-the-money, or a
    function that takes the underlying's raw symbol and returns that price.
    Only strikes listed as both a call and a put are eligible.
    """
    options = zero_dte_options(definitions, trading_date)
    future = underlying_future(definitions, options)
    if callable(reference_price):
        reference_price = reference_price(future["raw_symbol"])

    per_strike = options.groupby("strike_price")["instrument_class"].nunique()
    paired = per_strike[per_strike == 2].index
    if paired.empty:
        raise InstrumentsUnavailable(f"no strike has both a call and a put on {trading_date}")
    strikes = nearest_strikes(paired, reference_price, n_strikes)
    atm = nearest_strikes(paired, reference_price, 1)[0]

    chosen = options[options["strike_price"].isin(strikes)]
    chosen = chosen.sort_values(["strike_price", "instrument_class"]).reset_index(drop=True)
    return InstrumentSelection(
        trading_date=trading_date,
        lead_future=lead_future_symbol(trading_date),
        underlying=future,
        series=chosen["asset"].iloc[0],
        expiration=chosen["expiration"].iloc[0],
        reference_time=reference_time,
        reference_price=float(reference_price),
        atm_strike=float(atm),
        options=chosen,
    )


# ---------------------------------------------------------------------------
# Databento access
# ---------------------------------------------------------------------------


def _at(trading_date: date, t: time) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(trading_date, t), tz=config.STUDY_TZ)


def api_key() -> str:
    """Databento key from the environment or the repo's ``.env`` file."""
    names = ("DATABENTO_API_KEY", "DATABENTO_KEY")
    env_file = config.ROOT_DIR / ".env"
    if not any(os.environ.get(n) for n in names) and env_file.exists():
        for line in env_file.read_text().splitlines():
            name, _, value = line.strip().partition("=")
            if name in names:
                os.environ.setdefault(name, value.strip().strip("'\""))
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
    raise RuntimeError("set DATABENTO_API_KEY (or DATABENTO_KEY in .env)")


def get_client():
    import databento as db

    return db.Historical(api_key())


def fetch_definitions(client, trading_date: date, cache_dir: Path | None = None) -> pd.DataFrame:
    """ES futures and ES option definitions published on `trading_date`.

    The raw DBN file is cached, so reruns read the same definitions offline.
    """
    import databento as db

    cache_dir = cache_dir or config.RAW_DIR / "definitions"
    path = cache_dir / f"{config.DATASET}_definition_{trading_date:%Y%m%d}.dbn.zst"
    if not path.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".partial")
        client.timeseries.get_range(
            dataset=config.DATASET,
            schema="definition",
            stype_in="parent",
            symbols=[config.ES_FUTURES_PARENT] + [f"{root}.OPT" for root in config.ES_OPTION_ROOTS],
            start=pd.Timestamp(trading_date, tz="UTC"),
            end=pd.Timestamp(trading_date, tz="UTC") + pd.Timedelta(days=1),
            path=partial,
        )
        partial.rename(path)
    definitions = db.DBNStore.from_file(path).to_df()
    if definitions.empty:
        raise InstrumentsUnavailable(f"no instrument definitions published on {trading_date}")
    return definitions


def fetch_reference_price(client, raw_symbol: str, at: pd.Timestamp) -> float:
    """Close of the last one-minute bar of `raw_symbol` ending at `at`."""
    bars = client.timeseries.get_range(
        dataset=config.DATASET,
        schema="ohlcv-1m",
        stype_in="raw_symbol",
        symbols=[raw_symbol],
        start=at - pd.Timedelta(minutes=15),
        end=at,
    ).to_df()
    if bars.empty:
        raise InstrumentsUnavailable(f"no {raw_symbol} trades in the 15 minutes before {at}")
    return float(bars["close"].iloc[-1])


def select_for_date(
    trading_date: date,
    client=None,
    n_strikes: int = config.N_STRIKES,
    reference_time: time = config.ATM_REFERENCE_TIME,
    cache_dir: Path | None = None,
) -> InstrumentSelection:
    """Download what is needed and select the instruments for one date.

    Raises `InstrumentsUnavailable` when the date has no usable 0DTE series
    (weekends, exchange holidays, dates before daily expiries were listed).
    """
    if trading_date.weekday() >= 5:
        raise InstrumentsUnavailable(f"{trading_date} is a weekend")
    client = client or get_client()
    definitions = fetch_definitions(client, trading_date, cache_dir)
    at = _at(trading_date, reference_time)
    return select_instruments(
        definitions,
        trading_date,
        lambda symbol: fetch_reference_price(client, symbol, at),
        n_strikes=n_strikes,
        reference_time=at,
    )


def select_many(
    trading_dates: Iterable[date], client=None, **kwargs
) -> tuple[list[InstrumentSelection], dict[date, str]]:
    """Selections for every usable date, plus the reason each other date was skipped."""
    client = client or get_client()
    selections, skipped = [], {}
    for trading_date in trading_dates:
        try:
            selections.append(select_for_date(trading_date, client, **kwargs))
        except InstrumentsUnavailable as exc:
            skipped[trading_date] = str(exc)
    return selections, skipped


def save_selections(selections: Iterable[InstrumentSelection], path: Path | None = None) -> Path:
    """Write all selected instruments and their metadata to one parquet file."""
    path = path or config.PROCESSED_DIR / "instruments.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([s.to_frame() for s in selections], ignore_index=True).to_parquet(path, index=False)
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("dates", nargs="+", type=date.fromisoformat, help="trading dates, YYYY-MM-DD")
    parser.add_argument("--n-strikes", type=int, default=config.N_STRIKES)
    parser.add_argument("--out", type=Path, default=None, help="parquet output path")
    args = parser.parse_args(argv)

    selections, skipped = select_many(args.dates, n_strikes=args.n_strikes)
    for selection in selections:
        print(selection.summary())
    for trading_date, reason in skipped.items():
        print(f"{trading_date}: skipped, {reason}")
    if selections:
        print(f"wrote {save_selections(selections, args.out)}")


if __name__ == "__main__":
    main()
