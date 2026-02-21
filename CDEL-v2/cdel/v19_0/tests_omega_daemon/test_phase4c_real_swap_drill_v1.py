from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v19_0.verify_rsi_omega_daemon_v1 import verify as verify_v19
from orchestrator.omega_v18_0.io_v1 import freeze_pack_config


def _latest_json(path: Path, suffix: str) -> Path:
    rows = sorted(path.glob(f"sha256_*.{suffix}"), key=lambda row: row.as_posix())
    assert rows, f"missing {suffix} under {path}"
    return rows[-1]


def _run_drill(out_dir_rel: Path) -> Path:
    if out_dir_rel.is_absolute():
        raise AssertionError("out_dir_rel must be repo-relative")
    cmd = [
        "python3",
        str(REPO_ROOT / "scripts" / "run_phase4c_real_swap_drill_v1.py"),
        "--out-dir",
        out_dir_rel.as_posix(),
        "--tick-base",
        "8100",
    ]
    proc = subprocess.run(  # noqa: S603
        cmd,
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, f"drill failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    lines = [row.strip() for row in proc.stdout.splitlines() if row.strip()]
    assert lines, "drill did not print summary path"
    summary_path = Path(lines[-1])
    if not summary_path.is_absolute():
        summary_path = (REPO_ROOT / summary_path).resolve()
    assert summary_path.exists(), f"missing summary file: {summary_path}"
    return summary_path


def test_phase4c_real_swap_drill_manifest_replay_valid(tmp_path: Path) -> None:
    out_dir_rel = Path("runs") / f"pytest_phase4c_real_swap_{tmp_path.name}"
    summary_path = _run_drill(out_dir_rel)
    summary = load_canon_json(summary_path)
    run_dir = (REPO_ROOT / str(summary["run_dir"])).resolve()
    state_root = run_dir / "shadow_tick" / "daemon" / "rsi_omega_daemon_v19_0" / "state"

    invariance_path = _latest_json(
        state_root / "shadow" / "invariance",
        "shadow_corpus_invariance_receipt_v1.json",
    )
    readiness_path = _latest_json(
        state_root / "shadow" / "readiness",
        "shadow_regime_readiness_receipt_v1.json",
    )
    invariance = load_canon_json(invariance_path)
    readiness = load_canon_json(readiness_path)
    pack = load_canon_json(run_dir / "shadow_config_v19" / "rsi_omega_daemon_pack_v1.json")

    assert str(invariance.get("graph_invariance_contract_id", "")) == str(
        pack.get("shadow_graph_invariance_contract_id", "")
    )
    assert str(invariance.get("type_binding_invariance_contract_id", "")) == str(
        pack.get("shadow_type_binding_invariance_contract_id", "")
    )
    assert str(invariance.get("cert_invariance_contract_id", "")) == str(
        pack.get("shadow_cert_invariance_contract_id", "")
    )
    assert str(readiness.get("corpus_invariance_receipt_id", "")) == str(invariance.get("receipt_id", ""))
    rollback_hash = str(readiness.get("rollback_evidence_hash", ""))
    assert rollback_hash.startswith("sha256:") and len(rollback_hash) == 71
    assert bool(readiness.get("rollback_plan_bound_b", False))

    assert verify_v19(state_root, mode="full") == "VALID"


def test_phase4c_shadow_pack_missing_pin_fail_closed(tmp_path: Path) -> None:
    source_campaign = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0_phase4d_epistemic_airlock"
    campaign_copy = tmp_path / "campaign"
    shutil.copytree(source_campaign, campaign_copy)
    pack_path = campaign_copy / "rsi_omega_daemon_pack_v1.json"

    pack = load_canon_json(pack_path)
    pack.pop("shadow_cert_profile_id", None)
    write_canon_json(pack_path, pack)

    with pytest.raises(Exception) as exc:
        freeze_pack_config(
            campaign_pack=pack_path,
            config_dir=tmp_path / "config",
        )
    assert "shadow_cert_profile_id" in str(exc.value)
