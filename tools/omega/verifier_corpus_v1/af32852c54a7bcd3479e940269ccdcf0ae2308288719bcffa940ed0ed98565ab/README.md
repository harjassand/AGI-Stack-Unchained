# af32852c54a7bcd3479e940269ccdcf0ae2308288719bcffa940ed0ed98565ab

> Path: `tools/omega/verifier_corpus_v1/af32852c54a7bcd3479e940269ccdcf0ae2308288719bcffa940ed0ed98565ab`

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
ls -la tools/omega/verifier_corpus_v1/af32852c54a7bcd3479e940269ccdcf0ae2308288719bcffa940ed0ed98565ab
find tools/omega/verifier_corpus_v1/af32852c54a7bcd3479e940269ccdcf0ae2308288719bcffa940ed0ed98565ab -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/omega/verifier_corpus_v1/af32852c54a7bcd3479e940269ccdcf0ae2308288719bcffa940ed0ed98565ab | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
