# native

> Path: `tools/omega/native`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `native_benchmark_v1.py`: Python module or executable script.
- `native_healthcheck_v1.py`: Python module or executable script.
- `native_profiler_v1.py`: Python module or executable script.
- `rust_build_repro_v1.py`: Python module or executable script.
- `rust_codegen_v1.py`: Python module or executable script.
- `rust_vendor_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 6 files

## Operational Checks

```bash
ls -la tools/omega/native
find tools/omega/native -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/omega/native | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
