# Issue 1: Data availability and timestamp assessment

## Sample and access
Dataset: GLBX.MDP3; schema: mbp-1. Sample: 2026-10-08, 2026-10-08 14:00:00+00:00 to 2026-10-08 14:10:00+00:00.
Future: ESZ6; options: E2DV6 P7830, E2DV6 C7830, E2DV6 P7835, E2DV6 C7835, E2DV6 C7825, E2DV6 P7825.
Retrieved rows: 166,088 futures and 264,414 options.
Run this notebook with the API key in DATABENTO_API_KEY or the hidden prompt. Dependencies and request metadata are saved alongside this report. Local cache entries reuse identical requests.

### Current-key historical metadata
```json
{
  "start": "2010-06-06T00:00:00.000000000Z",
  "end": "2026-10-11T13:08:20.817591000Z",
  "schema": {
    "mbo": {
      "start": "2017-05-21T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "mbp-1": {
      "start": "2010-06-06T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "mbp-10": {
      "start": "2010-06-06T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "tbbo": {
      "start": "2010-06-06T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "trades": {
      "start": "2010-06-06T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "bbo-1s": {
      "start": "2010-06-06T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "bbo-1m": {
      "start": "2010-06-06T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "ohlcv-1s": {
      "start": "2010-06-06T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "ohlcv-1m": {
      "start": "2010-06-06T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "ohlcv-1h": {
      "start": "2010-06-06T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "ohlcv-1d": {
      "start": "2010-06-06T00:00:00.000000000Z",
      "end": "2026-10-11T00:00:00.000000000Z"
    },
    "definition": {
      "start": "2010-06-06T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "statistics": {
      "start": "2010-06-06T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "status": {
      "start": "2010-06-06T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "cmbp-1": {
      "start": "2017-05-21T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "cbbo-1s": {
      "start": "2017-05-21T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    },
    "cbbo-1m": {
      "start": "2017-05-21T00:00:00.000000000Z",
      "end": "2026-10-11T13:08:20.817591000Z"
    }
  }
}
```
This is the range returned for the current key. Successful requests verify access only for this sample. Full course-license coverage and free access across the entire range have not been independently established.

### Contracts and common coverage
The future is selected by nearest unexpired calendar maturity. Options are linked through instrument definitions, including daily/weekly roots; expiration must fall on the sample's Chicago date and after the sample window.
```text
     symbol  instrument_id  records              common_start                common_end  positive_overlap
E2DV6 P7830       42646140    50987 2026-10-08 14:00:00+00:00 2026-10-08 14:10:00+00:00              True
E2DV6 C7830       42662869    41445 2026-10-08 14:00:00+00:00 2026-10-08 14:10:00+00:00              True
E2DV6 P7835       42866656    43887 2026-10-08 14:00:00+00:00 2026-10-08 14:10:00+00:00              True
E2DV6 C7835       42874305    49623 2026-10-08 14:00:00+00:00 2026-10-08 14:10:00+00:00              True
E2DV6 C7825       43046056    34877 2026-10-08 14:00:00+00:00 2026-10-08 14:10:00+00:00              True
E2DV6 P7825       43078412    43595 2026-10-08 14:00:00+00:00 2026-10-08 14:10:00+00:00              True
```

## Timestamp definitions and quality
For CME MDP 3.0, ts_event is the matching-engine-received timestamp (60-TransactTime). ts_recv is Databento capture-server reception time. Their difference measures reception delay, not market-maker reaction latency. Timestamp precision does not establish clock accuracy.
```text
 market  instrument_id  records  missing_event  missing_recv  event_backsteps  recv_backsteps  duplicate_event_times  bad_recv_or_snapshot  negative_recv_event  recv_event_median_us  recv_event_p95_us  recv_event_p99_us
futures          10252   166088              0             0                0               0                   8399                     0                    0               90.7475           338.3020          642.77818
options       42874305    49623              0             0                0               0                     40                     0                    0            16690.4770        334987.4570       861052.02810
options       42662869    41445              0             0                0               0                     29                     0                    0            16065.0010        302550.3166       801781.56568
options       42866656    43887              0             0                0               0                     35                     0                    0            15352.8170        337086.2687       881717.69054
options       42646140    50987              0             0                0               0                     53                     0                    0            16993.4140        344484.9129       861086.25320
options       43046056    34877              0             0                0               0                     39                     0                    0            14983.8570        308284.7326       776167.73104
options       43078412    43595              0             0                0               0                     39                     0                    0            20701.8980        357685.1421       870461.72646
```
Reception delays are materially different when the option/futures median gap exceeds the review threshold. This can reflect processing, dissemination, batching or capture-path effects; these summaries do not identify the cause or prove clock skew. It also means reception-time matching answers a different question from exchange-event-time matching.
```text
 instrument_id  recv_event_median_us  recv_event_p95_us  recv_event_p99_us  median_gap_to_futures_us
      42874305             16690.477        334987.4570       861052.02810                16599.7295
      42662869             16065.001        302550.3166       801781.56568                15974.2535
      42866656             15352.817        337086.2687       881717.69054                15262.0695
      42646140             16993.414        344484.9129       861086.25320                16902.6665
      43046056             14983.857        308284.7326       776167.73104                14893.1095
      43078412             20701.898        357685.1421       870461.72646                20611.1505
```

### Sending-timestamp decomposition
Where ts_in_delta is available, recv-minus-send is ts_in_delta / 1,000 in microseconds; send-minus-event is total reception delay minus that interval. This helps locate the observed gap, but does not establish clock accuracy or identify an exchange/feed-path cause. Missing or sentinel deltas are excluded.
```text
 market  instrument_id  valid_delta_records  recv_minus_send_median_us  recv_minus_send_p95_us  send_minus_event_median_us  send_minus_event_p95_us
futures          10252               166088                     12.670                 14.8210                      77.862                325.10725
options       42646140                50987                     13.131              27358.5548                    9591.763             318172.18540
options       42662869                41445                     13.633              53074.0618                    6813.881             263027.95600
options       42866656                43887                     13.398              42918.2443                    7017.342             303735.71640
options       42874305                49623                     13.268              32436.1514                    8927.684             307459.81560
options       43046056                34877                     14.043              71694.4858                    4784.893             253295.92300
options       43078412                43595                     13.227              32876.7059                   12081.270             327640.94190
```

## Corrected event construction
Final quote states are aggregated at each instrument/event timestamp BEFORE changes are computed. Invalid final quotes break the comparison. This prevents a later size-only update at the same timestamp from erasing a price move.
```text
 legacy_events  corrected_events  event_count_difference
          7519              7519                       0
```
Regression tests passed: 17. Old notebook counts should not be used in place of these corrected results.

## Signed updates and waiting times
Nearest matching searches both directions within +/-10000 us. Across matched pairs, 37.2% of nearest updates occur before the futures event. These are signed update offsets, not identified negative causal reactions. First-after matching is strictly later by definition. Its quantiles exclude unmatched/censored cases and describe observed waits within the configured horizon.
```text
 instrument_id  event_pairs  eligible_pre_state  nearest_matched  negative_nearest_fraction  simultaneous_fraction  nearest_median_us  nearest_p05_us  nearest_p95_us  forward_matched  first_after_median_us  first_after_p95_us  right_censored_fraction  contaminated_fraction
      42646140         7519                7519             7353                   0.371277                    0.0             26.048      -1118.1092        760.4612             6971                243.884           5599.2250                 0.072882               0.450581
      42662869         7519                7519             7297                   0.376730                    0.0             31.624      -1247.2028        704.7364             6783                251.860           5360.7022                 0.097885               0.461743
      42866656         7519                7519             7309                   0.385005                    0.0             28.796      -1282.5060        984.4676             6822                250.249           5378.6980                 0.092698               0.460422
      42874305         7519                7519             7371                   0.361959                    0.0             31.346      -1196.5030        794.3250             6969                240.966           5100.7096                 0.073148               0.458746
      43046056         7519                7519             7205                   0.372241                    0.0             37.170      -1620.3492        980.4472             6653                263.070           5721.8716                 0.115175               0.482489
      43078412         7519                7519             7267                   0.367552                    0.0             28.596      -1083.6954        941.5794             6849                255.030           5783.7148                 0.089108               0.465031
```

### Window sensitivity
```text
 window_us  pairs  matched  negative_fraction  near_zero_1us_fraction  eligible_pre_fraction
       100  45114    17392           0.349126                0.030416                    1.0
      1000  45114    39306           0.350583                0.013459                    1.0
     10000  45114    43802           0.372449                0.012077                    1.0
```

### Overlapping events
Among observed forward matches, 46.3% follow another futures midpoint move. Censored pairs have unknown overlap status rather than a fabricated zero. The following table restricts to eligible observed updates before the next futures event; this filtering changes the population and does not eliminate unrelated option activity.
```text
 instrument_id  event_pairs  eligible_pre_state  nearest_matched  negative_nearest_fraction  simultaneous_fraction  nearest_median_us  nearest_p05_us  nearest_p95_us  forward_matched  first_after_median_us  first_after_p95_us  right_censored_fraction  contaminated_fraction
      42646140         3830                3830             3830                   0.236292                    0.0             36.406       -300.4637        495.5491             3830                101.597           2850.8049                      0.0                    0.0
      42662869         3651                3651             3651                   0.224870                    0.0             41.536       -317.5270        477.8500             3651                109.162           2791.6940                      0.0                    0.0
      42866656         3681                3681             3681                   0.242054                    0.0             39.134       -305.7520        526.2520             3681                105.846           3068.1280                      0.0                    0.0
      42874305         3772                3772             3772                   0.218187                    0.0             38.763       -253.5261        528.5628             3772                 93.868           2224.6777                      0.0                    0.0
      43046056         3443                3443             3443                   0.218995                    0.0             45.902       -296.2290        518.4268             3443                107.990           2961.4546                      0.0                    0.0
      43078412         3664                3664             3664                   0.223253                    0.0             38.677       -282.7930        535.7605             3664                103.849           2395.5234                      0.0                    0.0
```

### Isolated events and signed directional proxy
An isolated event has no other midpoint event in the +/-10000 us window. There are 195 isolated events and 1,036 nearest matched event-contract pairs. Endpoints with unknown neighboring events are excluded.
```text
 instrument_id  event_pairs  eligible_pre_state  nearest_matched  negative_nearest_fraction  simultaneous_fraction  nearest_median_us  nearest_p05_us  nearest_p95_us  forward_matched  first_after_median_us  first_after_p95_us  right_censored_fraction  contaminated_fraction
      42646140          195                 195              178                   0.129213                    0.0            221.125       -361.3901       4719.5588              171                257.388           6584.4920                 0.123077                    0.0
      42662869          195                 195              174                   0.132184                    0.0            209.157       -447.8185       4691.9281              165                253.906           5569.6516                 0.153846                    0.0
      42866656          195                 195              168                   0.166667                    0.0            165.788       -420.7896       4990.2776              159                233.974           6219.8400                 0.184615                    0.0
      42874305          195                 195              179                   0.162011                    0.0            213.128      -1767.6726       3220.7200              166                263.852           4642.3290                 0.148718                    0.0
      43046056          195                 195              167                   0.149701                    0.0            224.742       -276.8358       1786.4406              152                278.282           4207.4389                 0.220513                    0.0
      43078412          195                 195              170                   0.129412                    0.0            212.030      -2080.2592       3616.3627              153                251.976           4692.3832                 0.215385                    0.0
```
The directional proxy selects call midpoint changes in the futures-move direction and put changes in the opposite direction. It retains both negative and positive offsets. Direction consistency is not a causal identification rule; independent information and shared news remain possible explanations.
```text
 instrument_id  event_pairs  eligible_pre_state  nearest_matched  negative_nearest_fraction  simultaneous_fraction  nearest_median_us  nearest_p05_us  nearest_p95_us  forward_matched  first_after_median_us  first_after_p95_us  right_censored_fraction  contaminated_fraction
      42646140          195                 193               55                   0.181818                    0.0            279.290      -4444.8706       5335.6248               45                354.146           5699.5328                 0.769231                    0.0
      42662869          195                 195               73                   0.191781                    0.0            263.420      -3631.4752       2918.2708               60                336.036           5599.2986                 0.692308                    0.0
      42866656          195                 194               79                   0.177215                    0.0            258.920      -1826.7372       4790.7024               66                362.671           5026.5640                 0.661538                    0.0
      42874305          195                 195               62                   0.225806                    0.0            257.024      -2615.3699       1818.2188               51                341.518           5673.9890                 0.738462                    0.0
      43046056          195                 194               81                   0.148148                    0.0            341.358      -1915.6180       4068.1720               72                424.601           6357.9498                 0.630769                    0.0
      43078412          195                 191               57                   0.192982                    0.0            334.156      -4725.2616       6688.0392               47                375.278           7664.6022                 0.758974                    0.0
```

### Reception clock and same-pair comparison
The reception-time matcher now measures overlap against the next reception-time futures event. This is separate from the same-pair comparison below: the latter holds the futures/option pair fixed and shows how its offset changes between the two clocks.
```text
 instrument_id  event_pairs  eligible_pre_state  nearest_matched  negative_nearest_fraction  simultaneous_fraction  nearest_median_us  nearest_p05_us  nearest_p95_us  forward_matched  first_after_median_us  first_after_p95_us  right_censored_fraction  contaminated_fraction
      42646140         7519                7519             6658                   0.403875                    0.0           316.3220     -5095.69885      6252.60510             5726               2014.340          8398.68275                 0.238463               0.649494
      42662869         7519                7519             6483                   0.399661                    0.0           383.3280     -5798.60960      6624.74670             5516               2064.681          8455.50500                 0.266392               0.650653
      42866656         7519                7519             6527                   0.438946                    0.0           225.6070     -6317.58130      6114.65200             5463               2141.168          8531.69020                 0.273441               0.649643
      42874305         7519                7519             6703                   0.419961                    0.0           268.4010     -6023.61140      6742.39280             5721               1967.821          8541.50300                 0.239128               0.652159
      43046056         7519                7519             6288                   0.385655                    0.0           456.5900     -5888.64200      6704.23385             5271               2067.471          8470.77300                 0.298976               0.658509
      43078412         7519                7519             6458                   0.428925                    0.0           275.7165     -5868.99530      6656.87710             5458               2267.806          8277.56930                 0.274106               0.645291
```
```text
 instrument_id  pairs  event_offset_median_us  receive_offset_median_us  difference_median_us  difference_p95_us
      42646140   6971                 243.884                 38451.229             37255.854       700452.97650
      42662869   6783                 251.860                 36002.700             35102.876       576747.86130
      42866656   6822                 250.249                 37135.116             35939.008       732045.02895
      42874305   6969                 240.966                 36390.501             35543.589       693812.50660
      43046056   6653                 263.070                 35102.557             34492.340       545378.09880
      43078412   6849                 255.030                 37961.576             37190.542       731975.05740
```

### Placebo
The +20 ms placebo shifts the event anchor but keeps real futures events on their actual timeline when assessing overlap. It is a descriptive control for update intensity, not a clock calibration.
```text
 instrument_id  event_pairs  eligible_pre_state  nearest_matched  negative_nearest_fraction  simultaneous_fraction  nearest_median_us  nearest_p05_us  nearest_p95_us  forward_matched  first_after_median_us  first_after_p95_us  right_censored_fraction  contaminated_fraction
      42646140         7519                7519             7353                   0.371277                    0.0             26.048      -1118.1092        760.4612             6971                243.884           5599.2250                 0.072882               0.450581
      42662869         7519                7519             7297                   0.376730                    0.0             31.624      -1247.2028        704.7364             6783                251.860           5360.7022                 0.097885               0.461743
      42866656         7519                7519             7309                   0.385005                    0.0             28.796      -1282.5060        984.4676             6822                250.249           5378.6980                 0.092698               0.460422
      42874305         7519                7519             7371                   0.361959                    0.0             31.346      -1196.5030        794.3250             6969                240.966           5100.7096                 0.073148               0.458746
      43046056         7519                7519             7205                   0.372241                    0.0             37.170      -1620.3492        980.4472             6653                263.070           5721.8716                 0.115175               0.482489
      43078412         7519                7519             7267                   0.367552                    0.0             28.596      -1083.6954        941.5794             6849                255.030           5783.7148                 0.089108               0.465031
```
```text
 instrument_id  event_pairs  eligible_pre_state  nearest_matched  negative_nearest_fraction  simultaneous_fraction  nearest_median_us  nearest_p05_us  nearest_p95_us  forward_matched  first_after_median_us  first_after_p95_us  right_censored_fraction  contaminated_fraction
      42646140         7519                7519             6344                   0.495113                    0.0             28.316      -7869.2747       7445.8632             4829               3892.256           8833.8600                 0.357760               0.121971
      42662869         7519                7519             5936                   0.527460                    0.0           -232.123      -8182.9225       7797.6135             4216               3754.527           9099.9850                 0.439287               0.138046
      42866656         7519                7519             6006                   0.532634                    0.0           -296.758      -8442.4930       7541.6080             4172               3770.751           9033.4768                 0.445139               0.144295
      42874305         7519                7519             6286                   0.497773                    0.0             21.240      -8027.5575       7937.6235             4695               4137.374           9096.9234                 0.375582               0.142918
      43046056         7519                7519             5432                   0.552835                    0.0           -451.299      -8606.9923       7505.8851             3485               3615.686           9107.8880                 0.536508               0.165280
      43078412         7519                7519             6088                   0.502300                    0.0            -14.947      -8253.6758       7834.0385             4545               4009.102           8943.2676                 0.395531               0.112871
```

## Assessment
**Conditional Go — data available; microsecond comparability unverified**
**Microsecond measurement status:** Not validated: no independent cross-engine clock error bound; empirical concerns require follow-up.
The sample supports data ingestion and further method development. It does not yet support causal microsecond reaction-latency claims. The assessment is not changed to Go simply because data downloads succeeded.

### Findings requiring review
- Largest absolute option/futures median reception-delay gap is 20,611.2 us, above the 1,000 us review threshold.
- 46.3% of observed first-after matches follow another futures move. All-pair waiting times cannot be interpreted as single-event reactions.

## Task coverage
```text
                                           task                                              status                                                                             evidence_or_limitation
                     Futures MBP-1 availability                                 Verified for sample                                                                              ESZ6: 166,088 records
                 0DTE option MBP-1 availability                                 Verified for sample                                                              6 selected contracts; 264,414 records
                Historical course-license range Metadata recorded; full license coverage unverified                            Current-key range does not establish free access to every contract/date
          Common sample retrieval and alignment                                 Verified for sample                                                        2026-10-08; 7,519 corrected midpoint events
                   Timestamp fields and quality                                             Checked                                                  Definitions and per-contract quality/delay tables
              Zero/near-zero lead-lag artifacts                         Descriptive checks complete                                 Signed offsets, window sensitivity, placebo, isolated-event checks
Systematically negative causal reaction latency                     Not identified from MBP-1 alone      Direction-consistent signed-update proxy reported; causality and clock skew remain unresolved
        Timestamp comparability and limitations                   Conditional assessment documented Not validated: no independent cross-engine clock error bound; empirical concerns require follow-up
```

## Next steps and scope
1. Investigate the option/futures reception-delay gap using ts_in_delta and channel/feed-path information where available. Do not treat reception delay as a clock-skew estimate.
2. Repeat across additional windows/dates if isolated-event matches are sparse. Do not expand to a profitability study under this issue.
3. Obtain provider or exchange evidence for cross-engine synchronization accuracy. Without an error bound, keep microsecond timing claims conditional.
4. Report descriptive results in 100 us, 1 ms and 10 ms windows, with denominators, censoring and overlap exclusions. Coarser buckets do not cure unknown clock bias.
5. Later issues must define economic reaction/stale-window resolution. Do not clamp negative offsets or silently shift timestamps to fit an expected result.

## References
- https://databento.com/docs/venues-and-datasets/glbx-mdp3
- https://databento.com/docs/examples/futures/futures-product-options
- https://databento.com/docs/api-reference-historical

## Reproducibility and publication
Only aggregate tables, figures and metadata are exported here. Keep raw DBN files and credentials out of Git. Run this revision before citing its findings; outputs from the previous version are not reused.
