"""Curriculum ladder and tier calibration (v1.1)."""

from __future__ import annotations

from typing import Dict, List, Tuple


_DEFAULT_LADDER = [
    {
        "name": "t0",
        "sealed_dev_plan": "code_agentic_v1_dev_ladder_t0",
        "devscreen_suite": "code_agentic_dev_t0",
    },
    {
        "name": "t1",
        "sealed_dev_plan": "code_agentic_v1_dev_ladder_t1",
        "devscreen_suite": "code_agentic_dev_t1",
    },
    {
        "name": "t2",
        "sealed_dev_plan": "code_agentic_v1_dev_ladder_t2",
        "devscreen_suite": "code_agentic_dev_t2",
    },
]


def ladder_from_config(cfg: Dict) -> List[Dict]:
    ladder = cfg.get("ladder")
    if isinstance(ladder, list) and ladder:
        out: List[Dict] = []
        for idx, entry in enumerate(ladder):
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", f"t{idx}"))
            sealed = str(entry.get("sealed_dev_plan", ""))
            devscreen = str(entry.get("devscreen_suite", ""))
            out.append({"name": name, "sealed_dev_plan": sealed, "devscreen_suite": devscreen})
        if out:
            return out
    return [dict(item) for item in _DEFAULT_LADDER]


def _parse_threshold(rule: Dict) -> Tuple[int, int]:
    value = rule.get("threshold", 0)
    if isinstance(value, int):
        return int(value), 1
    if isinstance(value, str):
        if "/" in value:
            num, den = value.split("/", 1)
            return int(num), max(1, int(den))
        if "." in value:
            parts = value.split(".")
            whole = parts[0] or "0"
            frac = parts[1] if len(parts) > 1 else ""
            den = 10 ** len(frac)
            num = int(whole) * den + (int(frac) if frac else 0)
            return num, den
        return int(value), 1
    return int(value * 10000), 10000


def select_active_tier(ladder: List[Dict], baseline_results: List[Dict]) -> Dict:
    all_pass = True
    all_fail = True
    chosen_index = 0
    chosen_status = "FAIL"
    for idx, tier in enumerate(ladder):
        status = "FAIL"
        if idx < len(baseline_results):
            status = str(baseline_results[idx].get("status", "FAIL"))
        if status == "PASS":
            all_fail = False
            continue
        chosen_index = idx
        chosen_status = status
        all_pass = False
        break
    if not ladder:
        return {"tier": "", "tier_index": 0, "baseline_status": "FAIL", "all_pass": False, "all_fail": True}
    if all_pass:
        chosen_index = len(ladder) - 1
        chosen_status = "PASS"
        all_fail = False
    return {
        "tier": ladder[chosen_index]["name"],
        "tier_index": int(chosen_index),
        "baseline_status": chosen_status,
        "all_pass": bool(all_pass),
        "all_fail": bool(all_fail),
    }


def init_state(active: Dict) -> Dict:
    return {
        "tier": str(active.get("tier", "")),
        "tier_index": int(active.get("tier_index", 0)),
        "epochs_in_tier": 0,
        "epochs_without_pass": 0,
        "submissions_in_tier": 0,
    }


def tier_info(ladder: List[Dict], state: Dict) -> Dict:
    idx = int(state.get("tier_index", 0))
    if idx < 0:
        idx = 0
    if idx >= len(ladder):
        idx = len(ladder) - 1 if ladder else 0
    return ladder[idx] if ladder else {"name": "", "sealed_dev_plan": "", "devscreen_suite": ""}


def update_state(
    curriculum_cfg: Dict,
    ladder: List[Dict],
    state: Dict,
    sealed_passes: int,
    sealed_submissions: int,
    null_control_pass: bool,
) -> Tuple[Dict, List[str]]:
    notes: List[str] = []
    epochs_in_tier = int(state.get("epochs_in_tier", 0)) + 1
    submissions_in_tier = int(state.get("submissions_in_tier", 0)) + int(sealed_submissions)
    epochs_without_pass = int(state.get("epochs_without_pass", 0))
    if int(sealed_passes) > 0:
        epochs_without_pass = 0
    else:
        epochs_without_pass += 1

    rule = curriculum_cfg.get("advance_rule", {}) if isinstance(curriculum_cfg.get("advance_rule", {}), dict) else {}
    min_epochs = int(rule.get("min_epochs", 1))
    threshold_num, threshold_den = _parse_threshold(rule)
    min_submissions = int(curriculum_cfg.get("min_submissions_before_advancing", 0))
    deescalate_after = int(curriculum_cfg.get("deescalate_after_epochs", 3))

    idx = int(state.get("tier_index", 0))
    advance_reason = ""

    if null_control_pass and idx + 1 < len(ladder):
        idx += 1
        advance_reason = "null_control"
    else:
        pass_rate_ok = False
        if sealed_submissions > 0 and threshold_den > 0:
            pass_rate_ok = sealed_passes * threshold_den >= threshold_num * sealed_submissions
        if pass_rate_ok and epochs_in_tier >= min_epochs and submissions_in_tier >= min_submissions:
            if idx + 1 < len(ladder):
                idx += 1
                advance_reason = "pass_rate"
        if not advance_reason and epochs_without_pass >= deescalate_after and idx > 0:
            idx -= 1
            advance_reason = "deescalate"

    if advance_reason:
        epochs_in_tier = 0
        submissions_in_tier = 0
        epochs_without_pass = 0
        notes.append(f"tier_{advance_reason}")

    tier_name = ladder[idx]["name"] if ladder else ""
    return (
        {
            "tier": tier_name,
            "tier_index": int(idx),
            "epochs_in_tier": int(epochs_in_tier),
            "epochs_without_pass": int(epochs_without_pass),
            "submissions_in_tier": int(submissions_in_tier),
        },
        notes,
    )


__all__ = [
    "ladder_from_config",
    "select_active_tier",
    "init_state",
    "tier_info",
    "update_state",
]
