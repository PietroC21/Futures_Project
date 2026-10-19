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
