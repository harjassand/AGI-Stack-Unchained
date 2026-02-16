from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cdel.v1_7r.canon import canon_bytes, load_canon_json


def test_recursive_ontology_transfer_gate_blocks() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    target_inputs_path = (
        repo_root
        / "campaigns"
        / "rsi_real_recursive_ontology_v2_1_target"
        / "translation"
        / "translation_inputs_v2.json"
    )
    original = target_inputs_path.read_bytes()

    try:
        cases = []
        for idx, val in enumerate(range(0, 16)):
            cases.append(
                {
                    "case_id": f"unique_{idx:02d}",
                    "kind": "ctx_hash_repeat_v1",
                    "ctx_mode": "explicit",
                    "repeat": 1,
                    "active_ontology_id": "sha256:" + "0" * 64,
                    "active_snapshot_id": "sha256:" + "1" * 64,
                    "values": [val],
                }
            )
        payload = {"schema": "translation_inputs_v1", "schema_version": 1, "cases": cases}
        target_inputs_path.write_bytes(canon_bytes(payload) + b"\n")

        wrapper_pack = load_canon_json(
            repo_root
            / "campaigns"
            / "rsi_real_recursive_ontology_v2_1"
            / "rsi_real_recursive_ontology_pack_v1.json"
        )
        wrapper_pack["max_attempts_total"] = 1

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "recursive_run"
            pack_path = Path(tmp) / "wrapper_pack.json"
            pack_path.write_bytes(canon_bytes(wrapper_pack) + b"\n")

            env = os.environ.copy()
            env["PYTHONPATH"] = str(repo_root / "Extension-1" / "agi-orchestrator")

            cmd = [
                sys.executable,
                "-m",
                "orchestrator.rsi_recursive_ontology_v2_1",
                "--recursive_pack",
                str(pack_path),
                "--out_dir",
                str(out_dir),
            ]
            result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
            assert result.returncode != 0

            receipt = load_canon_json(out_dir / "diagnostics" / "rsi_recursive_ontology_receipt_v1.json")
            assert receipt.get("verdict") == "INVALID"

            report = load_canon_json(out_dir / "diagnostics" / "recursive_ontology_report_v1.json")
            assert int(report.get("attempts_executed", 0)) == 1
    finally:
        target_inputs_path.write_bytes(original)
