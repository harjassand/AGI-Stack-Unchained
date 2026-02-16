from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cdel.v1_9r.autonomy import load_translation_inputs, write_autonomy_outputs
from cdel.v1_7r.canon import load_canon_json, write_canon_json


def test_autonomy_manifest_verifier_rejects_tamper() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    run_dir = Path(tempfile.mkdtemp())

    translation_path = repo_root / "campaigns" / "rsi_real_demon_v5_autonomy" / "translation" / "translation_inputs_v1.json"
    translation_inputs = load_translation_inputs(translation_path)
    write_autonomy_outputs(run_dir=run_dir, translation_inputs=translation_inputs)

    campaign_pack_src = repo_root / "campaigns" / "rsi_real_demon_v5_autonomy" / "rsi_real_demon_campaign_pack_v5.json"
    pinned_path = run_dir / "current" / "campaign_pack" / "campaign_pack_used.json"
    write_canon_json(pinned_path, load_canon_json(campaign_pack_src))

    proposals_dir = run_dir / "autonomy" / "metabolism_v1" / "proposals"
    proposal_path = next(proposals_dir.glob("*.json"))
    tampered = load_canon_json(proposal_path)
    tampered["params"]["capacity"] = int(tampered["params"]["capacity"]) + 1
    write_canon_json(proposal_path, tampered)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "CDEL-v2")
    cmd = [
        sys.executable,
        "-m",
        "cdel.v1_9r.verify_rsi_demon_v5",
        "--state_dir",
        str(run_dir),
    ]
    result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
    assert result.returncode == 0
    out = result.stdout.strip()
    assert out.startswith("INVALID: AUTONOMY_PROPOSALS_DIR_MISMATCH") or out.startswith(
        "INVALID: AUTONOMY_ENUM_MISMATCH"
    )
