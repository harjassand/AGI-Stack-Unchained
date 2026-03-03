# 15c2e75adbb4b0f98e823d17959d64ba84abe81591c626e997b416e88f050455

> Path: `tools/omega/verifier_corpus_v1/15c2e75adbb4b0f98e823d17959d64ba84abe81591c626e997b416e88f050455`

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
ls -la tools/omega/verifier_corpus_v1/15c2e75adbb4b0f98e823d17959d64ba84abe81591c626e997b416e88f050455
find tools/omega/verifier_corpus_v1/15c2e75adbb4b0f98e823d17959d64ba84abe81591c626e997b416e88f050455 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/omega/verifier_corpus_v1/15c2e75adbb4b0f98e823d17959d64ba84abe81591c626e997b416e88f050455 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
