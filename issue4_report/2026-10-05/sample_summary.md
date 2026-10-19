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
