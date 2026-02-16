"""C-MECH benchmark evaluation helpers for v1.6r."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .canon import canon_bytes, hash_json, load_canon_json, sha256_prefixed
from .eval_runner import eval_instance
from .family_dsl.runtime import compute_family_id, compute_signature

BENCH_FRONTIER_HASH = "sha256:" + "0" * 64


def _apply_mech_patch(base_mech_payload: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    policy_program = patch.get("policy_program")
    if not isinstance(policy_program, dict):
        raise ValueError("mech_patch missing policy_program")
    policy_name = policy_program.get("name")
    if not isinstance(policy_name, str):
        raise ValueError("mech_patch policy_program missing name")
    mech = dict(base_mech_payload)
    definitions = list(mech.get("definitions", [])) if isinstance(mech.get("definitions"), list) else []
    definitions = [item for item in definitions if item.get("name") != policy_name]
    definitions.append(policy_program)
    mech["definitions"] = definitions
    mech["candidate_symbol"] = policy_name
    mech["baseline_symbol"] = policy_name
    mech["oracle_symbol"] = policy_name
    return mech


def _family_from_suite_row(suite_row: dict[str, Any], max_steps_default: int) -> dict[str, Any]:
    max_steps = suite_row.get("max_steps")
    if not isinstance(max_steps, int) or max_steps <= 0:
        max_steps = max_steps_default
    family = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": int(max_steps),
            "max_instance_bytes": 4096,
            "max_instantiation_gas": 10000,
            "max_shrink_gas": 10000,
        },
        "instantiator": {"op": "CONST", "value": {"suite_row": suite_row}},
    }
    family["signature"] = compute_signature(family)
    family["family_id"] = compute_family_id(family)
    return family


def _score_tuple(metrics: dict[str, Any], worstcase_steps: int) -> tuple[int, int, int, int]:
    return (
        int(metrics.get("episodes_solved", 0)),
        -int(worstcase_steps),
        -int(metrics.get("env_steps_total", 0)),
        -int(metrics.get("bytes_hashed_total", 0)),
    )


def _evaluate_instances(
    *,
    suite_rows: list[dict[str, Any]],
    mech: dict[str, Any],
    epoch_id: str,
    epoch_key: bytes,
    budget_env_steps: int,
    budget_bytes_hashed: int,
) -> tuple[dict[str, int], int, bool]:
    episodes_total = 0
    episodes_solved = 0
    env_steps_total = 0
    bytes_hashed_total = 0
    verifier_gas_total = 0
    worstcase_steps = 0
    budget_exceeded = False

    epoch_commit = {
        "commitment": "sha256:" + epoch_key.hex(),
        "frontier_hash": BENCH_FRONTIER_HASH,
    }

    for suite_row in suite_rows:
        episodes_total += 1
        family = _family_from_suite_row(suite_row, max_steps_default=16)
        success, trace, work_delta, _failure_kind, _inst_hash, _instance_spec = eval_instance(
            epoch_id=epoch_id,
            family=family,
            theta={},
            epoch_commit=epoch_commit,
            base_mech=mech,
            receipt_hash=sha256_prefixed(canon_bytes({"epoch": epoch_id, "family": family.get("family_id", "")})),
            epoch_key=epoch_key,
        )
        if success == 1:
            episodes_solved += 1
        steps_to_solve = len(trace) if success == 1 else None
        max_steps = suite_row.get("max_steps")
        if not isinstance(max_steps, int) or max_steps <= 0:
            max_steps = 16
        unsolved_penalty = max_steps + 1
        case_steps = steps_to_solve if steps_to_solve is not None else unsolved_penalty
        if case_steps > worstcase_steps:
            worstcase_steps = case_steps
        env_steps_total += int(work_delta.get("env_steps_total", 0)) if isinstance(work_delta, dict) else 0
        bytes_hashed_total += int(work_delta.get("bytes_hashed_total", 0)) if isinstance(work_delta, dict) else 0
        verifier_gas_total += int(work_delta.get("verifier_gas_total", 0)) if isinstance(work_delta, dict) else 0
        if env_steps_total > budget_env_steps or bytes_hashed_total > budget_bytes_hashed:
            budget_exceeded = True
            break

    metrics = {
        "episodes_total": int(episodes_total),
        "episodes_solved": int(episodes_solved),
        "env_steps_total": int(env_steps_total),
        "bytes_hashed_total": int(bytes_hashed_total),
        "verifier_gas_total": int(verifier_gas_total),
    }
    return metrics, worstcase_steps, budget_exceeded


def compute_mech_patch_eval_cert(
    *,
    epoch_id: str,
    patch: dict[str, Any],
    base_mech: dict[str, Any],
    benchmark_pack: dict[str, Any],
    base_patch_set_hash: str,
    benchmark_pack_hash: str,
) -> tuple[dict[str, Any], list[tuple[int, int, int, int]]]:
    patch_id = patch.get("patch_id") or hash_json(patch)
    patch_hash = hash_json(patch)
    candidate_mech = _apply_mech_patch(base_mech, patch)

    cases_out: list[dict[str, Any]] = []
    case_deltas: list[tuple[int, int, int, int]] = []
    any_strict_gain = False
    any_regression = False

    for case in benchmark_pack.get("cases", []) if isinstance(benchmark_pack, dict) else []:
        case_id = case.get("case_id")
        inst_pack_path = case.get("instance_pack_path")
        epoch_key = case.get("epoch_key")
        budget = case.get("budget", {}) if isinstance(case.get("budget"), dict) else {}
        budget_env_steps = int(budget.get("max_env_steps_total", 0))
        budget_bytes = int(budget.get("max_bytes_hashed_total", 0))
        if not isinstance(case_id, str) or not isinstance(inst_pack_path, str) or not isinstance(epoch_key, str):
            continue
        inst_pack = load_canon_json(Path(inst_pack_path))
        suite_rows = inst_pack.get("instances", []) if isinstance(inst_pack, dict) else []
        suite_rows = [row for row in suite_rows if isinstance(row, dict)]
        epoch_key_bytes = bytes.fromhex(epoch_key.split(":", 1)[1]) if ":" in epoch_key else bytes.fromhex(epoch_key)

        base_metrics, base_worst, base_budget_exceeded = _evaluate_instances(
            suite_rows=suite_rows,
            mech=base_mech,
            epoch_id=epoch_id,
            epoch_key=epoch_key_bytes,
            budget_env_steps=budget_env_steps,
            budget_bytes_hashed=budget_bytes,
        )
        new_metrics, new_worst, new_budget_exceeded = _evaluate_instances(
            suite_rows=suite_rows,
            mech=candidate_mech,
            epoch_id=epoch_id,
            epoch_key=epoch_key_bytes,
            budget_env_steps=budget_env_steps,
            budget_bytes_hashed=budget_bytes,
        )

        base_score = _score_tuple(base_metrics, base_worst)
        new_score = _score_tuple(new_metrics, new_worst)
        case_pass = new_score >= base_score and not base_budget_exceeded and not new_budget_exceeded
        reason_codes: list[str] = []
        if base_budget_exceeded or new_budget_exceeded:
            reason_codes.append("BUDGET_EXCEEDED")
            any_regression = True
        if new_score < base_score:
            reason_codes.append("MECH_PATCH_REGRESSION")
        if new_score > base_score:
            any_strict_gain = True
        if new_score < base_score:
            any_regression = True
        case_deltas.append(
            (
                new_score[0] - base_score[0],
                new_score[1] - base_score[1],
                new_score[2] - base_score[2],
                new_score[3] - base_score[3],
            )
        )
        cases_out.append(
            {
                "case_id": case_id,
                "base_metrics": base_metrics,
                "new_metrics": new_metrics,
                "pass": bool(case_pass),
                "reason_codes": reason_codes,
            }
        )

    overall_reasons: list[str] = []
    if any_regression:
        overall_reasons.append("MECH_PATCH_REGRESSION")
    if not any_strict_gain:
        overall_reasons.append("MECH_PATCH_NO_STRICT_GAIN")
    overall_pass = not any_regression and any_strict_gain

    cert = {
        "schema": "mech_patch_eval_cert_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "patch_id": patch_id,
        "patch_hash": patch_hash,
        "base_patch_set_hash": base_patch_set_hash,
        "benchmark_pack_hash": benchmark_pack_hash,
        "cases": cases_out,
        "overall": {"pass": bool(overall_pass), "selected": False, "reason_codes": overall_reasons},
    }
    return cert, case_deltas
