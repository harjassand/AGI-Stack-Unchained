# eudrs_u

> Path: `CDEL-v2/cdel/v18_0/eudrs_u`

## Mission

Core verifier/runtime implementation for CDEL protocol versions and shared primitives.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `__init__.py`: Python module or executable script.
- `cac_v1.py`: Python module or executable script.
- `concept_shard_v1.py`: Python module or executable script.
- `dep_v1.py`: Python module or executable script.
- `dmpl_action_encode_v1.py`: Python module or executable script.
- `dmpl_action_receipt_v1.py`: Python module or executable script.
- `dmpl_config_load_v1.py`: Python module or executable script.
- `dmpl_gate_v1.py`: Python module or executable script.
- `dmpl_merkle_v1.py`: Python module or executable script.
- `dmpl_patch_compose_v1.py`: Python module or executable script.
- `dmpl_planner_dcbts_l_v1.py`: Python module or executable script.
- `dmpl_retrieve_v1.py`: Python module or executable script.
- `dmpl_reward_proxy_v1.py`: Python module or executable script.
- `dmpl_tensor_io_v1.py`: Python module or executable script.
- `dmpl_trace_v1.py`: Python module or executable script.
- `dmpl_train_sgd_v1.py`: Python module or executable script.
- `dmpl_train_trace_v1.py`: Python module or executable script.
- `dmpl_types_v1.py`: Python module or executable script.
- `dmpl_value_v1.py`: Python module or executable script.
- `eudrs_u_artifact_refs_v1.py`: Python module or executable script.
- `eudrs_u_common_v1.py`: Python module or executable script.
- `eudrs_u_hash_v1.py`: Python module or executable script.
- `eudrs_u_merkle_v1.py`: Python module or executable script.
- `eudrs_u_q32ops_v1.py`: Python module or executable script.
- `fal_ladder_v1.py`: Python module or executable script.
- ... and 64 more files.

## File-Type Surface

- `py`: 89 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v18_0/eudrs_u
find CDEL-v2/cdel/v18_0/eudrs_u -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v18_0/eudrs_u | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
