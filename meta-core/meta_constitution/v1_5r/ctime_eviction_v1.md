# C-CRYSTAL Eviction v1 (Pinned)

This document pins macro eviction rules for v1.5r.

## Window

- `W_MAC = 8` epochs
- `F_KEEP = 2`
- `K_DROP = 3` consecutive epochs

## Metrics

Compute over the last `W_MAC` heldout traces:

- `support_families_hold_window`
- `MDL_Gain_bits_window`
- Replay equivalence spot-check

## Eviction

A macro is evicted if any condition holds for `K_DROP` consecutive epochs:

1. `support_families_hold_window < F_KEEP`
2. `MDL_Gain_bits_window <= 0`
3. Replay equivalence fails under current frontier

Eviction produces `macro_eviction_reason_v1.json` with reason codes and proof hashes.
