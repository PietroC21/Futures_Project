"""Study-wide settings: dataset, products, strike range and paths."""

from datetime import date, time
from pathlib import Path

DATASET = "GLBX.MDP3"

# Sample of trading days (inside the window where `mbo` is also licensed).
# Override without editing code: `python scripts/download.py --dates ...`.
STUDY_DATES = [date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 9)]
# Market-data schemas to download. `mbp-1` carries both BBO updates and trades.
SCHEMAS = ["mbp-1"]

# Exchange and study time zones. CME products are defined in Chicago time;
# the cash session (and our reference times) are quoted in New York time.
EXCHANGE_TZ = "America/Chicago"
STUDY_TZ = "America/New_York"

# ES futures parent symbol (outrights and calendar spreads).
ES_FUTURES_PARENT = "ES.FUT"

# Option product roots that settle into ES futures. `ES.OPT` only covers the
# AM-settled quarterly options; every weekly/daily expiry has its own root:
#   EW          end-of-month (PM)
#   EW1..EW4    Friday weeklies, week 1-4 of the month (EW3 = 3rd Friday, PM)
#   E{1-5}{A-D} Monday (A), Tuesday (B), Wednesday (C), Thursday (D) weeklies
ES_OPTION_ROOTS = (
    ["ES", "EW", "EW1", "EW2", "EW3", "EW4"]
    + [f"E{week}{day}" for day in "ABCD" for week in range(1, 6)]
)

# Near-the-money strike selection.
N_STRIKES = 10
# Time at which the futures price is sampled to define at-the-money.
ATM_REFERENCE_TIME = time(9, 30)  # STUDY_TZ, cash open
# Regular trading hours used as the default market-data request window.
RTH_START = time(9, 30)  # STUDY_TZ
RTH_END = time(16, 0)  # STUDY_TZ

# Stale-quote test (staleness.py). A quote is an opportunity only if it beats
# fair value by more than COST = OPTION_TICK / 2 + FEE_PER_CONTRACT_USD / multiplier.
#
# Tick: ES weekly/0DTE options quote in 0.05 increments at every premium level
# (checked on 2026-10-07 mbp-1 data; definitions only give tick_rule 17).
OPTION_TICK = 0.05
# Fees: one flat, all-in taker fee per contract (exchange + clearing; no
# brokerage). Taking a stale quote always crosses the spread, so only the taker
# side applies; maker rebates and CME volume/membership tiers are NOT modelled.
# $1.00 is a round, conservative assumption to check against the CME fee schedule.
FEE_PER_CONTRACT_USD = 1.00
# Fair value adds the gamma term (PR #14 shows delta-only is off by more than
# half a tick for 8+ tick moves late in the day).
USE_GAMMA = True
# Longest stale window tracked when events carry no `observation_end`.
MAX_WINDOW_NS = 10_000_000  # 10 ms, the issue #4 observation horizon

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
