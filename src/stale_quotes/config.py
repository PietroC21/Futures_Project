"""Study-wide settings: dataset, products, strike range and paths."""

from datetime import time
from pathlib import Path

DATASET = "GLBX.MDP3"

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

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
