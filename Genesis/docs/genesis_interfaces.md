# Genesis Module Interfaces (Level-1)

This document defines the Genesis Engine internal module interfaces and invariants.

## Common Types

```
CapsuleRef:
  capsule_id: uuid
  capsule_hash: sha256

ArtifactIR:
  format: enum
  version: string
  payload: bytes

BudgetBid:
  grade: ResearchGrade | DeploymentGrade
  alpha_bid: number
  privacy_bid:
    epsilon: number
    delta: number
  compute_bid:
    max_compute_units: int
    max_wall_time_ms: int
    max_adversary_strength: int

Candidate:
  capsule: Capsule
  shadow_metrics: map<string, number>
  diagnostics: map<string, any>

Counterexample:
  trace_id: string
  inputs: any
  observed: any
  expected: any

ArchiveEntry:
  capsule: CapsuleRef
  descriptors: map<string, number>
  scores: map<string, number>
  lineage: list<CapsuleRef>
```

## Operator Algebra

### Interface

```
ApplyOperator(op, inputs) -> Candidate
```

- `op` in {compose, mutate, rewrite, factorize, abduce, analogize, dualize}
- `inputs` is a list of Capsules or IR nodes.

### Invariants

- Output MUST include updated `parents` and `operators_used`.
- Output MUST preserve or tighten effect restrictions (never broaden).
- Output MUST include reproducibility fields.
- Output MUST preserve required provenance fields: `parents`, `operators_used`, `budget_bid`, `commitments`.

## Quality-Diversity (QD) Archive

### Interface

```
ArchiveInsert(candidate) -> ArchiveEntry
ArchiveQuery(descriptor_filter) -> list<ArchiveEntry>
```

### Invariants

- Archive descriptors MUST be declared and bounded.
- Archive must be append-only per epoch.

## CEGIS Repair Loop

### Interface

```
Repair(candidate, counterexamples) -> Candidate
```

- `counterexamples` come only from Shadow-CDEL.

### Invariants

- Repairs MUST not increase effect permissions.
- Repairs MUST update lineage and operators_used.
- Repairs MUST preserve `budget_bid` and update `commitments` when IR changes.

## Forager (Experiment Capsules)

### Interface

```
ProposeExperiment(hypotheses) -> ExperimentCapsule
ExecuteExperiment(experiment) -> DatasetHandle
```

### Invariants

- Experiments MUST be reproducible and budgeted.
- Experiments MUST NOT use private CDEL data.

## Promotion Policy

### Interface

```
PromotionReady(candidate, shadow_result, ledger_state) -> bool
SelectBid(candidate, ledger_state) -> BudgetBid
```

### Invariants

- Promotion attempts MUST be rate-limited per epoch.
- Promotion MUST require PASS_shadow and stability checks.
- Promotion MUST not exceed ledger budgets.

## Capsule Provenance Requirements

Genesis MUST preserve or update the following provenance fields on any capsule transformation:

- `parents` (lineage)
- `operators_used`
- `budget_bid`
- `commitments` (recomputed if IR or contract changes)
