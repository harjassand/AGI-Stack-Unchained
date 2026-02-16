# Frontier Compression v1 (Pinned)

This document pins the deterministic frontier compression for v1.5r.

## Inputs

- Current frontier `F_t` (size M_FRONTIER)
- Optional admitted family `f_new`
- Witness window `W_t` (ordered list of the last W_WITNESS witnesses)

## Algorithm

1. Let `C = F_t` or `C = F_t U {f_new}` if a new family is admitted.
2. Initialize `S = {}`.
3. While `|S| < M_FRONTIER`:
   - For each `f` in `C \ S`, compute `marginal_covered_witnesses`.
   - Choose the `f` with largest marginal coverage.
   - Tie-break by lexicographically smallest `family_id`.
   - Add `f` to `S`.
4. Set `F_{t+1} = S`.

A full trace of the selection MUST be recorded in `frontier_update_report_v1.json`.
