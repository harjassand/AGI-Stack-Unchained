# docs

> Path: `Genesis/docs`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `ccai_x_mind_v1/`: component subtree.
- `ccai_x_v1/`: component subtree.

## Key Files

- `PHASE3_NUISANCE_V1_2_COMMIT.txt`: text output or trace artifact.
- `alpha_ledger.md`: documentation artifact.
- `alpha_ledger_correctness_proof_sketch.md`: documentation artifact.
- `archive_distillation.md`: documentation artifact.
- `assumptions_spec.md`: documentation artifact.
- `canonicalization.md`: documentation artifact.
- `compute_ledger.md`: documentation artifact.
- `contract_calculus.md`: documentation artifact.
- `contract_taxonomy.md`: documentation artifact.
- `determinism_attestation.md`: documentation artifact.
- `dp_accountant_validation_plan.md`: documentation artifact.
- `enums.md`: documentation artifact.
- `evaluate_protocol.md`: documentation artifact.
- `experiment_capsule.md`: documentation artifact.
- `genesis_interfaces.md`: documentation artifact.
- `implementation_mapping.md`: documentation artifact.
- `privacy_ledger.md`: documentation artifact.
- `promotion_policy.md`: documentation artifact.
- `red_team_plan.md`: documentation artifact.
- `robustness_spec.md`: documentation artifact.
- `shadow_cdel.md`: documentation artifact.
- `side_channel_audit_checklist.md`: documentation artifact.
- `system_integration_contract.md`: documentation artifact.
- `tcb_boundary.md`: documentation artifact.
- `verify_receipt.md`: documentation artifact.

## File-Type Surface

- `md`: 24 files
- `txt`: 1 files

## Operational Checks

```bash
ls -la Genesis/docs
find Genesis/docs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/docs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
