
"""Study-wide settings for the ES 0DTE stale-quote project."""

from datetime import date, time
from pathlib import Path


# ---------------------------------------------------------------------
# Dataset and study dates
# ---------------------------------------------------------------------

DATASET = "GLBX.MDP3"

# Full trading week: Monday, October 5 through Friday, October 9, 2026.
# Dates can also be overridden using scripts/download.py --dates.
STUDY_DATES = [date(2026, 10, d) for d in range(5, 10)]

# MBP-1 includes top-of-book updates and trades.
SCHEMAS = ["mbp-1"]


# ---------------------------------------------------------------------
# Trading sessions and time zones
# ---------------------------------------------------------------------

EXCHANGE_TZ = "America/Chicago"
STUDY_TZ = "America/New_York"

# Reference time used to select near-the-money option strikes.
ATM_REFERENCE_TIME = time(9, 30)

# Regular trading hours (New York time).
RTH_START = time(9, 30)
RTH_END = time(16, 0)


# ---------------------------------------------------------------------
# Futures and options instruments
# ---------------------------------------------------------------------

# ES futures parent symbol.
ES_FUTURES_PARENT = "ES.FUT"

# Option roots covering quarterly, weekly, and daily ES expirations.
ES_OPTION_ROOTS = (
    ["ES", "EW", "EW1", "EW2", "EW3", "EW4"]
    + [f"E{week}{day}" for day in "ABCD" for week in range(1, 6)]
)

# Number of strikes selected around ATM.
N_STRIKES = 10


# ---------------------------------------------------------------------
# Issue #4: Futures event detection
# ---------------------------------------------------------------------

# ES minimum price increment, in index points.
ES_FUTURES_TICK_SIZE = 0.25

# Maximum gap between nearby midpoint changes for clustering.
# 250 microseconds = 250,000 nanoseconds.
CLUSTER_GAP_NS = 250_000

# Maximum allowed span of a cluster.
# 2 milliseconds = 2,000,000 nanoseconds.
MAX_CLUSTER_SPAN_NS = 2_000_000

# Maximum observation window following a futures event.
# 10 milliseconds = 10,000,000 nanoseconds.
REACTION_WINDOW_NS = 10_000_000

# Maximum tolerated gap between consecutive quote observations.
# 1 second = 1,000,000,000 nanoseconds.
MAX_QUOTE_GAP_NS = 1_000_000_000


# ---------------------------------------------------------------------
# Issue #6: Stale-quote detection
# ---------------------------------------------------------------------

# ES weekly/0DTE option tick size, in premium points.
# Verified against the 2026-10-07 mbp-1 sample.
OPTION_TICK = 0.05

# Assumed all-in taker fee per contract (USD), excluding brokerage.
# Maker rebates and volume/membership tiers are not modeled.
FEE_PER_CONTRACT_USD = 1.00

# Include the gamma term when updating option fair value.
USE_GAMMA = True

# Longest stale window when an event has no observation_end (10 ms).
MAX_WINDOW_NS = 10_000_000


# ---------------------------------------------------------------------
# Local paths
# ---------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[2]

RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

# Generated event tables are kept outside Git.
EVENTS_DIR = PROCESSED_DIR / "events"

# Small summary files and documentation for Issue #4.
ISSUE4_REPORT_DIR = ROOT_DIR / "issue4_report"
