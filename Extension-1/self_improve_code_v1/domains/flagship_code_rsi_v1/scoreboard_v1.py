"""Run manifest and scoreboard helpers (v1.1)."""

from __future__ import annotations

from typing import Dict, List

from ...canon.json_canon_v1 import canon_bytes
from ...canon.hash_v1 import sha256_hex


def build_run_manifest(
    *,
    run_id: str,
    baseline_commit: str,
    config_hash: str,
    extension_commit: str,
    suite_ids: Dict[str, str],
) -> Dict:
    return {
        "schema_version": "flagship_code_rsi_v1_run_manifest",
        "run_id": run_id,
        "baseline_commit": baseline_commit,
        "config_hash": config_hash,
        "extension1_commit": extension_commit,
        "suite_ids": suite_ids,
    }


def init_scoreboard(run_id: str) -> Dict:
    return {
        "schema_version": "flagship_code_rsi_v1_scoreboard",
        "run_id": run_id,
        "epochs": [],
        "template_stats": {},
    }


def _ratio(num: int, den: int) -> str:
    if den <= 0:
        return "0/1"
    return f"{int(num)}/{int(den)}"


def update_scoreboard(
    scoreboard: Dict,
    epoch_summary: Dict,
    template_stats: Dict,
    costs: Dict,
    rolling_window: int,
) -> Dict:
    entry = {
        "epoch": int(epoch_summary.get("epoch", 0)),
        "tier": str(epoch_summary.get("curriculum", {}).get("tier", "")),
        "sealed_dev_passes": int(epoch_summary.get("sealed_passes", 0)),
        "sealed_dev_submissions": int(epoch_summary.get("topk_submitted", 0)),
        "sealed_heldout_passes": int(epoch_summary.get("sealed_heldout_passes", 0)),
        "null_control_pass": bool(epoch_summary.get("null_control_pass", False)),
        "noop_filtered": int(epoch_summary.get("noop_filtered", 0)),
        "noop_filtered_fraction": str(epoch_summary.get("noop_filtered_fraction", "0/1")),
        "improvement_events": int(epoch_summary.get("improvement_events", 0)),
        "top_template_ids": epoch_summary.get("top_template_ids", []),
        "costs": costs,
    }
    scoreboard.setdefault("epochs", []).append(entry)

    # Rolling pass rate
    window = max(1, int(rolling_window))
    recent = scoreboard["epochs"][-window:]
    pass_sum = sum(int(e.get("sealed_dev_passes", 0)) for e in recent)
    sub_sum = sum(int(e.get("sealed_dev_submissions", 0)) for e in recent)
    entry["sealed_dev_pass_rate_window"] = _ratio(pass_sum, max(1, sub_sum))

    scoreboard["template_stats"] = template_stats
    return scoreboard


def scoreboard_hash(scoreboard: Dict) -> str:
    return sha256_hex(canon_bytes(scoreboard))


__all__ = ["build_run_manifest", "init_scoreboard", "update_scoreboard", "scoreboard_hash"]
