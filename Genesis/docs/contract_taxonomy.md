# Contract Taxonomy (Level-1)

Contracts are machine-checkable, binary-adjudicable specifications that accompany every capsule. They define what must be evaluated by CDEL.

## Contract Blocks

A contract MUST include the following blocks:

1. **FunctionalSpec**: Pre/postconditions and typed constraints in a decidable subset.
2. **SafetySpec**: Invariants and forbidden behaviors.
3. **ResourceSpec**: Time/memory/sample limits and optional GPU caps.
4. **StatisticalSpec**: Metrics, thresholds, and confidence requirements.
5. **RobustnessSpec**: Worst-slice or DRO guarantees under bounded capacity.

## Minimum Required Clauses by Artifact Type

All artifact types MUST provide all five blocks. Additional requirements:

- **ALGORITHM**: FunctionalSpec and SafetySpec MUST reference all entrypoints.
- **WORLD_MODEL**: StatisticalSpec MUST include predictive metrics; RobustnessSpec MUST specify a DRO set or certified slices.
- **CAUSAL_MODEL**: StatisticalSpec MUST include coverage or error bounds; capsule MUST include an identifiability witness certificate.
- **POLICY**: SafetySpec MUST include at least one invariant guarding unsafe actions.
- **EXPERIMENT**: SafetySpec MUST forbid external side effects; ResourceSpec caps MUST be strict.

## Machine-Readable Requirements

The following JSON block is normative and used by automated consistency checks.

```json
{
  "required_blocks": [
    "functional_spec",
    "safety_spec",
    "resource_spec",
    "statistical_spec",
    "robustness_spec"
  ],
  "artifact_requirements": {
    "ALGORITHM": {
      "min_functional_clauses": 1,
      "min_safety_clauses": 1
    },
    "WORLD_MODEL": {
      "min_functional_clauses": 1,
      "min_safety_clauses": 1
    },
    "CAUSAL_MODEL": {
      "min_functional_clauses": 1,
      "min_safety_clauses": 1,
      "requires_identifiability_witness": true
    },
    "POLICY": {
      "min_functional_clauses": 1,
      "min_safety_clauses": 1
    },
    "EXPERIMENT": {
      "min_functional_clauses": 1,
      "min_safety_clauses": 1
    }
  }
}
```

## FunctionalSpec

- Expressed in a decidable language (GCL1/DSL1/SMT-LIB2 subset).
- Clauses MUST be checkable by the trusted checker.
- Example: shape constraints, bounded outputs, deterministic relationships.

## SafetySpec

- Invariants: conditions that must always hold during execution.
- Forbidden behaviors: explicit disallowed actions or state changes.

## ResourceSpec

- Hard caps on wall time and memory.
- Optional caps on sample count and GPU time.
- MUST be enforced by the runtime harness.

## StatisticalSpec

- Declares metrics and decision rules (threshold, e-value, or CS LCB).
- Must include a failure probability `delta` for any probabilistic claim.
- Adaptive or sequential evaluation MUST use time-uniform methods.

## RobustnessSpec

- MUST specify certified slice families or DRO sets only.
- Worst-slice claims outside these classes are invalid and MUST be rejected.

## Measurement Protocol

- Every contract MUST declare how metrics are computed (dataset/env IDs are implicit in CDEL harness configuration).
- Genesis MUST NOT assume access to private evaluation data.
- CDEL MUST compute metrics exactly as defined without returning diagnostics to Genesis.
