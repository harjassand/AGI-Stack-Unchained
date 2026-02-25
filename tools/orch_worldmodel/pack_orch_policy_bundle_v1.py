#!/usr/bin/env python3
"""Pack orchestration policy tables into content-addressed policy bundles (v1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from cdel.v1_7r.canon import canon_bytes, write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj


class PackError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise PackError(str(reason))


def _is_sha256(value: Any) -> bool:
    raw = str(value).strip()
    return raw.startswith("sha256:") and len(raw) == 71 and all(ch in "0123456789abcdef" for ch in raw.split(":", 1)[1])


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PackError("SCHEMA_FAIL") from exc
    if not isinstance(payload, dict):
        _fail("SCHEMA_FAIL")
    return payload


def _ensure_out_root(out_root: Path, *, repo_root: Path) -> None:
    out_abs = out_root.resolve()
    try:
        rel = out_abs.relative_to(repo_root.resolve())
    except Exception as exc:
        raise PackError("OUT_ROOT_INVALID") from exc
    parts = rel.parts
    if len(parts) < 2 or parts[0] != "daemon" or parts[1] != "orch_policy":
        _fail("OUT_ROOT_INVALID")


def _to_repo_rel(path: Path, *, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.resolve().as_posix()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _write_blob_immutable(*, blobs_dir: Path, digest: str, suffix: str, data: bytes) -> Path:
    if not _is_sha256(digest):
        _fail("SCHEMA_FAIL")
    hexd = digest.split(":", 1)[1]
    path = blobs_dir / f"sha256_{hexd}.{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_file():
        if path.read_bytes() != data:
            _fail("IMMUTABLE_BLOB_CONFLICT")
    else:
        path.write_bytes(data)
    return path


def pack_orch_policy_bundle(
    *,
    policy_table_path: Path,
    train_config_path: Path,
    transition_dataset_manifest_path: Path,
    out_root: Path,
    notes: str,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    root = (repo_root or _REPO_ROOT).resolve()
    out_abs = out_root.resolve()

    _ensure_out_root(out_abs, repo_root=root)

    policy_table_payload = _load_json(policy_table_path.resolve())
    if str(policy_table_payload.get("schema_version", "")).strip() != "orch_policy_table_v1":
        _fail("SCHEMA_FAIL")
    policy_no_id = dict(policy_table_payload)
    policy_no_id.pop("policy_id", None)
    policy_id = str(canon_hash_obj(policy_no_id))
    if str(policy_table_payload.get("policy_id", "")).strip() not in {"", policy_id}:
        _fail("POLICY_ID_MISMATCH")
    policy_table_payload = dict(policy_no_id)
    policy_table_payload["policy_id"] = policy_id
    policy_table_bytes = canon_bytes(policy_table_payload)

    train_config_payload = _load_json(train_config_path.resolve())
    if str(train_config_payload.get("schema_version", "")).strip() != "orch_worldmodel_train_config_v1":
        _fail("SCHEMA_FAIL")
    train_config_id = str(canon_hash_obj(train_config_payload))

    dataset_manifest_payload = _load_json(transition_dataset_manifest_path.resolve())
    if str(dataset_manifest_payload.get("schema_version", "")).strip() != "orch_transition_dataset_manifest_v1":
        _fail("SCHEMA_FAIL")
    transition_dataset_manifest_id = str(dataset_manifest_payload.get("dataset_manifest_id", "")).strip()
    if not _is_sha256(transition_dataset_manifest_id):
        _fail("SCHEMA_FAIL")

    ek_id = str(policy_table_payload.get("ek_id", "")).strip()
    kernel_ledger_id = str(policy_table_payload.get("kernel_ledger_id", "")).strip()
    if not _is_sha256(ek_id) or not _is_sha256(kernel_ledger_id):
        _fail("SCHEMA_FAIL")

    blobs_dir = out_abs / "store" / "blobs" / "sha256"
    manifests_dir = out_abs / "store" / "manifests"
    blobs_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    policy_blob_id = "sha256:" + hashlib.sha256(policy_table_bytes).hexdigest()

    policy_blob_path = _write_blob_immutable(
        blobs_dir=blobs_dir,
        digest=policy_blob_id,
        suffix="orch_policy_table_v1.json",
        data=policy_table_bytes,
    )

    policy_table_relpath = _to_repo_rel(policy_blob_path, repo_root=root)

    train_config_sha = _sha256_file(train_config_path.resolve())
    dataset_manifest_sha = _sha256_file(transition_dataset_manifest_path.resolve())

    bundle_no_id = {
        "schema_version": "orch_policy_bundle_v1",
        "ek_id": str(ek_id),
        "kernel_ledger_id": str(kernel_ledger_id),
        "train_config_id": str(train_config_id),
        "transition_dataset_manifest_id": str(transition_dataset_manifest_id),
        "policy_table_id": str(policy_id),
        "policy_table_relpath": str(policy_table_relpath),
        "artifacts": [
            {
                "relpath": str(policy_table_relpath),
                "sha256": str(policy_blob_id),
            },
            {
                "relpath": _to_repo_rel(train_config_path.resolve(), repo_root=root),
                "sha256": str(train_config_sha),
            },
            {
                "relpath": _to_repo_rel(transition_dataset_manifest_path.resolve(), repo_root=root),
                "sha256": str(dataset_manifest_sha),
            },
        ],
        "notes": str(notes),
    }
    bundle_id = str(canon_hash_obj(bundle_no_id))
    bundle_payload = dict(bundle_no_id)
    bundle_payload["bundle_id"] = bundle_id

    bundle_path = manifests_dir / f"sha256_{bundle_id.split(':', 1)[1]}.orch_policy_bundle_v1.json"
    write_canon_json(bundle_path, bundle_payload)

    plain_policy_path = out_abs / "orch_policy_table_v1.json"
    plain_bundle_path = out_abs / "orch_policy_bundle_v1.json"
    write_canon_json(plain_policy_path, policy_table_payload)
    write_canon_json(plain_bundle_path, bundle_payload)

    return {
        "bundle_id": str(bundle_id),
        "bundle_manifest_path": bundle_path.as_posix(),
        "policy_table_blob_id": str(policy_blob_id),
        "policy_table_blob_path": policy_blob_path.as_posix(),
        "plain_policy_table_path": plain_policy_path.as_posix(),
        "plain_bundle_path": plain_bundle_path.as_posix(),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pack_orch_policy_bundle_v1")
    parser.add_argument("--policy_table", required=True)
    parser.add_argument("--train_config", required=True)
    parser.add_argument("--transition_dataset_manifest", required=True)
    parser.add_argument("--out_root", required=True)
    parser.add_argument("--notes", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    summary = pack_orch_policy_bundle(
        policy_table_path=Path(str(args.policy_table)).resolve(),
        train_config_path=Path(str(args.train_config)).resolve(),
        transition_dataset_manifest_path=Path(str(args.transition_dataset_manifest)).resolve(),
        out_root=Path(str(args.out_root)).resolve(),
        notes=str(args.notes),
    )
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
