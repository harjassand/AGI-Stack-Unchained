# tool_nativeblock_shadow

> Path: `baremetal_lgp/fixtures/apfsc/phase4/tools/tool_nativeblock_shadow`

## Mission

Bare-metal Rust runtime components, services, and performance-critical execution surfaces.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `gold_traces.jsonl`: project artifact.
- `manifest.json`: JSON contract, config, or artifact.
- `toolpack.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files
- `jsonl`: 1 files

## Operational Checks

```bash
ls -la baremetal_lgp/fixtures/apfsc/phase4/tools/tool_nativeblock_shadow
find baremetal_lgp/fixtures/apfsc/phase4/tools/tool_nativeblock_shadow -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files baremetal_lgp/fixtures/apfsc/phase4/tools/tool_nativeblock_shadow | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
