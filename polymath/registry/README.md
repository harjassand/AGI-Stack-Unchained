# registry

> Path: `polymath/registry`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `eudrs_u/`: component subtree.

## Key Files

- `polymath_domain_registry_v1.json`: JSON contract, config, or artifact.
- `polymath_portfolio_v1.json`: JSON contract, config, or artifact.
- `polymath_scout_status_v1.json`: JSON contract, config, or artifact.
- `polymath_void_report_v1.jsonl`: project artifact.
- `void_topic_router_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 4 files
- `jsonl`: 1 files

## Operational Checks

```bash
ls -la polymath/registry
find polymath/registry -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
