"""Run manifest builder (v1)."""

from __future__ import annotations

from typing import Dict, List, Tuple



def _get_baseline_commit(run_config: Dict) -> str:
    if isinstance(run_config.get("target_repo"), dict):
        return run_config.get("target_repo", {}).get("baseline_commit", "")
    return run_config.get("baseline_commit", "")


def _get_eval_plan_id(run_config: Dict) -> str:
    if "eval_plan_id" in run_config:
        return run_config.get("eval_plan_id", "")
    return run_config.get("target_repo", {}).get("eval_plan_id", "") if isinstance(run_config.get("target_repo"), dict) else ""

def rank_attempts(attempts: List[Dict]) -> List[Dict]:
    return sorted(
        attempts,
        key=lambda a: (-int(a.get("reward", 0)), str(a.get("candidate_id", ""))),
    )


def build_run_manifest(
    run_config: Dict,
    attempts: List[Dict],
    state_before_sha: str,
    state_after_sha: str,
    artifacts: Dict[str, Dict[str, str]],
    selected_candidate_id: str | None,
) -> Dict:
    ranked = rank_attempts(attempts)
    if not selected_candidate_id and ranked:
        selected_candidate_id = ranked[0].get("candidate_id", "")
    ranked_rows = []
    for idx, a in enumerate(ranked, start=1):
        cand_id = a.get("candidate_id", "")
        art = artifacts.get(cand_id, {})
        row = {
            "rank": idx,
            "candidate_id": cand_id,
            "arm_ids": a.get("arm_ids", []),
            "value_choices": a.get("value_choices", []),
            "status": a.get("status", ""),
            "m_bp": int(a.get("m_bp", 0)),
            "baseline_m_bp": int(a.get("baseline_m_bp", 0)),
            "reward": int(a.get("reward", 0)),
            "patch_sha256": art.get("patch_sha256", a.get("patch_sha256", "")),
            "tar_sha256": art.get("tar_sha256", ""),
            "selection_reason": a.get("selection_reason", ""),
        }
        ranked_rows.append(row)
    return {
        "schema_version": "run_manifest_v1",
        "baseline_commit": _get_baseline_commit(run_config),
        "eval_plan_id": _get_eval_plan_id(run_config),
        "state_before_sha256": state_before_sha,
        "state_after_sha256": state_after_sha,
        "selected_candidate_id": selected_candidate_id or "",
        "ranked_candidates": ranked_rows,
    }


__all__ = ["rank_attempts", "build_run_manifest"]
