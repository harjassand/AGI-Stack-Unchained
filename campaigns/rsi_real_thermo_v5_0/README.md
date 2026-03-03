# rsi_real_thermo_v5_0

> Path: `campaigns/rsi_real_thermo_v5_0`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `rsi_real_thermo_pack_fixture_v1.json`: JSON contract, config, or artifact.
- `rsi_real_thermo_pack_live_capture_v1.json`: JSON contract, config, or artifact.
- `rsi_real_thermo_pack_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 3 files

## Operational Checks

```bash
ls -la campaigns/rsi_real_thermo_v5_0
find campaigns/rsi_real_thermo_v5_0 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_real_thermo_v5_0 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
