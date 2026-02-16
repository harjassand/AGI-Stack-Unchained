from __future__ import annotations

import json
from pathlib import Path

from tools.omega.omega_replay_bundle_v1 import write_replay_manifest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_replay_manifest_bytes_are_stable_d4_v1(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_json(run_dir / "OMEGA_OVERNIGHT_REPORT_v1.json", {"schema_version": "OMEGA_OVERNIGHT_REPORT_v1"})
    _write_json(run_dir / "OMEGA_GATE_PROOF_v1.json", {"schema_version": "OMEGA_GATE_PROOF_v1"})
    _write_json(run_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state" / "state.json", {"ok": True})

    campaign_pack = tmp_path / "campaign_pack.json"
    _write_json(campaign_pack, {"schema_version": "rsi_omega_daemon_pack_v1"})
    capability_registry = tmp_path / "omega_capability_registry_v2.json"
    _write_json(capability_registry, {"schema_version": "omega_capability_registry_v2", "capabilities": []})

    first_path = write_replay_manifest(
        run_dir=run_dir,
        series_prefix="omega_test",
        profile="full",
        meta_core_mode="production",
        campaign_pack_path=campaign_pack,
        capability_registry_path=capability_registry,
        goal_queue_effective_path=None,
    )
    first_bytes = first_path.read_bytes()

    second_path = write_replay_manifest(
        run_dir=run_dir,
        series_prefix="omega_test",
        profile="full",
        meta_core_mode="production",
        campaign_pack_path=campaign_pack,
        capability_registry_path=capability_registry,
        goal_queue_effective_path=None,
    )
    second_bytes = second_path.read_bytes()

    assert first_bytes == second_bytes
