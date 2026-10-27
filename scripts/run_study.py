"""Run the study on cached data and write results/ (issue #7).

    python scripts/download.py                       # once, caches data/raw/
    python scripts/run_study.py                      # config.STUDY_DATES
    python scripts/run_study.py --dates 2026-10-07 \
    --events "data/processed/events/{date}/events.parquet"

Per-date stale-quote and latency tables are cached in data/processed/{stale,latency}/;
pass --recompute to rebuild them. Tables go to results/tables/, figures to results/figures/.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stale_quotes.metrics import main  # noqa: E402

if __name__ == "__main__":
    main()
