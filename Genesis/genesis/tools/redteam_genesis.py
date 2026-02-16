from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from genesis.capsules.world_model_builder import build_world_model_capsule
from genesis.core.world_model_search import seed_model_specs
from genesis.promotion.promote import promote
from genesis.tools.path_utils import resolve_path


def _load_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _make_config(base: Dict[str, Any], run_dir: Path) -> Dict[str, Any]:
    cfg = json.loads(json.dumps(base))
    cfg["cdel_url"] = "http://127.0.0.1:1/evaluate"
    cfg["max_cdel_calls_per_epoch"] = 0
    cfg["promotions_max"] = 0
    cfg["protocol_budget_path"] = str(run_dir / "protocol_budget.json")
    cfg["receipts_dir"] = str(run_dir / "receipts")
    cfg["local_budget"] = {
        "alpha_total": "0",
        "epsilon_total": "0",
        "delta_total": "0",
        "compute_total_units": 0,
    }
    return cfg


def run(out_path: Path) -> Dict[str, Any]:
    base_cfg = _load_config(resolve_path("configs/world_model.json", ROOT))
    run_dir = Path(tempfile.mkdtemp(prefix="genesis_redteam_"))
    cfg = _make_config(base_cfg, run_dir)

    model_spec = seed_model_specs(cfg)[0]
    capsule = build_world_model_capsule(model_spec, cfg)

    results = {"status": "PASS", "cases": []}

    outcome = promote(
        capsule,
        cfg,
        epoch_id=cfg.get("epoch_id", "epoch-1"),
        receipts_dir=Path(cfg["receipts_dir"]),
        state_path=Path(cfg["receipts_dir"]) / "promotion_state.json",
        shadow_result=None,
        shadow_margin=0.0,
        descriptor={"descriptor_sig": "redteam"},
        iteration_idx=0,
    )
    results["cases"].append(
        {
            "case": "call_cap_refusal",
            "promotion_attempted": outcome.get("promotion_attempted"),
            "refusal_reason": outcome.get("refusal_reason"),
        }
    )
    if outcome.get("promotion_attempted"):
        results["status"] = "FAIL"

    outcome2 = promote(
        capsule,
        cfg,
        epoch_id=cfg.get("epoch_id", "epoch-1"),
        receipts_dir=Path(cfg["receipts_dir"]),
        state_path=Path(cfg["receipts_dir"]) / "promotion_state.json",
        shadow_result=None,
        shadow_margin=0.0,
        descriptor={"descriptor_sig": "redteam"},
        iteration_idx=1,
    )
    results["cases"].append(
        {
            "case": "repeat_refusal",
            "promotion_attempted": outcome2.get("promotion_attempted"),
            "refusal_reason": outcome2.get("refusal_reason"),
        }
    )
    if outcome2.get("promotion_attempted"):
        results["status"] = "FAIL"

    _write_json(out_path, results)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis red-team runner")
    parser.add_argument("--out", default="GENESIS_REDTEAM_REPORT.json")
    args = parser.parse_args()
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = (ROOT.parent / out_path).resolve()
    report = run(out_path)
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
