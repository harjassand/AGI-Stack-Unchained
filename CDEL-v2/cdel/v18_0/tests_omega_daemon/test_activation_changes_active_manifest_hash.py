from __future__ import annotations

import pytest

from cdel.v18_0.omega_common_v1 import write_hashed_json
from cdel.v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error, verify
from .utils import latest_file, load_json, run_tick_once, write_json


def test_activation_changes_active_manifest_hash(tmp_path) -> None:
    _, state_dir = run_tick_once(tmp_path, tick_u64=1)

    activation_payload = {
        "schema_version": "omega_activation_receipt_v1",
        "receipt_id": "sha256:" + "0" * 64,
        "tick_u64": 1,
        "before_active_manifest_hash": "sha256:" + "4" * 64,
        "after_active_manifest_hash": "sha256:" + "4" * 64,
        "healthcheck_suite_hash": "sha256:" + "3" * 64,
        "healthcheck_result": "PASS",
        "activation_method": "ATOMIC_POINTER_SWAP",
        "activation_success": True,
        "pass": True,
        "reasons": ["HEALTHCHECK_PASS"],
    }
    _, _, activation_hash = write_hashed_json(
        state_dir / "dispatch" / "fake" / "activation",
        "omega_activation_receipt_v1.json",
        activation_payload,
        id_field="receipt_id",
    )

    snapshot_path = latest_file(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snapshot = load_json(snapshot_path)
    snapshot["activation_receipt_hash"] = activation_hash
    write_json(snapshot_path, snapshot)

    with pytest.raises(OmegaV18Error, match="ACTIVATION_NO_MANIFEST_CHANGE"):
        verify(state_dir, mode="full")
