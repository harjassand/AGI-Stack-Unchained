# qxwmr_states

> Path: `polymath/registry/eudrs_u/vision/perception/qxwmr_states`

## Mission

Polymath registry/store logic for scouting, bootstrap, and domain conquest flows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_1c00c18893db37e22713e11024392740a5db4c461fce9bcf210f6dfb1c2f5a50.qxwmr_state_packed_v1.bin`: project artifact.
- `sha256_20e5316cf09a5c9dc7fb3a969405ee597c66cd13bc803e2e237abe9a716e543f.qxwmr_state_packed_v1.bin`: project artifact.
- `sha256_456a282bf8e308b7755ec930565511dc24f9447fde9a8b2eaeac501b3fd376f4.qxwmr_state_packed_v1.bin`: project artifact.
- `sha256_602d0d028e97a602ad077821a7b22d85af3bee10a0162445b131b4bd8d798d3f.qxwmr_state_packed_v1.bin`: project artifact.
- `sha256_70c6068d4f597bed73bb6b7302b3ed5a5e4e21b817b817551af1c7d2ea2bcb94.qxwmr_state_packed_v1.bin`: project artifact.
- `sha256_981bb88e64a7bb3508c0a375b2e83647391bb56e60230ceb061fef4e6c5116c2.qxwmr_state_packed_v1.bin`: project artifact.
- `sha256_a09c15f4bf74551b6311a5c0a8d2a795211f599bff55cb15a4ee6c7b6b84b162.qxwmr_state_packed_v1.bin`: project artifact.
- `sha256_a7217bd57ae4b32bcbaed607d4dbe88a12ee7128d3be2fe52775b660dc6945e1.qxwmr_state_packed_v1.bin`: project artifact.
- `sha256_ff4daaa13d5d053f8530bc86077cbca1ec3bf2654b6802ab928713d1e61f8234.qxwmr_state_packed_v1.bin`: project artifact.

## File-Type Surface

- `bin`: 9 files

## Operational Checks

```bash
ls -la polymath/registry/eudrs_u/vision/perception/qxwmr_states
find polymath/registry/eudrs_u/vision/perception/qxwmr_states -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files polymath/registry/eudrs_u/vision/perception/qxwmr_states | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
