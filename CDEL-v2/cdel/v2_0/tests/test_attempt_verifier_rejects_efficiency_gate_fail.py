from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v2_0 import constants as v2_constants
from cdel.v2_0.autonomy import load_translation_inputs, write_autonomy_outputs


def test_attempt_verifier_rejects_efficiency_gate_fail() -> None:
    repo_root = Path(__file__).resolve().parents[4]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        meta_core = tmp_root / "meta-core"
        meta_const = meta_core / "meta_constitution" / "v2_0"
        meta_const_v1_7r = meta_core / "meta_constitution" / "v1_7r"
        kernel_dir = meta_core / "kernel" / "verifier"
        meta_const.mkdir(parents=True, exist_ok=True)
        meta_const_v1_7r.mkdir(parents=True, exist_ok=True)
        kernel_dir.mkdir(parents=True, exist_ok=True)

        base_constants = load_canon_json(repo_root / "meta-core" / "meta_constitution" / "v2_0" / "constants_v1.json")
        base_constants["RHO_MET_MIN_NUM"] = 1000
        base_constants["RHO_MET_MIN_DEN"] = 1
        write_canon_json(meta_const / "constants_v1.json", base_constants)
        (meta_const / "META_HASH").write_text("TEST_META_HASH", encoding="utf-8")
        (kernel_dir / "KERNEL_HASH").write_text("TEST_KERNEL_HASH", encoding="utf-8")

        onto_constants = load_canon_json(repo_root / "meta-core" / "meta_constitution" / "v1_7r" / "constants_v1.json")
        write_canon_json(meta_const_v1_7r / "constants_v1.json", onto_constants)
        (meta_const_v1_7r / "META_HASH").write_text("TEST_META_HASH_V1_7R", encoding="utf-8")

        prev_meta_core = os.environ.get("META_CORE_ROOT")
        os.environ["META_CORE_ROOT"] = str(meta_core)
        v2_constants.require_constants.cache_clear()
        v2_constants.meta_identities.cache_clear()

        run_dir = tmp_root / "attempt"
        run_dir.mkdir(parents=True, exist_ok=True)

        translation_path = (
            repo_root / "campaigns" / "rsi_real_demon_v6_efficiency" / "translation" / "translation_inputs_v1.json"
        )
        translation_inputs = load_translation_inputs(translation_path)
        write_autonomy_outputs(
            run_dir=run_dir,
            translation_inputs=translation_inputs,
            attempt_index=1,
            prior_attempt_index=0,
            prior_verifier_reason="",
        )

        campaign_pack_src = (
            repo_root / "campaigns" / "rsi_real_demon_v6_efficiency" / "rsi_real_demon_campaign_pack_v6.json"
        )

        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_root / "CDEL-v2")
        env["META_CORE_ROOT"] = str(meta_core)

        run_cmd = [
            sys.executable,
            "-m",
            "cdel.v2_0.run_rsi_campaign",
            "--mode",
            "real",
            "--strict-rsi",
            "--campaign_pack",
            str(campaign_pack_src),
            "--out_dir",
            str(run_dir),
        ]
        run_result = subprocess.run(run_cmd, env=env, check=False, capture_output=True, text=True)
        assert run_result.returncode == 0, run_result.stderr

        verify_cmd = [
            sys.executable,
            "-m",
            "cdel.v2_0.verify_rsi_demon_v6",
            "--state_dir",
            str(run_dir),
        ]
        verify_result = subprocess.run(verify_cmd, env=env, check=False, capture_output=True, text=True)
        assert verify_result.returncode == 0
        out = verify_result.stdout.strip()
        assert out == "INVALID: EFFICIENCY_GATE_FAIL"
        if prev_meta_core is None:
            os.environ.pop("META_CORE_ROOT", None)
        else:
            os.environ["META_CORE_ROOT"] = prev_meta_core
        v2_constants.require_constants.cache_clear()
        v2_constants.meta_identities.cache_clear()
