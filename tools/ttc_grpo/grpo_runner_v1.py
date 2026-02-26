from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes

from tools.ttc_grpo.candidate_store_v1 import CandidateStore
from tools.ttc_grpo.dmpl_eval_harness_v1 import DmplEvalHarnessV1
from tools.ttc_grpo.grpo_config_v1 import config_payload, load_grpo_config_v1
from tools.ttc_grpo.grpo_policy_mlx_v1 import PolicyLike, PolicyMlxV1
from tools.ttc_grpo.ir_generator_v1 import build_task_prompt_v1, parse_polymath_restricted_ir_v1
from tools.ttc_grpo.schemas import Q32_ONE, TTCGrpoRunConfigV1

_Q64_MASK = (1 << 64) - 1
_GOLDEN_RATIO_U64 = 0x9E3779B97F4A7C15
_MIN_REWARD_Q32 = -(1 << 62)
_ADV_CLIP_Q32 = 16 * Q32_ONE


class TTCGrpoRunnerError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise TTCGrpoRunnerError(str(reason).strip() or "GRPO_RUN_FAIL")


def _now_rfc3339_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _clip_q32(value: int, lo: int, hi: int) -> int:
    return int(max(int(lo), min(int(hi), int(value))))


def _mean_q32(values: list[int]) -> int:
    if not values:
        return 0
    return int(sum(int(v) for v in values) // len(values))


def _quantile_q32(values: list[int], *, pct: int) -> int:
    if not values:
        return 0
    rows = sorted(int(v) for v in values)
    idx = (len(rows) - 1) * int(pct) // 100
    return int(rows[idx])


def _derive_seed_u64(
    *,
    base_seed_u64: int,
    outer_iter_u64: int,
    in_group_index_u64: int,
    producer_run_id: str,
    candidate_index_u64: int,
) -> int:
    material = {
        "schema_id": "ttc_grpo_candidate_seed_v1",
        "base_seed_u64": int(base_seed_u64) & _Q64_MASK,
        "outer_iter_u64": int(outer_iter_u64) & _Q64_MASK,
        "in_group_index_u64": int(in_group_index_u64) & _Q64_MASK,
        "producer_run_id": str(producer_run_id),
        "candidate_index_u64": int(candidate_index_u64) & _Q64_MASK,
    }
    digest = hashlib.sha256(canon_bytes(material)).digest()
    return int.from_bytes(digest[-8:], "big", signed=False)


def _producer_run_id(config: TTCGrpoRunConfigV1) -> str:
    material = {
        "schema_id": "ttc_grpo_producer_run_id_v1",
        "config_hash": str(config.id),
        "run_seed_u64": int(config.seed.run_seed_u64),
        "tick_u64": int(config.seed.tick_u64),
    }
    return _sha256_prefixed(canon_bytes(material))


def _q32_mul(lhs_q32: int, rhs_q32: int) -> int:
    return (int(lhs_q32) * int(rhs_q32)) >> 32


def run_grpo_ttc_v1(
    *,
    config: TTCGrpoRunConfigV1,
    run_root: Path,
    policy: PolicyLike | None = None,
    dmpl_eval_harness: DmplEvalHarnessV1 | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    if str(config.base_model.backend).strip().lower() != "mlx":
        _fail("SCHEMA_FAIL:BASE_MODEL_BACKEND")

    out_root = Path(run_root).resolve()
    store = CandidateStore(out_root)
    cfg_hash = store.write_config(config_payload(config))

    producer_run_id = _producer_run_id(config)
    base_seed = (int(config.seed.run_seed_u64) ^ ((int(config.seed.tick_u64) * _GOLDEN_RATIO_U64) & _Q64_MASK)) & _Q64_MASK

    if policy is None:
        policy_init_seed_u64 = _derive_seed_u64(
            base_seed_u64=int(base_seed),
            outer_iter_u64=0,
            in_group_index_u64=0,
            producer_run_id=str(producer_run_id),
            candidate_index_u64=0,
        )
        policy = PolicyMlxV1(
            model_id=str(config.base_model.model_id),
            model_path=str(config.base_model.model_path),
            adapter_state_path=(out_root / "model" / "lora_adapter_state_v1.json").resolve(),
            init_seed_u64=int(policy_init_seed_u64),
            lora_enabled_b=bool(config.lora.enabled_b),
            lora_rank_u64=int(config.lora.rank_u64),
            lora_alpha_u64=int(config.lora.alpha_u64),
            lora_target_modules=tuple(str(row) for row in config.lora.target_modules),
            trust_remote_code_b=False,
        )

    if dmpl_eval_harness is None:
        dmpl_eval_harness = DmplEvalHarnessV1(
            store=store,
            dmpl_campaign_id=str(config.dmpl_eval.campaign_id),
            reward_from_cac_field=str(config.dmpl_eval.reward_from_cac_field),
            budget={
                "beam_width_u64": int(config.dmpl_eval.budget.beam_width_u64),
                "max_nodes_u64": int(config.dmpl_eval.budget.max_nodes_u64),
            },
            require_real_dmpl_b=False,
        )

    best_index = 0
    best_ir_hash = "sha256:" + ("0" * 64)
    best_cac_hash = "sha256:" + ("0" * 64)
    best_reward = _MIN_REWARD_Q32

    rewards_all: list[int] = []
    n_valid = 0
    n_evaluated = 0
    candidate_index_u64 = 0

    store.append_log(
        event="run_start",
        payload={
            "tick_u64": int(config.seed.tick_u64),
            "producer_run_id": str(producer_run_id),
            "config_hash": str(cfg_hash),
        },
    )

    outer_iters = int(config.optimization.num_outer_iters_u64)
    target_candidates = int(config.sampling.num_candidates_u64)
    group_size = int(config.sampling.group_size_u64)
    if int(outer_iters) * int(group_size) < int(target_candidates):
        _fail("SCHEMA_FAIL:INSUFFICIENT_OUTER_CAPACITY")

    for outer in range(outer_iters):
        if candidate_index_u64 >= target_candidates:
            break

        group_texts: list[str] = []
        group_rewards: list[int] = []
        group_indices: list[int] = []

        for in_group_idx in range(group_size):
            if candidate_index_u64 >= target_candidates:
                break

            seed_u64 = _derive_seed_u64(
                base_seed_u64=int(base_seed),
                outer_iter_u64=int(outer),
                in_group_index_u64=int(in_group_idx),
                producer_run_id=str(producer_run_id),
                candidate_index_u64=int(candidate_index_u64),
            )
            prompt = build_task_prompt_v1(
                tick_u64=int(config.seed.tick_u64),
                producer_run_id=str(producer_run_id),
                candidate_index_u64=int(candidate_index_u64),
            )

            text = policy.generate_ir_text(
                prompt=prompt,
                seed_u64=int(seed_u64),
                temperature_q16=int(config.sampling.temperature_q16),
                top_p_q16=int(config.sampling.top_p_q16),
                max_new_tokens_u64=int(config.sampling.max_new_tokens_u64),
            )

            ir_obj, parse_error = parse_polymath_restricted_ir_v1(text)
            if parse_error is not None or ir_obj is None:
                reward_q32 = int(_MIN_REWARD_Q32)
                eval_payload = {
                    "schema_id": "ttc_grpo_candidate_eval_v1",
                    "id": "sha256:" + ("0" * 64),
                    "tick_u64": int(config.seed.tick_u64),
                    "candidate_index_u64": int(candidate_index_u64),
                    "candidate_ir_hash": None,
                    "dmpl_plan_result_hash": None,
                    "cac_hash": None,
                    "reward_q32": int(reward_q32),
                    "valid_ir_b": False,
                    "parse_error": str(parse_error),
                    "gen": {
                        "seed_u64": int(seed_u64),
                        "temperature_q16": int(config.sampling.temperature_q16),
                        "top_p_q16": int(config.sampling.top_p_q16),
                    },
                }
                store.write_candidate_eval(eval_payload)
                rewards_all.append(int(reward_q32))
                store.append_log(
                    event="candidate_parse_fail",
                    payload={
                        "candidate_index_u64": int(candidate_index_u64),
                        "parse_error": str(parse_error),
                    },
                )
                candidate_index_u64 += 1
                continue

            n_valid += 1
            ir_hash = store.write_ir(ir_obj)

            plan_hash: str | None = None
            cac_hash: str | None = None
            reward_q32 = int(_MIN_REWARD_Q32)
            dmpl_error: str | None = None
            try:
                plan_hash, cac_hash, reward_q32 = dmpl_eval_harness.dmpl_eval_candidate_v1(
                    candidate_ir_hash=str(ir_hash),
                    tick_u64=int(config.seed.tick_u64),
                    candidate_index_u64=int(candidate_index_u64),
                    seed_u64=int(seed_u64),
                )
                n_evaluated += 1
            except Exception as exc:  # noqa: BLE001
                dmpl_error = f"DMPL_EVAL_FAIL:{exc.__class__.__name__}"
                reward_q32 = int(_MIN_REWARD_Q32)

            eval_payload = {
                "schema_id": "ttc_grpo_candidate_eval_v1",
                "id": "sha256:" + ("0" * 64),
                "tick_u64": int(config.seed.tick_u64),
                "candidate_index_u64": int(candidate_index_u64),
                "candidate_ir_hash": str(ir_hash),
                "dmpl_plan_result_hash": str(plan_hash) if plan_hash else None,
                "cac_hash": str(cac_hash) if cac_hash else None,
                "reward_q32": int(reward_q32),
                "valid_ir_b": True,
                "parse_error": dmpl_error,
                "gen": {
                    "seed_u64": int(seed_u64),
                    "temperature_q16": int(config.sampling.temperature_q16),
                    "top_p_q16": int(config.sampling.top_p_q16),
                },
            }
            store.write_candidate_eval(eval_payload)

            rewards_all.append(int(reward_q32))
            if plan_hash and cac_hash:
                group_texts.append(str(text))
                group_rewards.append(int(reward_q32))
                group_indices.append(int(candidate_index_u64))
                if int(reward_q32) > int(best_reward):
                    best_reward = int(reward_q32)
                    best_index = int(candidate_index_u64)
                    best_ir_hash = str(ir_hash)
                    best_cac_hash = str(cac_hash)

            candidate_index_u64 += 1

        if group_texts:
            r_mean_q32 = _mean_q32(group_rewards)
            advantages_q32 = [_clip_q32(int(rew) - int(r_mean_q32), -_ADV_CLIP_Q32, _ADV_CLIP_Q32) for rew in group_rewards]

            # Deterministic group loss trace for post-run forensics.
            loss_q32 = 0
            for text, adv_q32 in zip(group_texts, advantages_q32):
                logp_q32 = int(policy.model_logprob_q32(text))
                loss_q32 += int(-_q32_mul(int(adv_q32), int(logp_q32)))
            store.append_log(
                event="group_update",
                payload={
                    "outer_iter_u64": int(outer),
                    "group_candidate_indices": [int(row) for row in group_indices],
                    "group_mean_reward_q32": int(r_mean_q32),
                    "group_loss_q32": int(loss_q32),
                },
            )

            policy.apply_grpo_update(
                texts=group_texts,
                advantages_q32=advantages_q32,
                learning_rate_q16=int(config.optimization.learning_rate_q16),
                kl_beta_q16=int(config.optimization.kl_beta_q16),
                clip_range_q16=int(config.optimization.clip_range_q16),
            )

    if not rewards_all:
        rewards_all = [int(_MIN_REWARD_Q32)]

    reward_stats = {
        "mean_q32": int(_mean_q32(rewards_all)),
        "p50_q32": int(_quantile_q32(rewards_all, pct=50)),
        "p90_q32": int(_quantile_q32(rewards_all, pct=90)),
        "max_q32": int(max(rewards_all)),
    }

    created = str(created_at_utc).strip() if created_at_utc is not None else _now_rfc3339_utc()
    receipt_payload = {
        "schema_id": "ttc_grpo_run_receipt_v1",
        "id": "sha256:" + ("0" * 64),
        "tick_u64": int(config.seed.tick_u64),
        "producer_run_id": str(producer_run_id),
        "config_hash": str(cfg_hash),
        "num_candidates_u64": int(target_candidates),
        "num_valid_u64": int(n_valid),
        "num_evaluated_u64": int(n_evaluated),
        "best": {
            "candidate_index_u64": int(best_index),
            "candidate_ir_hash": str(best_ir_hash),
            "cac_hash": str(best_cac_hash),
            "reward_q32": int(best_reward),
        },
        "reward_stats": dict(reward_stats),
        "artifacts": {
            "candidate_eval_index_jsonl_hash": "sha256:" + ("0" * 64),
            "logs_hash": "sha256:" + ("0" * 64),
        },
        "created_at_utc": str(created),
    }

    store.append_log(
        event="run_end",
        payload={
            "best_reward_q32": int(best_reward),
            "num_candidates_u64": int(target_candidates),
        },
    )
    receipt = store.write_run_receipt(receipt_payload)
    return receipt


def run_from_campaign_pack(*, campaign_pack: Path, out_dir: Path) -> dict[str, Any]:
    pack = json.loads(Path(campaign_pack).resolve().read_text(encoding="utf-8"))
    if not isinstance(pack, dict):
        _fail("SCHEMA_FAIL")
    if str(pack.get("schema_version", "")).strip() != "rsi_proposer_arena_grpo_ttc_pack_v1":
        _fail("SCHEMA_FAIL")
    if str(pack.get("install_intent", "")).strip() != "STATUS_SHADOW":
        _fail("SCHEMA_FAIL:INSTALL_INTENT")

    rel = str(pack.get("ttc_grpo_run_config_rel", "")).strip()
    if not rel:
        _fail("SCHEMA_FAIL")

    root = Path(__file__).resolve().parents[2]
    config_path = (root / rel).resolve()
    cfg = load_grpo_config_v1(config_path)
    run_root = (Path(out_dir).resolve() / "daemon" / "rsi_proposer_arena_grpo_ttc_v1" / "state" / "ttc_grpo").resolve()
    return run_grpo_ttc_v1(config=cfg, run_root=run_root)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ttc_grpo_runner_v1")
    parser.add_argument("--config", required=False)
    parser.add_argument("--campaign_pack", required=False)
    parser.add_argument("--out_dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    out_dir = Path(args.out_dir).resolve()

    if args.campaign_pack:
        receipt = run_from_campaign_pack(campaign_pack=Path(args.campaign_pack).resolve(), out_dir=out_dir)
    else:
        if not args.config:
            _fail("CONFIG_REQUIRED")
        config = load_grpo_config_v1(Path(args.config).resolve())
        run_root = (out_dir / "ttc_grpo").resolve()
        receipt = run_grpo_ttc_v1(config=config, run_root=run_root)

    print(
        json.dumps(
            {
                "receipt_id": str(receipt.get("id", "")),
                "receipt_tick_u64": int(receipt.get("tick_u64", 0)),
                "num_candidates_u64": int(receipt.get("num_candidates_u64", 0)),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
