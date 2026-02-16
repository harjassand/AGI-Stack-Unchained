from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError, load_canon_json
from cdel.v2_2.code_patch import tree_hash_v1
from cdel.v2_2.constants import require_constants
from cdel.v2_2.verify_rsi_demon_v8 import verify as verify_attempt


def test_csi_bench_output_hash_match_required(csi_run_dir: Path, tmp_path: Path) -> None:
    run_copy = tmp_path / "run_copy"
    shutil.copytree(csi_run_dir, run_copy)

    attempt_dir = run_copy / "attempts" / "attempt_0001"
    candidate_tree = attempt_dir / "candidate_tree"

    bench_api = candidate_tree / "Extension-1" / "agi-orchestrator" / "orchestrator" / "csi" / "bench_api_v1.py"
    text = bench_api.read_text(encoding="utf-8")
    if "marker" not in text:
        text = text.replace(
            "    return outputs\n",
            "    for case_id in outputs:\n        outputs[case_id][\"marker\"] = \"x\"\n\n    return outputs\n",
        )
        bench_api.write_text(text, encoding="utf-8")

    constants = require_constants()
    allowed_roots = list(constants.get("CSI_ALLOWED_ROOTS", []))
    immutable_paths = list(constants.get("CSI_IMMUTABLE_PATHS", []))

    tree_hash = tree_hash_v1(candidate_tree, allowed_roots, immutable_paths)
    manifest = load_canon_json(attempt_dir / "csi_manifest_v1.json")

    suite_path = candidate_tree / "Extension-1" / "agi-orchestrator" / "orchestrator" / "csi" / "bench_suite_v1.json"
    inputs_path = candidate_tree / "Extension-1" / "agi-orchestrator" / "orchestrator" / "csi" / "bench_inputs_v1.json"

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(candidate_tree / "Extension-1" / "agi-orchestrator"),
            str(candidate_tree / "CDEL-v2"),
        ]
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [
        sys.executable,
        "-m",
        "cdel.v2_2.csi_bench",
        "--suite",
        str(suite_path),
        "--inputs",
        str(inputs_path),
        "--run_id",
        str(manifest.get("run_id")),
        "--attempt_id",
        str(manifest.get("attempt_id")),
        "--tree_hash",
        tree_hash,
        "--out",
        str(attempt_dir / "patch_bench_report_v1.json"),
    ]
    result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout

    with pytest.raises(CanonError) as excinfo:
        verify_attempt(attempt_dir)
    assert "CSI_OUTPUT_MISMATCH" in str(excinfo.value)
