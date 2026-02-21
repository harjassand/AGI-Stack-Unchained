"""Verifier wrapper for epistemic retention/hardening artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..v18_0.omega_common_v1 import OmegaV18Error, canon_hash_obj, fail
from .epistemic.compaction_v1 import verify_compaction_bundle
from .epistemic.retention_v1 import build_retention_artifacts


def _resolve_state(path: Path) -> Path:
    root = path.resolve()
    candidate = root / "daemon" / "rsi_epistemic_reduce_v1" / "state"
    if candidate.exists() and candidate.is_dir():
        return candidate
    if (root / "epistemic").is_dir():
        return root
    fail("SCHEMA_FAIL")
    return root


def _load_one(dir_path: Path, suffix: str) -> dict:
    rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix())
    if len(rows) != 1:
        fail("MISSING_STATE_INPUT")
    payload = json.loads(rows[0].read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if canon_hash_obj(payload) != "sha256:" + rows[0].name.split(".", 1)[0].split("_", 1)[1]:
        fail("NONDETERMINISTIC")
    return payload


def _load_by_id(dir_path: Path, suffix: str, *, id_field: str, expected_id: str) -> dict:
    target = str(expected_id).strip()
    rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix())
    matches: list[dict] = []
    for row in rows:
        payload = json.loads(row.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            fail("SCHEMA_FAIL")
        if canon_hash_obj(payload) != "sha256:" + row.name.split(".", 1)[0].split("_", 1)[1]:
            fail("NONDETERMINISTIC")
        if str(payload.get(id_field, "")) == target:
            matches.append(payload)
    if len(matches) != 1:
        fail("MISSING_STATE_INPUT")
    return matches[0]


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        fail("MODE_UNSUPPORTED")
    state_root = _resolve_state(state_dir)
    retention_dir = state_root / "epistemic" / "retention"

    policy = _load_one(retention_dir, "epistemic_retention_policy_v1.json")
    deletion = _load_one(retention_dir, "epistemic_deletion_plan_v1.json")
    sampling = _load_one(retention_dir, "epistemic_sampling_manifest_v1.json")
    summary = _load_one(retention_dir, "epistemic_summary_proof_v1.json")
    capsule = _load_one(state_root / "epistemic" / "capsules", "epistemic_capsule_v1.json")
    manifest = _load_one(state_root / "epistemic" / "world" / "manifests", "world_snapshot_manifest_v1.json")

    recomputed = build_retention_artifacts(
        retention_policy=policy,
        capsule=capsule,
        world_manifest=manifest,
        sampling_seed_u64=int(capsule.get("tick_u64", 0)),
    )
    if canon_hash_obj(recomputed["deletion_plan"]) != canon_hash_obj(deletion):
        fail("NONDETERMINISTIC")
    if canon_hash_obj(recomputed["sampling_manifest"]) != canon_hash_obj(sampling):
        fail("NONDETERMINISTIC")
    if canon_hash_obj(recomputed["summary_proof"]) != canon_hash_obj(summary):
        fail("NONDETERMINISTIC")

    execution_rows = sorted(
        retention_dir.glob("sha256_*.epistemic_compaction_execution_receipt_v1.json"),
        key=lambda p: p.as_posix(),
    )
    if execution_rows:
        execution = _load_one(retention_dir, "epistemic_compaction_execution_receipt_v1.json")
        witness_rows = sorted(
            retention_dir.glob("sha256_*.epistemic_compaction_witness_v1.json"),
            key=lambda p: p.as_posix(),
        )
        if not witness_rows:
            fail("MISSING_STATE_INPUT")
        witness = None
        for row in witness_rows:
            payload = json.loads(row.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                fail("SCHEMA_FAIL")
            if canon_hash_obj(payload) != "sha256:" + row.name.split(".", 1)[0].split("_", 1)[1]:
                fail("NONDETERMINISTIC")
            if int(payload.get("replay_floor_tick_u64", -1)) != int(execution.get("replay_floor_tick_u64", -2)):
                continue
            witness = payload
            break
        if not isinstance(witness, dict):
            fail("MISSING_STATE_INPUT")
        pack = _load_by_id(
            retention_dir,
            "epistemic_compaction_pack_manifest_v1.json",
            id_field="pack_manifest_id",
            expected_id=str(execution.get("pack_manifest_id", "")),
        )
        mapping = _load_by_id(
            retention_dir,
            "epistemic_compaction_mapping_manifest_v1.json",
            id_field="mapping_manifest_id",
            expected_id=str(execution.get("mapping_manifest_id", "")),
        )
        tombstone = _load_by_id(
            retention_dir,
            "epistemic_compaction_tombstone_manifest_v1.json",
            id_field="tombstone_manifest_id",
            expected_id=str(execution.get("tombstone_manifest_id", "")),
        )
        verify_compaction_bundle(
            state_root=state_root,
            execution_receipt=execution,
            witness=witness,
            pack_manifest=pack,
            mapping_manifest=mapping,
            tombstone_manifest=tombstone,
        )
    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_epistemic_retention_harden_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()
    try:
        print(verify(Path(args.state_dir), mode=str(args.mode)))
    except OmegaV18Error as exc:
        text = str(exc)
        if not text.startswith("INVALID:"):
            text = f"INVALID:{text}"
        print(text)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
