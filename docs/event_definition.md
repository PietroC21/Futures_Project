# ES futures event definition

We use the outright future selected by Issue 2 and recorded in the Issue 3 `futures.json` manifest. MBP-1 is read without requesting data from Databento again. `ts_event` is the exchange event timestamp and is retained at nanosecond precision. Trade (`action=T`) messages are not interpreted as an updated book state. Same-timestamp book updates are collapsed to their final state.

A raw candidate is a BBO price update; a price event is a change in `(best_bid + best_ask) / 2`. ES has a 0.25-point tick, so one-sided updates can generate half-tick midpoint changes. `move_points` and signed `move_ticks` are calculated from before/after midpoint states. We distinguish `sub_tick`, `single_tick`, and `multi_tick`. Primary economic summaries should separately report moves of at least one tick.

## Filtering

The default run uses `cluster_gap_ns=250000` and `max_cluster_span_ns=2000000`. Nearby updates are grouped within a bounded interval. Round trips and clusters with bidirectional moves are excluded. The primary table keeps clusters with one midpoint-changing update, timestamped at that **actual update**, not the cluster end. This selection is retrospective: persistence cannot be known to a taker at `t0`. The second `events_unfiltered.parquet` series uses `cluster_gap_ns=0` as a check against this look-ahead selection.

## Observation windows

The original `observation_end` is the earliest of (1) the next raw midpoint change, (2) the 10 ms horizon, or (3) the continuity-segment boundary. The alternative `observation_end_tick` replaces the next-raw-move bound with the next raw midpoint move of absolute size **at least one ES tick**. Both use unfiltered raw events for their bounds, not only selected events. A smaller move may still change an option's fair value; the tick-bound window is **only a robustness horizon**, not proof of additional actionable stale time.

## Outputs

`data/processed/events/YYYYMMDD/events.parquet` and `events_unfiltered.parquet` store the full tables. These are regenerated locally and stay out of Git. Small CSV summaries are written to `issue4_report/`. Run `pytest tests/test_events.py` and `python scripts/detect_events.py`. No API key is needed with an existing Issue 3 cache.
