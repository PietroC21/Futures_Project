# Issue 4: Detect and classify ES futures price-move events

## What this adds

A self-contained notebook reads the Issue 3 futures cache and exports reproducible
price-move events for the stale-quote study. It keeps candidates and cluster
exclusions so we can review what the filter removes.

Run type: **real cached market data**.
Offline tests: **68 passed, 0 failed, 0 skipped**.
The saved primary Parquet table also passed exact timestamp and signed-tick
round-trip checks. Selected primary event times are unique, move sizes agree
with prices, and their observation windows do not overlap.

## Event definition

We use valid best bid/offer states from `mbp-1`. Trade records are ignored because
their BBO is pre-trade. Size-only changes do not trigger an event. For multiple
quote records with one exchange timestamp, we keep the final state before
calculating changes. This is a timestamp-level state definition: moves reversed
within that same timestamp are not separately observable in this table.
Invalid states, resets and quote gaps over 1,000,000,000 ns break continuity.
We do not compare prices across those breaks or between different futures.
The future is taken from `futures.json`, rather than re-selected from a roll rule.

The primary price is `(bid + ask) / 2`. One ES tick is 0.25 index
points. We retain signed point/tick changes, classify up/down and distinguish
sub-tick, single-tick and multi-tick moves. A native single update can be multi-tick.
The primary table contains one midpoint-changing update per selected cluster;
`t0` is that update's exchange `ts_event`. All times are UTC. Epoch timestamps
and durations are stored in integer ns, without conversion to microseconds.
Nanosecond representation alone does not validate cross-contract clock alignment.

## Clustering, bouncing and overlap

Adjacent BBO price changes join a cluster when their gap is at most
250,000 ns and the total span from the first member is at most
2,000,000 ns. Round trips and partial reversals are excluded.
Clusters linked across a span-cap split are excluded, so the cap does not create
artificial independent moves. Quiet context is required on both sides.

`clustered_events.parquet` stores selected net paths as a secondary specification;
its `t0` is the final constituent update, never the first one. `confirmed_at` is
cluster end plus the gap. Filtering uses later quotes and is retrospective.
It should not be described as an immediately available trading signal.

The observation window is `[t0, observation_end)`. It ends at the next raw
midpoint move, the 10,000,000 ns horizon or the segment boundary,
whichever occurs first. A later move ends the window even if that move is
filtered out. A truncated window is recorded, not treated as an option response.

## Sample: 2026-10-05

ESZ6, instrument ID 10252; requested interval 2026-10-05 09:30:00-04:00 to 2026-10-05 16:00:00-04:00.

| Measure | Count |
| --- | ---: |
| Input records | 3,646,277 |
| Trade records ignored | 255,212 |
| Same-timestamp quote records collapsed | 27 |
| Invalid final quote states | 0 |
| Continuity segments | 89 |
| BBO price-change candidates | 158,413 |
| Midpoint-changing candidates | 158,413 |
| Clusters before filtering | 84,620 |
| Selected paths, including single updates | 67,544 |
| Primary single-update events | 46,683 |
| Primary events with truncated horizons | 27,360 |

Observed final quote-state timestamps: 2026-10-05 13:29:59.999951635+00:00 to 2026-10-05 19:59:59.999851975+00:00.
The median primary observation window is 3520548 ns. This is an available
futures observation window, not an option reaction-time estimate.

### Direction and move size

| sample | direction | size_class | events |
| --- | --- | --- | --- |
| 2026-10-05 | down | multi_tick | 47 |
| 2026-10-05 | down | single_tick | 1168 |
| 2026-10-05 | down | sub_tick | 22170 |
| 2026-10-05 | up | multi_tick | 54 |
| 2026-10-05 | up | single_tick | 1367 |
| 2026-10-05 | up | sub_tick | 21877 |

Move ticks are signed: negative means down. The size label uses absolute ticks.
Midpoints can move by half a futures tick.

### Excluded clusters

| reason | clusters |
| --- | --- |
| reversal | 17075 |
| round_trip | 7215 |
| span_cap_split | 14 |

Reasons can overlap; their counts should not be added to obtain a total.
The primary table also omits selected paths with more than one midpoint move.

### Clustering-gap sensitivity

| sample | cluster_gap_ns | clustered_events | single_update_events | round_trip_clusters | reversal_clusters | sub_tick_events | single_tick_events | multi_tick_events | truncated_events | median_observation_duration_ns |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-05 | 0 | 158413 | 158413 | 0 | 0 | 152520 | 5760 | 133 | 119946 | 273226.0 |
| 2026-10-05 | 100000 | 99709 | 84471 | 9195 | 15627 | 80761 | 3602 | 108 | 56173 | 557180.0 |
| 2026-10-05 | 250000 | 67544 | 46683 | 7215 | 17075 | 44047 | 2535 | 101 | 27360 | 3520548.0 |
| 2026-10-05 | 500000 | 41465 | 17831 | 9430 | 18361 | 16148 | 1594 | 89 | 6510 | 10000000.0 |

Other parameters and the input sample are held fixed. The zero-gap case still
uses the same final-state, validity and boundary rules. These samples differ in
composition; a higher event count alone does not establish a better filter.

### Generated tables

| file | rows | MiB |
| --- | --- | --- |
| 2026-10-05/candidates.parquet | 158413 | 3.4 |
| 2026-10-05/clusters.parquet | 84620 | 8.262 |
| 2026-10-05/clustered_events.parquet | 67544 | 7.085 |
| 2026-10-05/events.parquet | 46683 | 4.851 |

The Parquet tables are local analysis outputs. Running the notebook regenerates
them; they are not required attachments to this PR.


## Sample: 2026-10-06

ESZ6, instrument ID 10252; requested interval 2026-10-06 09:30:00-04:00 to 2026-10-06 16:00:00-04:00.

| Measure | Count |
| --- | ---: |
| Input records | 3,669,065 |
| Trade records ignored | 243,713 |
| Same-timestamp quote records collapsed | 35 |
| Invalid final quote states | 0 |
| Continuity segments | 77 |
| BBO price-change candidates | 141,898 |
| Midpoint-changing candidates | 141,898 |
| Clusters before filtering | 71,466 |
| Selected paths, including single updates | 55,656 |
| Primary single-update events | 35,990 |
| Primary events with truncated horizons | 22,129 |

Observed final quote-state timestamps: 2026-10-06 13:30:00.000012823+00:00 to 2026-10-06 19:59:59.999263543+00:00.
The median primary observation window is 1422082 ns. This is an available
futures observation window, not an option reaction-time estimate.

### Direction and move size

| sample | direction | size_class | events |
| --- | --- | --- | --- |
| 2026-10-06 | down | multi_tick | 26 |
| 2026-10-06 | down | single_tick | 1099 |
| 2026-10-06 | down | sub_tick | 16325 |
| 2026-10-06 | up | multi_tick | 18 |
| 2026-10-06 | up | single_tick | 1113 |
| 2026-10-06 | up | sub_tick | 17409 |

Move ticks are signed: negative means down. The size label uses absolute ticks.
Midpoints can move by half a futures tick.

### Excluded clusters

| reason | clusters |
| --- | --- |
| reversal | 15807 |
| round_trip | 6433 |
| span_cap_split | 16 |
| missing_left_context | 1 |

Reasons can overlap; their counts should not be added to obtain a total.
The primary table also omits selected paths with more than one midpoint move.

### Clustering-gap sensitivity

| sample | cluster_gap_ns | clustered_events | single_update_events | round_trip_clusters | reversal_clusters | sub_tick_events | single_tick_events | multi_tick_events | truncated_events | median_observation_duration_ns |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-06 | 0 | 141898 | 141898 | 0 | 0 | 136640 | 5195 | 63 | 109784 | 252395.0 |
| 2026-10-06 | 100000 | 85021 | 70055 | 8567 | 14879 | 66745 | 3261 | 49 | 48218 | 430446.0 |
| 2026-10-06 | 250000 | 55656 | 35990 | 6433 | 15807 | 33734 | 2212 | 44 | 22129 | 1422082.0 |
| 2026-10-06 | 500000 | 32722 | 11897 | 8705 | 16791 | 10441 | 1413 | 43 | 4482 | 10000000.0 |

Other parameters and the input sample are held fixed. The zero-gap case still
uses the same final-state, validity and boundary rules. These samples differ in
composition; a higher event count alone does not establish a better filter.

### Generated tables

| file | rows | MiB |
| --- | --- | --- |
| 2026-10-06/candidates.parquet | 141898 | 2.896 |
| 2026-10-06/clusters.parquet | 71466 | 7.34 |
| 2026-10-06/clustered_events.parquet | 55656 | 5.902 |
| 2026-10-06/events.parquet | 35990 | 3.783 |

The Parquet tables are local analysis outputs. Running the notebook regenerates
them; they are not required attachments to this PR.


## Sample: 2026-10-07

ESZ6, instrument ID 10252; requested interval 2026-10-07 09:30:00-04:00 to 2026-10-07 16:00:00-04:00.

| Measure | Count |
| --- | ---: |
| Input records | 4,547,488 |
| Trade records ignored | 273,162 |
| Same-timestamp quote records collapsed | 19 |
| Invalid final quote states | 0 |
| Continuity segments | 44 |
| BBO price-change candidates | 217,693 |
| Midpoint-changing candidates | 217,693 |
| Clusters before filtering | 113,722 |
| Selected paths, including single updates | 89,318 |
| Primary single-update events | 61,741 |
| Primary events with truncated horizons | 36,650 |

Observed final quote-state timestamps: 2026-10-07 13:30:00.000015857+00:00 to 2026-10-07 19:59:59.999837823+00:00.
The median primary observation window is 3244946 ns. This is an available
futures observation window, not an option reaction-time estimate.

### Direction and move size

| sample | direction | size_class | events |
| --- | --- | --- | --- |
| 2026-10-07 | down | multi_tick | 30 |
| 2026-10-07 | down | single_tick | 1120 |
| 2026-10-07 | down | sub_tick | 29820 |
| 2026-10-07 | up | multi_tick | 40 |
| 2026-10-07 | up | single_tick | 1012 |
| 2026-10-07 | up | sub_tick | 29719 |

Move ticks are signed: negative means down. The size label uses absolute ticks.
Midpoints can move by half a futures tick.

### Excluded clusters

| reason | clusters |
| --- | --- |
| reversal | 24401 |
| round_trip | 10411 |
| span_cap_split | 33 |
| missing_left_context | 1 |

Reasons can overlap; their counts should not be added to obtain a total.
The primary table also omits selected paths with more than one midpoint move.

### Clustering-gap sensitivity

| sample | cluster_gap_ns | clustered_events | single_update_events | round_trip_clusters | reversal_clusters | sub_tick_events | single_tick_events | multi_tick_events | truncated_events | median_observation_duration_ns |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-07 | 0 | 217693 | 217693 | 0 | 0 | 211844 | 5729 | 120 | 167130 | 264282.0 |
| 2026-10-07 | 100000 | 137705 | 117620 | 12500 | 21384 | 114260 | 3285 | 75 | 80237 | 504410.0 |
| 2026-10-07 | 250000 | 89318 | 61741 | 10411 | 24401 | 59539 | 2132 | 70 | 36650 | 3244946.0 |
| 2026-10-07 | 500000 | 54641 | 25384 | 13705 | 26268 | 24073 | 1253 | 58 | 9332 | 10000000.0 |

Other parameters and the input sample are held fixed. The zero-gap case still
uses the same final-state, validity and boundary rules. These samples differ in
composition; a higher event count alone does not establish a better filter.

### Generated tables

| file | rows | MiB |
| --- | --- | --- |
| 2026-10-07/candidates.parquet | 217693 | 3.919 |
| 2026-10-07/clusters.parquet | 113722 | 11.274 |
| 2026-10-07/clustered_events.parquet | 89318 | 9.43 |
| 2026-10-07/events.parquet | 61741 | 6.383 |

The Parquet tables are local analysis outputs. Running the notebook regenerates
them; they are not required attachments to this PR.


## Sample: 2026-10-08

ESZ6, instrument ID 10252; requested interval 2026-10-08 09:30:00-04:00 to 2026-10-08 16:00:00-04:00.

| Measure | Count |
| --- | ---: |
| Input records | 6,148,295 |
| Trade records ignored | 361,053 |
| Same-timestamp quote records collapsed | 66 |
| Invalid final quote states | 0 |
| Continuity segments | 8 |
| BBO price-change candidates | 343,533 |
| Midpoint-changing candidates | 343,533 |
| Clusters before filtering | 192,992 |
| Selected paths, including single updates | 155,551 |
| Primary single-update events | 113,791 |
| Primary events with truncated horizons | 70,074 |

Observed final quote-state timestamps: 2026-10-08 13:30:00.000014289+00:00 to 2026-10-08 19:59:59.999747485+00:00.
The median primary observation window is 3863984 ns. This is an available
futures observation window, not an option reaction-time estimate.

### Direction and move size

| sample | direction | size_class | events |
| --- | --- | --- | --- |
| 2026-10-08 | down | multi_tick | 85 |
| 2026-10-08 | down | single_tick | 1789 |
| 2026-10-08 | down | sub_tick | 54891 |
| 2026-10-08 | up | multi_tick | 76 |
| 2026-10-08 | up | single_tick | 1631 |
| 2026-10-08 | up | sub_tick | 55319 |

Move ticks are signed: negative means down. The size label uses absolute ticks.
Midpoints can move by half a futures tick.

### Excluded clusters

| reason | clusters |
| --- | --- |
| reversal | 37439 |
| round_trip | 16936 |
| span_cap_split | 20 |
| missing_left_context | 1 |

Reasons can overlap; their counts should not be added to obtain a total.
The primary table also omits selected paths with more than one midpoint move.

### Clustering-gap sensitivity

| sample | cluster_gap_ns | clustered_events | single_update_events | round_trip_clusters | reversal_clusters | sub_tick_events | single_tick_events | multi_tick_events | truncated_events | median_observation_duration_ns |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-08 | 0 | 343533 | 343533 | 0 | 0 | 335792 | 7485 | 256 | 261328 | 293190.0 |
| 2026-10-08 | 100000 | 231843 | 204153 | 18806 | 30884 | 199203 | 4767 | 183 | 140588 | 662370.0 |
| 2026-10-08 | 250000 | 155551 | 113791 | 16936 | 37439 | 110210 | 3420 | 161 | 70074 | 3863984.0 |
| 2026-10-08 | 500000 | 96978 | 49871 | 22557 | 42585 | 47591 | 2150 | 130 | 21585 | 10000000.0 |

Other parameters and the input sample are held fixed. The zero-gap case still
uses the same final-state, validity and boundary rules. These samples differ in
composition; a higher event count alone does not establish a better filter.

### Generated tables

| file | rows | MiB |
| --- | --- | --- |
| 2026-10-08/candidates.parquet | 343533 | 6.098 |
| 2026-10-08/clusters.parquet | 192992 | 18.153 |
| 2026-10-08/clustered_events.parquet | 155551 | 15.538 |
| 2026-10-08/events.parquet | 113791 | 9.601 |

The Parquet tables are local analysis outputs. Running the notebook regenerates
them; they are not required attachments to this PR.


## Sample: 2026-10-09

ESZ6, instrument ID 10252; requested interval 2026-10-09 09:30:00-04:00 to 2026-10-09 16:00:00-04:00.

| Measure | Count |
| --- | ---: |
| Input records | 3,299,223 |
| Trade records ignored | 214,265 |
| Same-timestamp quote records collapsed | 47 |
| Invalid final quote states | 0 |
| Continuity segments | 121 |
| BBO price-change candidates | 150,865 |
| Midpoint-changing candidates | 150,865 |
| Clusters before filtering | 80,291 |
| Selected paths, including single updates | 64,260 |
| Primary single-update events | 44,280 |
| Primary events with truncated horizons | 25,769 |

Observed final quote-state timestamps: 2026-10-09 13:30:00.000012951+00:00 to 2026-10-09 19:59:59.999852525+00:00.
The median primary observation window is 3662065 ns. This is an available
futures observation window, not an option reaction-time estimate.

### Direction and move size

| sample | direction | size_class | events |
| --- | --- | --- | --- |
| 2026-10-09 | down | multi_tick | 29 |
| 2026-10-09 | down | single_tick | 894 |
| 2026-10-09 | down | sub_tick | 20527 |
| 2026-10-09 | up | multi_tick | 23 |
| 2026-10-09 | up | single_tick | 1048 |
| 2026-10-09 | up | sub_tick | 21759 |

Move ticks are signed: negative means down. The size label uses absolute ticks.
Midpoints can move by half a futures tick.

### Excluded clusters

| reason | clusters |
| --- | --- |
| reversal | 16028 |
| round_trip | 6717 |
| span_cap_split | 19 |

Reasons can overlap; their counts should not be added to obtain a total.
The primary table also omits selected paths with more than one midpoint move.

### Clustering-gap sensitivity

| sample | cluster_gap_ns | clustered_events | single_update_events | round_trip_clusters | reversal_clusters | sub_tick_events | single_tick_events | multi_tick_events | truncated_events | median_observation_duration_ns |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-09 | 0 | 150865 | 150865 | 0 | 0 | 146242 | 4515 | 108 | 114053 | 271786.0 |
| 2026-10-09 | 100000 | 96697 | 82676 | 8335 | 14338 | 79806 | 2812 | 58 | 55359 | 527391.0 |
| 2026-10-09 | 250000 | 64260 | 44280 | 6717 | 16028 | 42286 | 1942 | 52 | 25769 | 3662065.0 |
| 2026-10-09 | 500000 | 39445 | 17946 | 9394 | 17814 | 16702 | 1198 | 46 | 6435 | 10000000.0 |

Other parameters and the input sample are held fixed. The zero-gap case still
uses the same final-state, validity and boundary rules. These samples differ in
composition; a higher event count alone does not establish a better filter.

### Generated tables

| file | rows | MiB |
| --- | --- | --- |
| 2026-10-09/candidates.parquet | 150865 | 2.996 |
| 2026-10-09/clusters.parquet | 80291 | 8.371 |
| 2026-10-09/clustered_events.parquet | 64260 | 6.761 |
| 2026-10-09/events.parquet | 44280 | 4.605 |

The Parquet tables are local analysis outputs. Running the notebook regenerates
them; they are not required attachments to this PR.

## Validation and scope

The offline suite covers direction/tick classification, half ticks, same-timestamp
updates, invalid states, bounded clusters, bouncing, overlap, exact ns boundaries,
manifest checks and compressed DBN decoding. The full cached sample was processed
with the settings above. Input checksums, parameters and dependency versions are
saved in each date's `diagnostics.json`.

The counts above cover five trading days, October 5 to 9, 2026. More dates and different filter thresholds remain robustness checks.
The filtered events are a selected population, not all futures moves. This step
does not establish timestamp comparability with options or estimate stale-quote
profitability. Those questions remain for the downstream analysis.

## Reproduce and review

Place `issue4_engine.ipynb` in the project root (or `notebooks/`). Keep the Issue 3
cache at `data/raw/mbp-1/YYYYMMDD/futures.dbn.zst` with `futures.json`. Use Python
3.11+ and Run All with `RUN_MODE = 'real'`. Missing dependencies are installed in
the current kernel. The notebook makes no data-download requests. Outputs go to
`issue4_report/`; date folders are regenerated for the dates selected in the run.

Submit the executed notebook and this Markdown report. The large Parquet files
can remain local for subsequent analysis. CSV summaries and `sample_summary.md`
repeat the tables above and need not also be included in the PR. Raw DBN files
should stay out of Git. No API key is used or saved.
