# entries

> Path: `campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/entries`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_c52e4131b654c7df86e8a38f673856ebfafe1bbff31496b7e9b88a9bff40add9.shadow_corpus_entry_manifest_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/entries
find campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/entries -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_omega_daemon_v19_0_phase4d_epistemic_airlock/entries | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
