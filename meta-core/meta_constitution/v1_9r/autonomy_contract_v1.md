# Autonomy Contract v1 (v1_9r)

This contract defines the autonomy boundary for metabolism v1 proposals.

## Scope
- Autonomy applies only to metabolism v1 patches.
- Only `ctx_hash_cache_v1` is allowlisted.
- Parameter search space is limited to `capacity` derived from translation inputs.

## Trust and Verification
- Extension-1 is untrusted and may generate proposals.
- CDEL verifier must recompute the proposal set from pinned inputs and reject mismatches.
- No randomness, no external inputs, and no network access are permitted.

## Inputs
- `translation_inputs_v1.json`
- `meta-core/meta_constitution/v1_9r/constants_v1.json`

## Outputs
- Autonomy manifest binds inputs to generated outputs.
- Generated proposals must exactly match enumerator output.
