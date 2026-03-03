# fail_c5

> Path: `CDEL-v2/proof/ccai_x_mind_v1/fixtures/candidates/fail_c5`

## Mission

Local component subtree within the AGI stack; maintain deterministic, contract-safe changes.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `causal_mechanism_registry.json`: JSON contract, config, or artifact.
- `coherence_operator.json`: JSON contract, config, or artifact.
- `do_map.json`: JSON contract, config, or artifact.
- `inference_kernel_isa.json`: JSON contract, config, or artifact.
- `inference_kernel_program.json`: JSON contract, config, or artifact.
- `markov_blanket_spec.json`: JSON contract, config, or artifact.
- `policy_prior.json`: JSON contract, config, or artifact.
- `preference_capsule.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 8 files

## Operational Checks

```bash
ls -la CDEL-v2/proof/ccai_x_mind_v1/fixtures/candidates/fail_c5
find CDEL-v2/proof/ccai_x_mind_v1/fixtures/candidates/fail_c5 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/proof/ccai_x_mind_v1/fixtures/candidates/fail_c5 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
