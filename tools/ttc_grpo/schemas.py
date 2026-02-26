from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Q16_ONE = 1 << 16
Q32_ONE = 1 << 32

U64_MAX = (1 << 64) - 1


def u64(value: Any, *, field: str) -> int:
    try:
        out = int(value)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"SCHEMA_FAIL:{field}") from exc
    if out < 0 or out > U64_MAX:
        raise ValueError(f"SCHEMA_FAIL:{field}")
    return int(out)


def i64(value: Any, *, field: str) -> int:
    try:
        out = int(value)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"SCHEMA_FAIL:{field}") from exc
    if out < -(1 << 63) or out > ((1 << 63) - 1):
        raise ValueError(f"SCHEMA_FAIL:{field}")
    return int(out)


def q16_to_f32(value_q16: int) -> float:
    return float(int(value_q16)) / float(Q16_ONE)


def q32_to_f64(value_q32: int) -> float:
    return float(int(value_q32)) / float(Q32_ONE)


@dataclass(frozen=True, slots=True)
class BaseModelConfig:
    backend: str
    model_id: str
    model_path: str


@dataclass(frozen=True, slots=True)
class LoraConfig:
    enabled_b: bool
    rank_u64: int
    alpha_u64: int
    target_modules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SamplingConfig:
    num_candidates_u64: int
    group_size_u64: int
    temperature_q16: int
    top_p_q16: int
    max_new_tokens_u64: int


@dataclass(frozen=True, slots=True)
class OptimizationConfig:
    num_outer_iters_u64: int
    learning_rate_q16: int
    kl_beta_q16: int
    clip_range_q16: int


@dataclass(frozen=True, slots=True)
class DmplEvalBudget:
    beam_width_u64: int
    max_nodes_u64: int


@dataclass(frozen=True, slots=True)
class DmplEvalConfig:
    campaign_id: str
    budget: DmplEvalBudget
    reward_from_cac_field: str


@dataclass(frozen=True, slots=True)
class SeedConfig:
    run_seed_u64: int
    tick_u64: int


@dataclass(frozen=True, slots=True)
class TTCGrpoRunConfigV1:
    schema_id: str
    id: str
    base_model: BaseModelConfig
    lora: LoraConfig
    sampling: SamplingConfig
    optimization: OptimizationConfig
    dmpl_eval: DmplEvalConfig
    seed: SeedConfig


@dataclass(frozen=True, slots=True)
class CandidateGenV1:
    seed_u64: int
    temperature_q16: int
    top_p_q16: int


@dataclass(frozen=True, slots=True)
class TTCGrpoCandidateEvalV1:
    schema_id: str
    id: str
    tick_u64: int
    candidate_index_u64: int
    candidate_ir_hash: str | None
    dmpl_plan_result_hash: str | None
    cac_hash: str | None
    reward_q32: int
    valid_ir_b: bool
    parse_error: str | None
    gen: CandidateGenV1


@dataclass(frozen=True, slots=True)
class TTCGrpoBestV1:
    candidate_index_u64: int
    candidate_ir_hash: str
    cac_hash: str
    reward_q32: int


@dataclass(frozen=True, slots=True)
class TTCGrpoRewardStatsV1:
    mean_q32: int
    p50_q32: int
    p90_q32: int
    max_q32: int


@dataclass(frozen=True, slots=True)
class TTCGrpoArtifactsV1:
    candidate_eval_index_jsonl_hash: str
    logs_hash: str


@dataclass(frozen=True, slots=True)
class TTCGrpoRunReceiptV1:
    schema_id: str
    id: str
    tick_u64: int
    producer_run_id: str
    config_hash: str
    num_candidates_u64: int
    num_valid_u64: int
    num_evaluated_u64: int
    best: TTCGrpoBestV1
    reward_stats: TTCGrpoRewardStatsV1
    artifacts: TTCGrpoArtifactsV1
    created_at_utc: str


__all__ = [
    "BaseModelConfig",
    "CandidateGenV1",
    "DmplEvalBudget",
    "DmplEvalConfig",
    "LoraConfig",
    "OptimizationConfig",
    "Q16_ONE",
    "Q32_ONE",
    "SamplingConfig",
    "SeedConfig",
    "TTCGrpoArtifactsV1",
    "TTCGrpoBestV1",
    "TTCGrpoCandidateEvalV1",
    "TTCGrpoRewardStatsV1",
    "TTCGrpoRunConfigV1",
    "TTCGrpoRunReceiptV1",
    "i64",
    "q16_to_f32",
    "q32_to_f64",
    "u64",
]
