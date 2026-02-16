#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT.parent))

from genesis.core.policy_search import run_policy_search, PolicyEvent  # noqa: E402
from genesis.capsules.world_model_builder import build_world_model_capsule  # noqa: E402
from genesis.promotion.promote import promote  # noqa: E402
from genesis.capsules.canonicalize import capsule_hash  # noqa: E402
from genesis.shadow_cdel.calibration import ShadowCalibrator  # noqa: E402
from genesis.shadow_cdel.nontriviality import margin_bucket  # noqa: E402
from genesis.tools.path_utils import normalize_config_paths  # noqa: E402


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def write_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def _runtime_bucket(duration_ms: int) -> str:
    if duration_ms < 50:
        return "rt_fast"
    if duration_ms < 200:
        return "rt_medium"
    return "rt_slow"


def _planning_config(config: dict) -> dict:
    return {
        "world_model_metric_name": config.get("planning_model_metric_name", "wm_accuracy"),
        "world_model_target": config.get("planning_model_target", -1.0),
        "world_model_direction": config.get("planning_model_direction", "maximize"),
        "world_model_risk_bound": config.get("planning_model_risk_bound", -1.0),
        "world_model_max_wall_time_ms": int(config.get("policy_max_wall_time_ms", 1000)),
        "world_model_max_memory_mb": int(config.get("policy_max_memory_mb", 256)),
        "world_model_max_sample_count": 0,
        "default_bid": config.get("default_bid"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis policy run")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config = load_config(Path(args.config))
    config = normalize_config_paths(
        config,
        ROOT,
        keys=[
            "run_log_path",
            "receipts_dir",
            "shadow_calibration_path",
            "protocol_budget_path",
        ],
    )
    cdel_url = os.getenv("CDEL_URL", "")
    if cdel_url:
        config["cdel_url"] = cdel_url

    epoch_id = config.get("epoch_id", "epoch-1")
    calibration_path = Path(config.get("shadow_calibration_path", str(ROOT / "shadow_calibration.json")))
    calibrator = ShadowCalibrator(
        path=calibration_path,
        base_margin=float(config.get("shadow_margin", 0.05)),
        step=float(config.get("shadow_margin_step", 0.02)),
        max_margin=float(config.get("shadow_margin_max", 0.2)),
    )
    config["shadow_margin"] = calibrator.margin_for_epoch(epoch_id)

    model_spec = config.get("planning_model_spec") or {
        "model_family": "logistic_regression",
        "weights": [1.0],
        "bias": 0.0,
    }
    model_capsule = build_world_model_capsule(model_spec, _planning_config(config))
    results = run_policy_search(config, model_capsule=model_capsule)
    events: list[PolicyEvent] = results["events"]

    log_path = Path(config.get("run_log_path", str(ROOT.parent / "genesis_run.jsonl")))
    receipts_dir = Path(config.get("receipts_dir", str(ROOT / "receipts")))
    state_path = receipts_dir / "promotion_state.json"

    max_promotions = int(config.get("promotions_max", 0))
    promoted = 0
    summary = {"shadow_pass": 0, "promoted_pass": 0, "promoted_fail": 0}

    for idx, event in enumerate(events):
        capsule = event.capsule
        shadow = event.shadow
        shadow_pass = shadow.decision == "PASS"
        if shadow_pass:
            summary["shadow_pass"] += 1

        record = {
            "artifact_type": "POLICY",
            "capsule_hash": capsule_hash(capsule),
            "operator": event.operator,
            "repair_depth": event.repair_depth,
            "shadow_decision": shadow.decision,
            "shadow_status": shadow.status,
            "shadow_return": shadow.return_value,
            "shadow_return_bound": shadow.return_bound,
            "shadow_return_threshold": shadow.return_threshold,
            "shadow_cost": shadow.cost_value,
            "shadow_cost_bound": shadow.cost_bound,
            "shadow_cost_threshold": shadow.cost_threshold,
            "shadow_runtime_bucket": _runtime_bucket(shadow.duration_ms),
            "forager_test_count": shadow.forager_test_count,
            "nontriviality_pass": getattr(shadow, "nontriviality_pass", None),
            "baseline_margin_bucket": margin_bucket(getattr(shadow, "baseline_margin", None)),
            "counterexample_id": event.counterexample_id,
            "epoch_id": epoch_id,
            "policy_family": event.descriptor.get("policy_family"),
            "param_bucket": event.descriptor.get("param_bucket"),
            "operator_history_sig": event.descriptor.get("operator_history_sig"),
        }

        if shadow_pass and promoted < max_promotions:
            outcome = promote(
                capsule,
                config,
                epoch_id,
                receipts_dir,
                state_path,
                shadow,
                config["shadow_margin"],
                descriptor=event.descriptor,
                iteration_idx=idx,
            )
            if outcome.get("promotion_attempted"):
                promoted += 1
                record["promotion_result"] = outcome["result"]
                record["bid"] = outcome.get("bid")
                record["promotion_attempted"] = True
                record["protocol_snapshot"] = outcome.get("protocol_snapshot")
                if outcome["result"] == "PASS":
                    summary["promoted_pass"] += 1
                    record["receipt_hash"] = outcome.get("receipt_hash", "")
                    record["audit_ref"] = outcome.get("audit_ref", "")
                else:
                    summary["promoted_fail"] += 1
                calibrator.record_outcome(epoch_id, shadow.decision, outcome["result"])
            else:
                record["promotion_result"] = "SKIP"
                record["bid"] = None
                record["promotion_attempted"] = False
                record["protocol_snapshot"] = outcome.get("protocol_snapshot")
                record["promotion_refusal_reason"] = outcome.get("refusal_reason")
        else:
            record["promotion_result"] = "SKIP"
            record["bid"] = None
            record["promotion_attempted"] = False

        write_jsonl(log_path, record)

    summary_path = Path("genesis_policy_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
