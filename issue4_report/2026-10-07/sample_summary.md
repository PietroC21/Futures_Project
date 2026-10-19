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
