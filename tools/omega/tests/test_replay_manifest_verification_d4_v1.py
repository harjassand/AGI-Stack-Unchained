from __future__ import annotations

import json
from pathlib import Path

from tools.omega.omega_replay_bundle_v1 import verify_existing_manifest, write_replay_manifest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_replay_manifest_verification_fails_on_mutation_d4_v1(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = run_dir / "OMEGA_GATE_PROOF_v1.json"
    _write_json(artifact_path, {"schema_version": "OMEGA_GATE_PROOF_v1", "ok_b": True})

    campaign_pack = tmp_path / "campaign_pack.json"
    _write_json(campaign_pack, {"schema_version": "rsi_omega_daemon_pack_v1"})

    write_replay_manifest(
        run_dir=run_dir,
        series_prefix="omega_test",
        profile="full",
        meta_core_mode="production",
        campaign_pack_path=campaign_pack,
        capability_registry_path=None,
        goal_queue_effective_path=None,
    )

    _write_json(artifact_path, {"schema_version": "OMEGA_GATE_PROOF_v1", "ok_b": False})

    ok_b, reason_code, details = verify_existing_manifest(run_dir)
    assert ok_b is False
    assert reason_code == "REPLAY_VERIFY_SHA_MISMATCH"
    assert details
