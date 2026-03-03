# ccai_x_v1

> Path: `Genesis/test_vectors/ccai_x_v1`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `do_map.json`: JSON contract, config, or artifact.
- `efe_report.json`: JSON contract, config, or artifact.
- `expected_candidate_id.txt`: text output or trace artifact.
- `expected_do_payload_hash.txt`: text output or trace artifact.
- `expected_intervention_log_final_link_hash.txt`: text output or trace artifact.
- `expected_mechanism_hash.txt`: text output or trace artifact.
- `expected_workspace_state_hash.txt`: text output or trace artifact.
- `inference_kernel_isa.json`: JSON contract, config, or artifact.
- `intervention_log.jsonl`: project artifact.
- `markov_blanket_spec.json`: JSON contract, config, or artifact.
- `mechanism_registry.json`: JSON contract, config, or artifact.
- `policy_prior.json`: JSON contract, config, or artifact.
- `preference_capsule.json`: JSON contract, config, or artifact.
- `workspace_state.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 8 files
- `txt`: 5 files
- `jsonl`: 1 files

## Operational Checks

```bash
ls -la Genesis/test_vectors/ccai_x_v1
find Genesis/test_vectors/ccai_x_v1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/test_vectors/ccai_x_v1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
