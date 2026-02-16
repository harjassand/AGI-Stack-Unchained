# phi_core v1 (Pinned)

phi_core defines the only features visible to Pi0 and guard evaluation.

## Input

`micro_observation_stream` is an ordered list of observation hashes, where each hash is a string of the form `sha256:<hex>`.

## Output Features

phi_core returns a feature map with **exactly** these integer keys:

1. `obs_count`
   - Number of observations in the stream.
2. `first_obs_mod_16`
   - The last hex nibble of the first observation hash (0-15). If empty, 0.
3. `last_obs_mod_16`
   - The last hex nibble of the last observation hash (0-15). If empty, 0.
4. `xor_obs_mod_16`
   - XOR of the last hex nibble of each observation hash (0-15). If empty, 0.

No other features may be accessed by Pi0 or guard DSL.
