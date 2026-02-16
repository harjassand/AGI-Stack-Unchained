# C-TIME Admission v1 (Pinned)

This document pins macro admission requirements for v1.5r.

## Inputs

- `macro_def_v1.json`
- `trace_heldout_v1.jsonl` for the current epoch only
- `macro_active_set_v1.json`

## Checks

1. **Semantics binding**
   - Recompute `macro_id` and `rent_bits` and reject if mismatched.
2. **Acyclicity**
   - Macro bodies must contain only primitive ops (no macro calls).
3. **Boundedness**
   - `2 <= len(body) <= L_MAX`.
4. **Heldout support**
   - `support_families_hold >= F_MIN`
   - `support_total_hold >= N_MIN`
5. **MDL gain**
   - `MDL_Gain_bits >= DELTA_MIN_TIME_BITS`.
6. **Replay equivalence**
   - Expanding macro occurrences must preserve `post_obs_hash` under replay.

## Encoder

Greedy longest-match encoder:

- At each position, choose the longest macro body among active macros plus candidate M.
- Tie-break by smallest `macro_id`.
- Non-overlapping.

Token counts:

- Primitive action = 1 token
- Macro token = 1 token

Rent bits:

`rent_bits = 8 * len(canon_bytes(macro_def_without_rent_bits_and_macro_id))`

MDL gain:

`MDL_Gain_bits = 8 * (EncLen(D_hold|R_t) - EncLen(D_hold|R_t U {M})) - rent_bits`
