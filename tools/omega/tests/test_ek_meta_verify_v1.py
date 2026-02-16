from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _canon_bytes(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _write_canon(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canon_bytes(payload))


def test_ek_meta_verify_passes_for_equal_or_monotone_safe_ek(tmp_path: Path) -> None:
    old_ek = {
        "schema_version": "evaluation_kernel_v1",
        "ek_version": 1,
        "obs_schema_ids": ["https://genesis.engine/specs/v18_0/omega_observation_report_v1"],
        "obs_canon_id": "sha256:" + ("1" * 64),
        "boundary_event_set_id": "sha256:46447887d799e38e9858ebdb844bebd75d7179d68dd232b382467b340b7c6404",
        "stages": [
            {"stage_name": "REALIZE"},
            {"stage_name": "SCORE"},
            {"stage_name": "FINAL_AUDIT"},
        ],
        "scoring_impl": {
            "kind": "OMEGA_BENCHMARK_SUITE",
            "code_ref": {"commit_hash": "abc1234", "path": "tools/omega/omega_benchmark_suite_v1.py"},
            "applicability_preds_id": "sha256:" + ("2" * 64),
            "ek_meta_tests_id": "sha256:" + ("3" * 64),
        },
    }
    new_ek = dict(old_ek)
    new_ek["stages"] = [
        {"stage_name": "REALIZE"},
        {"stage_name": "SCORE"},
        {"stage_name": "FINAL_AUDIT"},
        {"stage_name": "FINAL_AUDIT"},
    ]

    old_path = tmp_path / "old_ek.json"
    new_path = tmp_path / "new_ek.json"
    out_path = tmp_path / "ek_meta_verify_receipt_v1.json"
    _write_canon(old_path, old_ek)
    _write_canon(new_path, new_ek)

    golden = tmp_path / "golden"
    _write_canon(
        golden / "run_0001" / "omega_observation_report_v1.json",
        {
            "schema_version": "omega_observation_report_v1",
            "report_id": "sha256:" + ("4" * 64),
            "tick_u64": 1,
            "active_manifest_hash": "sha256:" + ("5" * 64),
            "metrics": {},
        },
    )

    tool = Path(__file__).resolve().parents[1] / "ek_meta_verify_v1.py"
    cmd = [
        sys.executable,
        str(tool),
        "--old_ek_path",
        str(old_path),
        "--new_ek_path",
        str(new_path),
        "--golden_runs_root",
        str(golden),
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    receipt = json.loads(out_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == "ek_meta_verify_receipt_v1"
    assert receipt["result"]["status"] == "PASS"
