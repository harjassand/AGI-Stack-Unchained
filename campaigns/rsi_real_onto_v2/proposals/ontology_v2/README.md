# ontology_v2

> Path: `campaigns/rsi_real_onto_v2/proposals/ontology_v2`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `defs/`: component subtree.

## Key Files

- `68cdacd3b23840975ee0361608a6d8e574bb43f04af8eaf9a174e0278cd8447e.json`: JSON contract, config, or artifact.
- `87e29dd7e1dcf12937d8ac83cbe9ddf51fbc384675e410a8a42aeab6cc9df08c.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la campaigns/rsi_real_onto_v2/proposals/ontology_v2
find campaigns/rsi_real_onto_v2/proposals/ontology_v2 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_real_onto_v2/proposals/ontology_v2 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
