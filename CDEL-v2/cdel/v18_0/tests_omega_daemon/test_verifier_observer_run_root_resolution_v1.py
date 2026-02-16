from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0 import verify_rsi_omega_daemon_v1 as verifier
from cdel.v18_0.omega_common_v1 import OmegaV18Error, canon_hash_obj, write_canon_json


def test_observer_source_lookup_accepts_explicit_run_roots_for_worktree_layout(tmp_path: Path) -> None:
    worktree_root = tmp_path / "_worktree"
    worktree_root.mkdir(parents=True, exist_ok=True)

    run_dir = tmp_path / "phase_u1_g1_example"
    perf_dir = run_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state" / "perf"
    perf_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": "omega_tick_perf_v1",
        "total_ns": 1,
        "stage_ns": {"run_subverifier": 0, "run_promotion": 0},
    }
    artifact_hash = canon_hash_obj(payload)
    artifact_hex = artifact_hash.split(":", 1)[1]
    artifact_path = perf_dir / f"sha256_{artifact_hex}.omega_tick_perf_v1.json"
    write_canon_json(artifact_path, payload)

    source = {
        "schema_id": "omega_tick_perf_v1",
        "artifact_hash": artifact_hash,
        "producer_campaign_id": "rsi_omega_daemon_v18_0",
        "producer_run_id": run_dir.name,
    }

    with pytest.raises(OmegaV18Error):
        verifier._read_observer_source_artifact(root=worktree_root, source=source)

    schema_id, got_payload = verifier._read_observer_source_artifact(
        root=worktree_root,
        source=source,
        runs_roots=[run_dir, run_dir.parent],
    )
    assert schema_id == "omega_tick_perf_v1"
    assert got_payload == payload
