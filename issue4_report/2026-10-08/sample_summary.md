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
