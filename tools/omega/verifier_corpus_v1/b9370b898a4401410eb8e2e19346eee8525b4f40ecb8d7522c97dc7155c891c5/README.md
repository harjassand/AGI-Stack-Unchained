# b9370b898a4401410eb8e2e19346eee8525b4f40ecb8d7522c97dc7155c891c5

> Path: `tools/omega/verifier_corpus_v1/b9370b898a4401410eb8e2e19346eee8525b4f40ecb8d7522c97dc7155c891c5`

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
ls -la tools/omega/verifier_corpus_v1/b9370b898a4401410eb8e2e19346eee8525b4f40ecb8d7522c97dc7155c891c5
find tools/omega/verifier_corpus_v1/b9370b898a4401410eb8e2e19346eee8525b4f40ecb8d7522c97dc7155c891c5 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/omega/verifier_corpus_v1/b9370b898a4401410eb8e2e19346eee8525b4f40ecb8d7522c97dc7155c891c5 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
