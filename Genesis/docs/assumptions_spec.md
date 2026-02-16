# Assumption Objects and Causal Identifiability (Level-1)

Assumptions are quantified objects; they are not treated as verified facts. Each assumption must include a falsification protocol and an induced uncertainty set.

## Assumption Object (Normative)

Required fields:

- `assumption_id`
- `statement`
- `scope`
- `falsification_test`:
  - `method`
  - `power_target`
  - `min_detectable_delta`
  - `anytime_valid` (boolean)
- `uncertainty_set`: explicit set used for robust evaluation
- `failure_probability`: numeric delta or `"untestable"`

## Contract Interaction Rules

A contract that depends on assumptions MUST either:

- be robust over the induced uncertainty set(s), or
- be conditional with explicit delta accounting (see contract calculus).

If `failure_probability` is `"untestable"`, the contract MUST be robust to the assumption or MUST fail.

## Falsification Testing

- Tests should be anytime-valid where possible.
- The minimum detectable deviation and power target MUST be declared.
- Falsification outcomes MUST be logged but are not exposed to Genesis.

## Causal Models: Identifiability Witness (Mandatory)

A CAUSAL_MODEL capsule MUST include an identifiability witness. Otherwise it is non-adjudicable and MUST FAIL.

Acceptable witness types:

- Do-calculus proof artifact.
- Instrumental variable validity certificate.
- Randomized intervention data handle.
- Front-door or back-door adjustment certificate.

Witnesses MUST be provided as certificates in `evidence.certificates` and MUST be checkable by the trusted kernel.
