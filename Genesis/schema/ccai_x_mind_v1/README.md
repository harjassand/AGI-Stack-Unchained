# ccai_x_mind_v1

> Path: `Genesis/schema/ccai_x_mind_v1`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `affordance_latent_v1.schema.json`: JSON contract, config, or artifact.
- `causal_mechanism_registry_v1.schema.json`: JSON contract, config, or artifact.
- `ccai_x_mind_patch_candidate_manifest_v1.schema.json`: JSON contract, config, or artifact.
- `coherence_operator_v1.schema.json`: JSON contract, config, or artifact.
- `do_map_v1.schema.json`: JSON contract, config, or artifact.
- `efe_report_v1.schema.json`: JSON contract, config, or artifact.
- `inference_kernel_isa_v1.schema.json`: JSON contract, config, or artifact.
- `inference_kernel_program_v1.schema.json`: JSON contract, config, or artifact.
- `intervention_log_entry_v1.schema.json`: JSON contract, config, or artifact.
- `markov_blanket_spec_v1.schema.json`: JSON contract, config, or artifact.
- `policy_prior_v1.schema.json`: JSON contract, config, or artifact.
- `preference_capsule_v1.schema.json`: JSON contract, config, or artifact.
- `workspace_state_v1.schema.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 13 files

## Operational Checks

```bash
ls -la Genesis/schema/ccai_x_mind_v1
find Genesis/schema/ccai_x_mind_v1 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/schema/ccai_x_mind_v1 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
