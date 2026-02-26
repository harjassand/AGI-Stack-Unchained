from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.ttc_grpo.candidate_store_v1 import CandidateStore
from tools.ttc_grpo.dmpl_eval_harness_v1 import DmplEvalHarnessError, DmplEvalHarnessV1
from tools.ttc_grpo.grpo_runner_v1 import TTCGrpoRunnerError, run_from_campaign_pack, run_grpo_ttc_v1
from tools.ttc_grpo.ir_generator_v1 import deterministic_ir_from_seed
from tools.ttc_grpo.schemas import (
    BaseModelConfig,
    DmplEvalBudget,
    DmplEvalConfig,
    LoraConfig,
    OptimizationConfig,
    SamplingConfig,
    SeedConfig,
    TTCGrpoRunConfigV1,
)
import pytest


def _sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mk_config(*, num_candidates: int = 8, group_size: int = 4, outer_iters: int = 2) -> TTCGrpoRunConfigV1:
    return TTCGrpoRunConfigV1(
        schema_id="ttc_grpo_run_config_v1",
        id=_sha("cfg"),
        base_model=BaseModelConfig(
            backend="mlx",
            model_id="mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit",
            model_path="",
        ),
        lora=LoraConfig(
            enabled_b=True,
            rank_u64=16,
            alpha_u64=32,
            target_modules=("q_proj", "k_proj", "v_proj", "o_proj"),
        ),
        sampling=SamplingConfig(
            num_candidates_u64=int(num_candidates),
            group_size_u64=int(group_size),
            temperature_q16=6554,
            top_p_q16=62259,
            max_new_tokens_u64=256,
        ),
        optimization=OptimizationConfig(
            num_outer_iters_u64=int(outer_iters),
            learning_rate_q16=655,
            kl_beta_q16=655,
            clip_range_q16=13107,
        ),
        dmpl_eval=DmplEvalConfig(
            campaign_id="rsi_eudrs_u_dmpl_plan_v1",
            budget=DmplEvalBudget(beam_width_u64=64, max_nodes_u64=1000000),
            reward_from_cac_field="total_advantage_q32",
        ),
        seed=SeedConfig(run_seed_u64=7, tick_u64=42),
    )


class _DeterministicPolicy:
    def generate_ir_text(
        self,
        *,
        prompt: str,
        seed_u64: int,
        temperature_q16: int,
        top_p_q16: int,
        max_new_tokens_u64: int,
    ) -> str:
        obj = deterministic_ir_from_seed(
            seed_u64=int(seed_u64),
            candidate_index_u64=int(seed_u64 & 0xFFFF),
            producer_run_id="unit_test",
        )
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def model_logprob_q32(self, text: str) -> int:
        return int((int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16) - 0x80000000) << 1)

    def apply_grpo_update(
        self,
        *,
        texts: list[str],
        advantages_q32: list[int],
        learning_rate_q16: int,
        kl_beta_q16: int,
        clip_range_q16: int,
    ) -> None:
        return None


class _DeterministicEval:
    def dmpl_eval_candidate_v1(
        self,
        *,
        candidate_ir_hash: str,
        tick_u64: int,
        candidate_index_u64: int,
        seed_u64: int,
    ) -> tuple[str, str, int]:
        plan = _sha(f"plan|{candidate_ir_hash}|{tick_u64}|{candidate_index_u64}|{seed_u64}")
        cac = _sha(f"cac|{candidate_ir_hash}|{tick_u64}|{candidate_index_u64}|{seed_u64}")
        reward = int(int(hashlib.sha256(candidate_ir_hash.encode("utf-8")).hexdigest()[:8], 16) << 1)
        return plan, cac, reward


class _NoCallEval:
    def dmpl_eval_candidate_v1(
        self,
        *,
        candidate_ir_hash: str,
        tick_u64: int,
        candidate_index_u64: int,
        seed_u64: int,
    ) -> tuple[str, str, int]:
        raise AssertionError("DMPL evaluation should not be called for malformed IR")


class _IndexedRewardEval:
    def __init__(self, rewards: list[int]) -> None:
        self.rewards = list(rewards)

    def dmpl_eval_candidate_v1(
        self,
        *,
        candidate_ir_hash: str,
        tick_u64: int,
        candidate_index_u64: int,
        seed_u64: int,
    ) -> tuple[str, str, int]:
        idx = int(candidate_index_u64)
        reward = int(self.rewards[idx]) if idx < len(self.rewards) else int(self.rewards[-1])
        return _sha(f"plan|{idx}"), _sha(f"cac|{idx}"), reward


class _MalformedPolicy:
    def generate_ir_text(
        self,
        *,
        prompt: str,
        seed_u64: int,
        temperature_q16: int,
        top_p_q16: int,
        max_new_tokens_u64: int,
    ) -> str:
        return "{ not_valid_json"

    def model_logprob_q32(self, text: str) -> int:
        return 0

    def apply_grpo_update(
        self,
        *,
        texts: list[str],
        advantages_q32: list[int],
        learning_rate_q16: int,
        kl_beta_q16: int,
        clip_range_q16: int,
    ) -> None:
        return None


class _HashMismatchPolicy:
    def generate_ir_text(
        self,
        *,
        prompt: str,
        seed_u64: int,
        temperature_q16: int,
        top_p_q16: int,
        max_new_tokens_u64: int,
    ) -> str:
        obj = deterministic_ir_from_seed(
            seed_u64=int(seed_u64),
            candidate_index_u64=int(seed_u64 & 0xFFFF),
            producer_run_id="unit_test_hash_mismatch",
        )
        obj["ir_id"] = _sha("wrong_ir_id")
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def model_logprob_q32(self, text: str) -> int:
        return 0

    def apply_grpo_update(
        self,
        *,
        texts: list[str],
        advantages_q32: list[int],
        learning_rate_q16: int,
        kl_beta_q16: int,
        clip_range_q16: int,
    ) -> None:
        return None


def _eval_rows(run_root: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted((run_root / "candidate_eval").glob("sha256_*.ttc_grpo_candidate_eval_v1.json"), key=lambda p: p.as_posix()):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    rows.sort(key=lambda row: int(row.get("candidate_index_u64", 0)))
    return rows


def test_ttc_grpo_seed_determinism_same_seed_same_ir_hashes(tmp_path: Path) -> None:
    cfg = _mk_config(num_candidates=10, group_size=5, outer_iters=3)

    run1 = (tmp_path / "run1" / "ttc_grpo").resolve()
    run2 = (tmp_path / "run2" / "ttc_grpo").resolve()

    run_grpo_ttc_v1(
        config=cfg,
        run_root=run1,
        policy=_DeterministicPolicy(),
        dmpl_eval_harness=_DeterministicEval(),
        created_at_utc="2026-02-26T00:00:00Z",
    )
    run_grpo_ttc_v1(
        config=cfg,
        run_root=run2,
        policy=_DeterministicPolicy(),
        dmpl_eval_harness=_DeterministicEval(),
        created_at_utc="2026-02-26T00:00:00Z",
    )

    hashes1 = [row.get("candidate_ir_hash") for row in _eval_rows(run1)[:8]]
    hashes2 = [row.get("candidate_ir_hash") for row in _eval_rows(run2)[:8]]
    assert hashes1 == hashes2


def test_ttc_grpo_dmpl_eval_harness_synthetic_determinism(tmp_path: Path) -> None:
    store = CandidateStore((tmp_path / "state").resolve())
    harness = DmplEvalHarnessV1(
        store=store,
        dmpl_campaign_id="rsi_eudrs_u_dmpl_plan_v1",
        reward_from_cac_field="total_advantage_q32",
        budget={"beam_width_u64": 64, "max_nodes_u64": 1000000},
        require_real_dmpl_b=False,
    )

    ir_hash = _sha("candidate_ir")
    first = harness.dmpl_eval_candidate_v1(candidate_ir_hash=ir_hash, tick_u64=42, candidate_index_u64=3, seed_u64=11)
    second = harness.dmpl_eval_candidate_v1(candidate_ir_hash=ir_hash, tick_u64=42, candidate_index_u64=3, seed_u64=11)
    assert first == second


def test_ttc_grpo_malformed_ir_fail_closed(tmp_path: Path) -> None:
    cfg = _mk_config(num_candidates=3, group_size=3, outer_iters=1)
    run_root = (tmp_path / "malformed" / "ttc_grpo").resolve()

    run_grpo_ttc_v1(
        config=cfg,
        run_root=run_root,
        policy=_MalformedPolicy(),
        dmpl_eval_harness=_NoCallEval(),
        created_at_utc="2026-02-26T00:00:00Z",
    )

    rows = _eval_rows(run_root)
    assert rows
    for row in rows:
        assert row["valid_ir_b"] is False
        assert row["dmpl_plan_result_hash"] is None
        assert row["cac_hash"] is None
        assert isinstance(row["parse_error"], str)


def test_ttc_grpo_ir_id_mismatch_fail_closed(tmp_path: Path) -> None:
    cfg = _mk_config(num_candidates=2, group_size=2, outer_iters=1)
    run_root = (tmp_path / "id_mismatch" / "ttc_grpo").resolve()
    run_grpo_ttc_v1(
        config=cfg,
        run_root=run_root,
        policy=_HashMismatchPolicy(),
        dmpl_eval_harness=_NoCallEval(),
        created_at_utc="2026-02-26T00:00:00Z",
    )
    rows = _eval_rows(run_root)
    assert rows
    for row in rows:
        assert row["valid_ir_b"] is False
        assert row["dmpl_plan_result_hash"] is None
        assert row["cac_hash"] is None
        assert row["parse_error"] == "ID_MISMATCH"


def test_ttc_grpo_best_candidate_matches_max_reward(tmp_path: Path) -> None:
    rewards = [10, 5, 999, 17, -7, 100]
    cfg = _mk_config(num_candidates=6, group_size=3, outer_iters=2)
    run_root = (tmp_path / "best" / "ttc_grpo").resolve()

    receipt = run_grpo_ttc_v1(
        config=cfg,
        run_root=run_root,
        policy=_DeterministicPolicy(),
        dmpl_eval_harness=_IndexedRewardEval(rewards),
        created_at_utc="2026-02-26T00:00:00Z",
    )

    rows = _eval_rows(run_root)
    observed_max = max(int(row["reward_q32"]) for row in rows)
    observed_idx = [int(row["candidate_index_u64"]) for row in rows if int(row["reward_q32"]) == observed_max][0]

    assert int(receipt["best"]["reward_q32"]) == observed_max
    assert int(receipt["best"]["candidate_index_u64"]) == observed_idx


def test_ttc_grpo_run_receipt_verifier_structural_valid(tmp_path: Path) -> None:
    from cdel.v19_0.verify_ttc_grpo_run_receipt_v1 import verify

    cfg = _mk_config(num_candidates=4, group_size=2, outer_iters=2)
    run_root = (tmp_path / "verify" / "ttc_grpo").resolve()
    harness = DmplEvalHarnessV1(
        store=CandidateStore(run_root),
        dmpl_campaign_id="rsi_eudrs_u_dmpl_plan_v1",
        reward_from_cac_field="total_advantage_q32",
        budget={"beam_width_u64": 64, "max_nodes_u64": 1000000},
        require_real_dmpl_b=False,
    )

    run_grpo_ttc_v1(
        config=cfg,
        run_root=run_root,
        policy=_DeterministicPolicy(),
        dmpl_eval_harness=harness,
        created_at_utc="2026-02-26T00:00:00Z",
    )

    assert verify(run_root, mode="full") == "VALID"


def test_ttc_grpo_fails_closed_when_outer_capacity_insufficient(tmp_path: Path) -> None:
    cfg = _mk_config(num_candidates=10, group_size=3, outer_iters=3)
    run_root = (tmp_path / "capacity" / "ttc_grpo").resolve()
    with pytest.raises(TTCGrpoRunnerError, match="SCHEMA_FAIL:INSUFFICIENT_OUTER_CAPACITY"):
        run_grpo_ttc_v1(
            config=cfg,
            run_root=run_root,
            policy=_DeterministicPolicy(),
            dmpl_eval_harness=_DeterministicEval(),
            created_at_utc="2026-02-26T00:00:00Z",
        )


def test_ttc_grpo_dmpl_harness_fails_on_missing_reward_field(tmp_path: Path) -> None:
    store = CandidateStore((tmp_path / "state_reward_field").resolve())
    harness = DmplEvalHarnessV1(
        store=store,
        dmpl_campaign_id="rsi_eudrs_u_dmpl_plan_v1",
        reward_from_cac_field="missing_q32_field",
        budget={"beam_width_u64": 64, "max_nodes_u64": 1000000},
        require_real_dmpl_b=False,
    )
    with pytest.raises(DmplEvalHarnessError, match="SCHEMA_FAIL:reward_from_cac_field"):
        harness.dmpl_eval_candidate_v1(
            candidate_ir_hash=_sha("candidate_ir_reward_field"),
            tick_u64=42,
            candidate_index_u64=1,
            seed_u64=5,
        )


def test_ttc_grpo_campaign_pack_requires_shadow_install_intent(tmp_path: Path) -> None:
    bad_pack = {
        "schema_version": "rsi_proposer_arena_grpo_ttc_pack_v1",
        "install_intent": "STATUS_ACTIVE",
        "ttc_grpo_run_config_rel": "campaigns/rsi_proposer_arena_grpo_ttc_v1/ttc_grpo_run_config_v1.json",
    }
    pack_path = (tmp_path / "bad_pack.json").resolve()
    pack_path.write_text(json.dumps(bad_pack, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(TTCGrpoRunnerError, match="SCHEMA_FAIL:INSTALL_INTENT"):
        run_from_campaign_pack(campaign_pack=pack_path, out_dir=(tmp_path / "out").resolve())


def test_ttc_grpo_candidate_eval_verifier_structural_valid(tmp_path: Path) -> None:
    from cdel.v19_0.verify_ttc_grpo_candidate_eval_v1 import verify as verify_eval

    cfg = _mk_config(num_candidates=4, group_size=2, outer_iters=2)
    run_root = (tmp_path / "verify_eval" / "ttc_grpo").resolve()
    harness = DmplEvalHarnessV1(
        store=CandidateStore(run_root),
        dmpl_campaign_id="rsi_eudrs_u_dmpl_plan_v1",
        reward_from_cac_field="total_advantage_q32",
        budget={"beam_width_u64": 64, "max_nodes_u64": 1000000},
        require_real_dmpl_b=False,
    )

    run_grpo_ttc_v1(
        config=cfg,
        run_root=run_root,
        policy=_DeterministicPolicy(),
        dmpl_eval_harness=harness,
        created_at_utc="2026-02-26T00:00:00Z",
    )

    rows = _eval_rows(run_root)
    target_hash = str(rows[0]["id"])
    assert verify_eval(run_root, mode="full", candidate_eval_hash=target_hash) == "VALID"
