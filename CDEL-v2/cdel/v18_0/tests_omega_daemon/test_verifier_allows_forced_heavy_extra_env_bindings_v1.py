from __future__ import annotations

import json

from cdel.v18_0.omega_common_v1 import write_hashed_json
from cdel.v18_0.verify_rsi_omega_daemon_v1 import verify
from .utils import latest_file, load_json, repo_root, run_tick_with_pack, write_json


def test_verifier_allows_forced_heavy_extra_env_bindings_v1(tmp_path) -> None:
    pack = repo_root() / "campaigns" / "rsi_omega_daemon_v18_0_prod" / "rsi_omega_daemon_pack_v1.json"
    _, state_dir = run_tick_with_pack(tmp_path=tmp_path, campaign_pack=pack, tick_u64=1)

    dispatch_path = latest_file(state_dir / "dispatch", "*/sha256_*.omega_dispatch_receipt_v1.json")
    dispatch = load_json(dispatch_path)
    invocation = dispatch.get("invocation")
    assert isinstance(invocation, dict)
    env_overrides = dict(invocation.get("env_overrides") or {})

    env_overrides["OMEGA_SH1_FAILED_SHAPE_BAN_JSON"] = json.dumps(
        [
            {
                "shape_id": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "target_relpath": "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json",
            }
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    env_overrides["OMEGA_SH1_LAST_FAILURE_HINT_JSON"] = json.dumps(
        {
            "debt_key": "frontier:rsi_ge_sh1_optimizer",
            "failed_threshold_code": "WIRING_CLASS_REQUIRED",
            "nontriviality_cert_v1": None,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    env_overrides["OMEGA_SH1_WIRING_LOCUS_RELPATH"] = "orchestrator/omega_v18_0/goal_synthesizer_v1.py"
    dispatch["invocation"]["env_overrides"] = env_overrides
    _, _, dispatch_hash = write_hashed_json(dispatch_path.parent, "omega_dispatch_receipt_v1.json", dispatch)

    snapshot_path = latest_file(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snapshot = load_json(snapshot_path)
    snapshot["dispatch_receipt_hash"] = dispatch_hash
    write_json(snapshot_path, snapshot)

    assert verify(state_dir, mode="full") == "VALID"
