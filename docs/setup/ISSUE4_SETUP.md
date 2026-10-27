# Issue 4 — integrate into the team repository

Copy the relative paths `src/stale_quotes/events.py`, `src/stale_quotes/event_runner.py`, `scripts/detect_events.py`, `tests/test_events.py`, `notebooks/issue4_engine.ipynb`, `docs/event_definition.md`, and `issue4_report/summary.md` into the team repository. Merge the **added Issue 4 constants and five-day STUDY_DATES** from `src/stale_quotes/config.py` rather than replacing a newer config wholesale. Keep the existing project files and requirements.

From the repository root:

```bash
python -m pip install -r requirements.txt
python -m pip install pyarrow
python -m pytest -q
python scripts/detect_events.py --dates 2026-10-05 2026-10-06 2026-10-07 2026-10-08 2026-10-09
```

Run `notebooks/issue4_engine.ipynb` to summarize the results. Do not upload `data/raw`, `data/processed` or large Parquet outputs. The five-day cache remains local.
