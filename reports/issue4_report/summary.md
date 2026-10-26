# Issue 4 — ES Futures Price-Move Events

## Overview

This analysis identifies ES futures midpoint changes that serve as triggers for the 0DTE option stale-quote study. It uses Databento CME `GLBX.MDP3` `mbp-1` data for October 5–9, 2026. Each event retains the exchange timestamp (`t0`), futures prices immediately before and after the move, direction, and signed size in index points and ES ticks.

ES has a 0.25-point minimum tick. Since the midpoint can change when only one side of the book moves, midpoint changes smaller than one tick are kept as a separate **sub-tick** category. The main economic analysis can focus on moves of at least one tick without losing the broader event counts.

## Event definition

The detector reconstructs the top of book from MBP-1 updates and uses `ts_event` for event timing. Events are classified as **sub-tick** (<1 ES tick), **single-tick** (1 tick), or **multi-tick** (>1 tick), using absolute move size for classification and retaining the direction separately.

The baseline groups rapid price changes using a 250,000 ns cluster-gap setting, with reversal/cluster filtering to avoid treating brief back-and-forth updates as separate persistent moves. The exported primary event table retains one midpoint-changing update from a selected single-move cluster. This is a retrospective selection rule, so the baseline should not be interpreted as a trading signal known at `t0`.

For comparison, an **unfiltered** specification sets the cluster gap to 0 ns. Both specifications are produced from the same futures records.

Two observation-window endpoints are recorded: the next **raw midpoint change** (`observation_end`) and the next **raw move of at least one ES tick** (`observation_end_tick`), subject to the configured observation horizon and data-continuity boundaries. The second window is a sensitivity measure, not a claim that a quote remains stale through intervening smaller moves.

## Five-day results

| Date | Baseline events | Unfiltered events |
|---|---:|---:|
| Oct 5 | 46,683 | 158,413 |
| Oct 6 | 35,990 | 141,898 |
| Oct 7 | 61,741 | 217,693 |
| Oct 8 | 113,791 | 343,533 |
| Oct 9 | 44,280 | 150,865 |
| **Total** | **302,485** | **1,012,402** |

The source covers **21,310,348 MBP-1 records** across five days.

| Event size | Baseline | Unfiltered |
|---|---:|---:|
| Sub-tick (<1 tick) | 289,816 | 983,038 |
| Single-tick (1 tick) | 12,241 | 28,684 |
| Multi-tick (>1 tick) | 428 | 680 |
| **Total** | **302,485** | **1,012,402** |

Under baseline filtering, **12,669 events (4.19%)** are at least one tick. Event counts are sensitive to the clustering rule, so results from the stale-quote analysis should identify which specification supplies the denominator.

## Observation windows

| Endpoint / reason | Baseline share ending at next qualifying move | Unfiltered share ending at next qualifying move |
|---|---:|---:|
| Next raw midpoint change | 60.16% | 76.28% |
| Next raw move ≥1 tick | 4.30% | 9.26% |

These percentages count window endpoints by their recorded reason; they are not option reaction or stale-quote rates. A substantial share of windows is cut short under the more conservative raw-midpoint definition. Analyses of option latency or stale duration need to account for censoring rather than treating these endpoints as observed quote reactions.

## Interpretation and limits

The results establish a reproducible event sample and show that event selection and observation-window definitions materially affect the available sample. The filtered and unfiltered tables let the downstream study test whether estimated option opportunities are sensitive to retrospective reversal filtering. The ≥1-tick sample is useful for the primary economic question, while sub-tick changes remain available for diagnostics.

This analysis detects futures events only. It does **not** measure option reaction times, stale-quote profitability, or cross-engine clock synchronization. Those conclusions require the option quotes and downstream pricing/measurement steps.

## Reproduction

From the repository root, with the Issue 3 cache present at `data/raw/mbp-1/YYYYMMDD/`:

```bash
python -m pytest tests/test_events.py -v
python scripts/detect_events.py --dates 2026-10-05 2026-10-06 2026-10-07 2026-10-08 2026-10-09
```

The generated event tables are stored under `data/processed/events/YYYYMMDD/` and are not committed to Git. Small summaries are written to `issue4_report/`, including `event_counts.csv`. The event definitions and clustering assumptions are documented in `docs/event_definition.md`.
