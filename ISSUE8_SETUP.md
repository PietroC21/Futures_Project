# Before running Issue 8

1. Merge the **new** module, CLI, test and notebook files from this folder into the team's repo root.
2. Install the team's requirements plus `pyarrow` and run `python -m pytest tests/test_mbo_analysis.py -v`.
3. Make sure the 2026-10-07 Issue #6 output exists: `data/processed/stale/20261007.parquet`.
4. Download 2026-10-07 option `mbo` (estimate cost first), along with its manifest. Download an MBO interval that supports actual book reconstruction/snapshot; an RTH-only download may be insufficient.
5. Ensure `data/raw/mbp-1/20261007/options.dbn.zst` exists for post-fill markouts.
6. Run the CLI shown in README from the repository root.
7. Inspect `resolution_summary`, `data_quality` and markout tables; if most pairs are `incomplete_initial_book`, fix the MBO warmup/snapshot before claiming resolution rates.
8. Run `notebooks/issue8_mbo_analysis.ipynb`. Commit code, tests and small report files; keep raw DBN and large Parquet in ignored `data/`.

`MISSING_INPUTS/` contains empty filenames ONLY to show which generated inputs are not available in the files uploaded to this conversation. Never copy these empty placeholders into the live cache.

For a smaller first run, use the sample downloader (00:00 UTC through 10:30 ET for four options) and restrict Issue 6 pairs to 10:00–10:30 ET using `--start-et 10:00 --end-et 10:30`. Requests still require cost confirmation. If a prior MBO cache already occupies the same filename, the downloader refuses to replace it; inspect its manifest and rename it only if you intend to replace that sample.
