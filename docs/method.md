# Issue 8: order-level resolution definitions

## Unit of observation

Issue #6 produces one row per (futures event, option). Only `status == 'stale'` enters this analysis. The stale side is the ask when a taker could buy under fair value, and the bid when a taker could sell above fair value. We identify orders resting at that side and pre-move quote price immediately before `start` (`t0`). For overlapping futures events, an order may appear in more than one event window; event-level rates are not independent.

## Resting-order state

Replay `mbo` per `instrument_id`, tracking order IDs through `A`, `M`, `C`, and `R`. `F` denotes an execution of a resting order; `T` is an aggressor trade and is not an independent resting-order fill. `F` and an associated `C` may describe one execution; do not count both as fill and cancellation. State is evaluated before `t0`; actions in `[start, min(resolution, window_end))` are audited. At identical timestamps, venue sequence is used where provided.

A valid initial snapshot or a confirmed clear-and-rebuild is needed to claim full state coverage. MBO starting late in the session may miss old orders; these windows remain `unclassified` regardless of any partial activity observed. A removed/modified *individual order* does not necessarily mean the entire quote disappeared. Confirm quote-level resolution against the MBP-1 path in Issue #6 before using these categories as definitive quote-level outcomes.

## Categories and denominators

`filled`, `cancelled`, `modified`, `mixed`, `unclassified`. They describe observed actions affecting matched resting orders, conditional on reliable book initialization. Multiple independent actions on matched orders produce `mixed`. Events without matching order IDs, questionable F/C pairing, missing initialization or no observed action stay `unclassified`.

All reported rates use the number of Issue #6 stale pairs in the selected sample as the denominator, unless otherwise stated. Keep unclassified and censored pairs visible. Fill and cancellation *quantities* are separately reported.

## Markouts

For confirmed resting-order fills, taker-sign is +1 for a stale ask and -1 for a stale bid. For horizon `h`, `markout_points = taker_sign * (mid(t_fill+h) - fill_price)` and `markout_usd = multiplier * markout_points`. We take the first available quote at or after the target horizon; missing observations remain missing. These are quote-marked outcomes, not net executable round-trip P&L. Do not stop markouts at the stale-window cutoff because the fill has already occurred.

## Limitations

- Cross-engine event-clock comparability remains conditional as discussed in Issue #1.
- MBO order IDs do not disclose market-maker identity or trading intent.
- The action-based implementation is intentionally conservative but cannot fully prove causal resolution of the top-of-book level without independent BBO checks.
- If MBO is truncated or no snapshot is present, quote-level totals should be treated as inconclusive.
- Same-event `F`/`C` matching and message grouping should be checked using actual CME samples, including `F_LAST` and sequence numbers.
