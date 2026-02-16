from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cdel.v1_7r.canon import load_canon_json


def test_recursive_ontology_two_concepts_requires_call() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    pack = repo_root / "campaigns" / "rsi_real_recursive_ontology_v2_1" / "rsi_real_recursive_ontology_pack_v1.json"

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "recursive_run"

        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root / "Extension-1" / "agi-orchestrator")

        cmd = [
            sys.executable,
            "-m",
            "orchestrator.rsi_recursive_ontology_v2_1",
            "--recursive_pack",
            str(pack),
            "--out_dir",
            str(out_dir),
        ]
        result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "VALID"

        receipt = load_canon_json(out_dir / "diagnostics" / "rsi_recursive_ontology_receipt_v1.json")
        accepted = receipt.get("accepted_concepts", [])
        assert len(accepted) >= 2
        assert any(entry.get("uses_recursive_call") for entry in accepted)
