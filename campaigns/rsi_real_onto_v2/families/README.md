# families

> Path: `campaigns/rsi_real_onto_v2/families`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `0dec07af1201fbcc445dbf5bfdf71d2367d438ee5f41543f5b1134dd0e6c7c7e.json`: JSON contract, config, or artifact.
- `bf152038789b040fd15dff8a28e6b7a8f391ff2a2314a36ca23e9b261e100039.json`: JSON contract, config, or artifact.
- `e0eaa992f60f86f51cfa5968cab008387838eafbdfc8341a8a204b195f513639.json`: JSON contract, config, or artifact.
- `e4047b23a8af767e2a477c58e055a228d8f89cf48ce9b84116f07d091ba2bb05.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 4 files

## Operational Checks

```bash
ls -la campaigns/rsi_real_onto_v2/families
find campaigns/rsi_real_onto_v2/families -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_real_onto_v2/families | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
