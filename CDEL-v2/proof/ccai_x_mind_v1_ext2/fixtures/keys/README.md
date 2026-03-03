# keys

> Path: `CDEL-v2/proof/ccai_x_mind_v1_ext2/fixtures/keys`

## Mission

Local component subtree within the AGI stack; maintain deterministic, contract-safe changes.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `ed25519_priv.hex`: project artifact.

## File-Type Surface

- `hex`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/proof/ccai_x_mind_v1_ext2/fixtures/keys
find CDEL-v2/proof/ccai_x_mind_v1_ext2/fixtures/keys -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/proof/ccai_x_mind_v1_ext2/fixtures/keys | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
