from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from orchestrator.omega_v19_0 import coordinator_v1


def _write_axis_gate_failure(path: Path, *, outcome: str, detail: str) -> None:
    payload = {
        "detail": detail,
        "outcome": outcome,
        "schema_name": "axis_gate_failure_v1",
        "schema_version": "v19_0",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _dispatch_ctx(*, root: Path, promotion_dir_rel: str) -> dict[str, Any]:
    subrun_root = root / "subrun"
    dispatch_dir = root / "dispatch"
    subrun_root.mkdir(parents=True, exist_ok=True)
    dispatch_dir.mkdir(parents=True, exist_ok=True)
    return {
        "subrun_root_abs": subrun_root,
        "dispatch_dir": dispatch_dir,
        "campaign_entry": {
            "promotion_bundle_rel": f"{promotion_dir_rel}/*.dummy.json",
        },
    }


def test_axis_gate_loader_prefers_subrun_promotion_dir(tmp_path: Path) -> None:
    promotion_dir_rel = "daemon/rsi_omega_daemon_v19_0/state/promotion"
    dispatch_ctx = _dispatch_ctx(root=tmp_path, promotion_dir_rel=promotion_dir_rel)

    _write_axis_gate_failure(
        tmp_path / "subrun" / promotion_dir_rel / "axis_gate_failure_v1.json",
        outcome="SAFE_HALT",
        detail="subrun-first",
    )
    _write_axis_gate_failure(
        tmp_path / "dispatch" / "promotion" / "axis_gate_failure_v1.json",
        outcome="SAFE_SPLIT",
        detail="dispatch-second",
    )

    axis_gate = coordinator_v1._load_axis_gate_failure(dispatch_ctx)
    assert axis_gate is not None
    assert axis_gate["outcome"] == "SAFE_HALT"
    assert axis_gate["detail"] == "subrun-first"


def test_axis_gate_safe_halt_propagates_to_safe_halt_and_reason(tmp_path: Path) -> None:
    promotion_dir_rel = "promotion"
    dispatch_ctx = _dispatch_ctx(root=tmp_path, promotion_dir_rel=promotion_dir_rel)
    _write_axis_gate_failure(
        tmp_path / "subrun" / promotion_dir_rel / "axis_gate_failure_v1.json",
        outcome="SAFE_HALT",
        detail="J_DOMINANCE_FAILURE",
    )

    axis_gate = coordinator_v1._load_axis_gate_failure(dispatch_ctx)
    assert axis_gate is not None
    assert axis_gate["outcome"] == "SAFE_HALT"

    safe_halt = coordinator_v1._axis_gate_applies_safe_halt(axis_gate)
    promotion_reason_code = coordinator_v1._axis_gate_promotion_reason_code(axis_gate)

    assert safe_halt is True
    assert isinstance(promotion_reason_code, str)
    assert promotion_reason_code.startswith("AXIS_GATE_SAFE_HALT:")


def test_axis_gate_safe_split_propagates_without_forcing_halt(tmp_path: Path) -> None:
    promotion_dir_rel = "daemon/rsi_omega_daemon_v19_0/state/promotion"
    dispatch_ctx = _dispatch_ctx(root=tmp_path, promotion_dir_rel=promotion_dir_rel)
    _write_axis_gate_failure(
        tmp_path / "dispatch" / "promotion" / "axis_gate_failure_v1.json",
        outcome="SAFE_SPLIT",
        detail="SAFE_SPLIT:TREATY_SAFE_SPLIT",
    )

    axis_gate = coordinator_v1._load_axis_gate_failure(dispatch_ctx)
    assert axis_gate is not None
    assert axis_gate["outcome"] == "SAFE_SPLIT"

    safe_halt = coordinator_v1._axis_gate_applies_safe_halt(axis_gate)
    promotion_reason_code = coordinator_v1._axis_gate_promotion_reason_code(axis_gate)

    assert safe_halt is False
    assert isinstance(promotion_reason_code, str)
    assert promotion_reason_code.startswith("AXIS_GATE_SAFE_SPLIT:")
