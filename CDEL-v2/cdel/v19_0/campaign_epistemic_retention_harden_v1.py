"""Campaign wrapper for epistemic retention/hardening verification (R7 baseline)."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..v18_0.omega_common_v1 import fail
from .epistemic.compaction_v1 import execute_compaction_campaign
from .epistemic.retention_v1 import build_retention_artifacts


def run(*, out_dir: Path) -> dict:
    import json

    state_root = out_dir.resolve() / "daemon" / "rsi_epistemic_reduce_v1" / "state"
    if not state_root.exists() or not state_root.is_dir():
        fail("MISSING_STATE_INPUT")

    retention_dir = state_root / "epistemic" / "retention"
    policy_rows = sorted(retention_dir.glob("sha256_*.epistemic_retention_policy_v1.json"), key=lambda p: p.as_posix())
    if len(policy_rows) != 1:
        fail("MISSING_STATE_INPUT")
    policy = json.loads(policy_rows[0].read_text(encoding="utf-8"))
    if not isinstance(policy, dict):
        fail("SCHEMA_FAIL")

    capsule_rows = sorted((state_root / "epistemic" / "capsules").glob("sha256_*.epistemic_capsule_v1.json"), key=lambda p: p.as_posix())
    manifest_rows = sorted(
        (state_root / "epistemic" / "world" / "manifests").glob("sha256_*.world_snapshot_manifest_v1.json"),
        key=lambda p: p.as_posix(),
    )
    if len(capsule_rows) != 1 or len(manifest_rows) != 1:
        fail("MISSING_STATE_INPUT")
    capsule = json.loads(capsule_rows[0].read_text(encoding="utf-8"))
    manifest = json.loads(manifest_rows[0].read_text(encoding="utf-8"))
    if not isinstance(capsule, dict) or not isinstance(manifest, dict):
        fail("SCHEMA_FAIL")
    artifacts = build_retention_artifacts(
        retention_policy=policy,
        capsule=capsule,
        world_manifest=manifest,
        sampling_seed_u64=int(capsule.get("tick_u64", 0)),
    )
    replay_floor_tick_u64 = int(capsule.get("tick_u64", 0))
    floor_override = __import__("os").environ.get("OMEGA_REPLAY_FLOOR_TICK_U64")
    if floor_override is not None and str(floor_override).strip():
        replay_floor_tick_u64 = int(str(floor_override).strip())
    compaction = execute_compaction_campaign(
        state_root=state_root,
        replay_floor_tick_u64=replay_floor_tick_u64,
    )
    return {
        "status": "OK",
        "deletion_plan_id": str((artifacts.get("deletion_plan") or {}).get("plan_id", "")),
        "sampling_manifest_id": str((artifacts.get("sampling_manifest") or {}).get("manifest_id", "")),
        "summary_proof_id": str((artifacts.get("summary_proof") or {}).get("proof_id", "")),
        "compaction_execution_receipt_id": str(compaction.get("execution_receipt_id", "")),
        "compaction_witness_id": str(compaction.get("witness_id", "")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="campaign_epistemic_retention_harden_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    _ = Path(args.campaign_pack)
    result = run(out_dir=Path(args.out_dir))
    print(result.get("status", "OK"))


if __name__ == "__main__":
    main()
