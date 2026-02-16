# Efficiency Flywheel Contract v1 (v2.0)

This contract defines the autonomy and verification boundary for metabolism v1
patches under the v2.0 efficiency flywheel.

## Scope
- Autonomy applies only to metabolism v1 patches.
- Only `ctx_hash_cache_v1` is allowlisted.
- Parameter search space is the deterministic capacity schedule derived from
  pinned translation inputs and constants.

## Determinism
- No randomness, clock, or network inputs are permitted.
- All adaptive decisions are derived from pinned inputs and prior verifier
  outputs.

## Inputs
- `translation/translation_inputs_v1.json`
- `meta-core/meta_constitution/v2_0/constants_v1.json`
- Attempt index and prior verifier reason (for manifest chaining only).

## Outputs
- Autonomy manifest v2 binds inputs and attempt metadata to the emitted patch.
- Generated proposals must match enumerator output.
- Efficiency gate must be derived from workvec replay and v2.0 constants.
