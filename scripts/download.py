"""Download the configured ES futures and 0DTE option data into data/raw/.

    python scripts/download.py               # config.STUDY_DATES, asks before paying
    python scripts/download.py --dry-run     # only show the cost estimate
    python scripts/download.py --dates 2026-10-07 --n-strikes 6 --schemas mbp-1 mbo
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stale_quotes.download import main  # noqa: E402

if __name__ == "__main__":
    main()
