# workflows

> Path: `agi-orchestrator/.github/workflows`

## Mission

Cross-domain orchestration package for concept execution and validation pipelines.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `heldout_rotation.yml`: YAML configuration or task spec.
- `smoke.yml`: YAML configuration or task spec.
- `suite_diff_report.yml`: YAML configuration or task spec.
- `tests.yml`: YAML configuration or task spec.

## File-Type Surface

- `yml`: 4 files

## Operational Checks

```bash
ls -la agi-orchestrator/.github/workflows
find agi-orchestrator/.github/workflows -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files agi-orchestrator/.github/workflows | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
