# defs

> Path: `campaigns/rsi_real_onto_v2/proposals/ontology_v2/defs`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `387f1e49dcfe001f06ff8dd4ccd72c53dac5b54322a204a0aab69b88c4c2aa81.json`: JSON contract, config, or artifact.
- `b6e0f27d859ed35af6bba5b597511642afad34652fc562285f9f6c441ed280a7.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la campaigns/rsi_real_onto_v2/proposals/ontology_v2/defs
find campaigns/rsi_real_onto_v2/proposals/ontology_v2/defs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_real_onto_v2/proposals/ontology_v2/defs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
