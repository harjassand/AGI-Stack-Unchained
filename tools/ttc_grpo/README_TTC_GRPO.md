# TTC GRPO v1 (Agent 2)

This module implements a deterministic Test-Time Compute RL loop for proposer-arena candidates.

## What it does

- Uses `mlx` generation for candidate IR (with deterministic seed lineage).
- Parses and validates `polymath_restricted_ir_v1` candidates fail-closed.
- Evaluates candidates through a DMPL harness that emits plan + `cac_v1` evidence.
- Computes GRPO-style group advantages and applies LoRA-state updates.
- Emits content-addressed candidate evals and a content-addressed run receipt.

## Key files

- `grpo_config_v1.py`: strict config loading + hash binding.
- `grpo_runner_v1.py`: main loop (`run_grpo_ttc_v1`).
- `grpo_policy_mlx_v1.py`: seeded MLX policy wrapper with LoRA trainable adapter updates.
- `ir_generator_v1.py`: prompt builder + IR parsing/validation.
- `dmpl_eval_harness_v1.py`: deterministic DMPL/CAC evaluation harness.
- `candidate_store_v1.py`: canonical content-addressed artifact store.
- `schemas.py`: runtime dataclass mirrors and Q16/Q32 helpers.
- `CDEL-v2/cdel/v19_0/verify_ttc_grpo_run_receipt_v1.py`: structural run verifier.
- `CDEL-v2/cdel/v19_0/verify_ttc_grpo_candidate_eval_v1.py`: optional candidate-eval verifier.

## Execution

Direct config mode:

```bash
python3 tools/ttc_grpo/grpo_runner_v1.py \
  --config campaigns/rsi_proposer_arena_grpo_ttc_v1/ttc_grpo_run_config_v1.json \
  --out_dir runs/ttc_grpo_demo
```

Campaign-pack mode:

```bash
python3 tools/ttc_grpo/grpo_runner_v1.py \
  --campaign_pack campaigns/rsi_proposer_arena_grpo_ttc_v1/rsi_proposer_arena_grpo_ttc_pack_v1.json \
  --out_dir runs/ttc_grpo_demo
```

## Determinism and fail-closed behavior

- Candidate seed = deterministic hash of run seed, tick, producer_run_id, outer iter, and candidate index.
- Artifact hashes are GCJ-1 canonical JSON hashes (`sha256:<hex>`).
- Schema mismatches, ID mismatches, and forbidden-token parsing issues fail closed.
- DMPL runtime can run in real mode when roots are available; otherwise synthetic mode stays deterministic.
- Campaign pack install intent is constrained to `STATUS_SHADOW`.
- `ttc_grpo_lora_adapter_state_v1` is training-local (non-promotable) state and is not part of verifier-critical promotion evidence.
