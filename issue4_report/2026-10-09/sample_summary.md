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
