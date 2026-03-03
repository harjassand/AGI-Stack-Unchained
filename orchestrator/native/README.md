# native

> Path: `orchestrator/native`

## Mission

Execution orchestration logic and campaign dispatch entrypoints.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `demo_fnv1a64_v1.py`: Python module or executable script.
- `demo_vectors_fnv1a64_v1.json`: JSON contract, config, or artifact.
- `metal_runner_v1.py`: Python module or executable script.
- `native_policy_registry_v1.json`: JSON contract, config, or artifact.
- `native_router_v1.py`: Python module or executable script.
- `omega_kernel_canon_bytes_v1.py`: Python module or executable script.
- `runtime_stats_v1.py`: Python module or executable script.
- `vectors_kernel_canon_bytes_v1.json`: JSON contract, config, or artifact.
- `wasm_shadow_soak_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 7 files
- `json`: 3 files

## Operational Checks

```bash
ls -la orchestrator/native
find orchestrator/native -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files orchestrator/native | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
