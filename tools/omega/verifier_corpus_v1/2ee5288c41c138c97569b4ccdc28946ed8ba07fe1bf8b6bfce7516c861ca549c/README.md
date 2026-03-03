# 2ee5288c41c138c97569b4ccdc28946ed8ba07fe1bf8b6bfce7516c861ca549c

> Path: `tools/omega/verifier_corpus_v1/2ee5288c41c138c97569b4ccdc28946ed8ba07fe1bf8b6bfce7516c861ca549c`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `meta.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la tools/omega/verifier_corpus_v1/2ee5288c41c138c97569b4ccdc28946ed8ba07fe1bf8b6bfce7516c861ca549c
find tools/omega/verifier_corpus_v1/2ee5288c41c138c97569b4ccdc28946ed8ba07fe1bf8b6bfce7516c861ca549c -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/omega/verifier_corpus_v1/2ee5288c41c138c97569b4ccdc28946ed8ba07fe1bf8b6bfce7516c861ca549c | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
