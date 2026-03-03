# fixtures

> Path: `CDEL-v2/cdel/v5_0/tests/fixtures`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `powermetrics_bad.txt`: text output or trace artifact.
- `powermetrics_good.txt`: text output or trace artifact.
- `powermetrics_help.txt`: text output or trace artifact.
- `sealed_thermo_fixture_bad_powermetrics.toml`: TOML configuration.
- `sealed_thermo_fixture_critical.toml`: TOML configuration.
- `sealed_thermo_fixture_ok.toml`: TOML configuration.
- `thermal_critical.log`: text output or trace artifact.
- `thermal_ok.log`: text output or trace artifact.

## File-Type Surface

- `txt`: 3 files
- `toml`: 3 files
- `log`: 2 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v5_0/tests/fixtures
find CDEL-v2/cdel/v5_0/tests/fixtures -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v5_0/tests/fixtures | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
