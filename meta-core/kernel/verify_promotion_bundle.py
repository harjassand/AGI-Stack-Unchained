#!/usr/bin/env python3
"""Promotion bundle verifier wrapper (Rust kernel verifier)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


def _canon_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canon_hash(payload: object) -> str:
    return f"sha256:{hashlib.sha256(_canon_bytes(payload)).hexdigest()}"


def _load_canon_json(path: Path) -> dict:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("CONTINUITY_SCHEMA_FAIL")
    if raw.rstrip(b"\n") != _canon_bytes(payload):
        raise RuntimeError("CONTINUITY_SCHEMA_FAIL")
    return payload


def _verify_declared_id(payload: dict, id_field: str) -> None:
    declared = str(payload.get(id_field, "")).strip()
    if not declared.startswith("sha256:"):
        raise RuntimeError("CONTINUITY_ID_MISMATCH")
    no_id = dict(payload)
    no_id.pop(id_field, None)
    if _canon_hash(no_id) != declared:
        raise RuntimeError("CONTINUITY_ID_MISMATCH")


def _validate_artifact_ref(path: Path, ref: object) -> dict:
    if not isinstance(ref, dict):
        raise RuntimeError("CONTINUITY_SCHEMA_FAIL")
    artifact_id = str(ref.get("artifact_id", "")).strip()
    artifact_relpath = str(ref.get("artifact_relpath", "")).strip()
    if not artifact_id.startswith("sha256:") or not artifact_relpath:
        raise RuntimeError("CONTINUITY_SCHEMA_FAIL")
    target = (path / artifact_relpath).resolve()
    try:
        target.relative_to(path.resolve())
    except ValueError as exc:
        raise RuntimeError("CONTINUITY_MISSING_ARTIFACT") from exc
    if not target.exists() or not target.is_file():
        raise RuntimeError("CONTINUITY_MISSING_ARTIFACT")
    payload = _load_canon_json(target)
    if _canon_hash(payload) != artifact_id:
        raise RuntimeError("CONTINUITY_ID_MISMATCH")
    return payload


def _enforce_continuity_sidecar(bundle_dir: Path) -> None:
    axis_path = bundle_dir / "omega" / "axis_upgrade_bundle_v1.json"
    if not axis_path.exists() or not axis_path.is_file():
        return

    axis_payload = _load_canon_json(axis_path)
    if str(axis_payload.get("schema_name", "")) != "axis_upgrade_bundle_v1":
        raise RuntimeError("CONTINUITY_SCHEMA_FAIL")
    _verify_declared_id(axis_payload, "axis_bundle_id")

    for key in ("sigma_old_ref", "sigma_new_ref", "objective_J_profile_ref"):
        _validate_artifact_ref(bundle_dir, axis_payload.get(key))
    for key in ("regime_old_ref", "regime_new_ref"):
        regime = axis_payload.get(key)
        if not isinstance(regime, dict):
            raise RuntimeError("CONTINUITY_SCHEMA_FAIL")
        for slot in ("C", "K", "E", "W", "T"):
            _validate_artifact_ref(bundle_dir, regime.get(slot))

    morphisms = axis_payload.get("morphisms")
    if not isinstance(morphisms, list) or not morphisms:
        raise RuntimeError("CONTINUITY_SCHEMA_FAIL")
    for row in morphisms:
        if not isinstance(row, dict):
            raise RuntimeError("CONTINUITY_SCHEMA_FAIL")
        for key in (
            "morphism_ref",
            "overlap_profile_ref",
            "translator_bundle_ref",
            "totality_cert_ref",
            "continuity_receipt_ref",
        ):
            _validate_artifact_ref(bundle_dir, row.get(key))
        continuity_payload = _validate_artifact_ref(bundle_dir, row.get("continuity_receipt_ref"))
        if str(continuity_payload.get("final_outcome", "")) != "ACCEPT":
            raise RuntimeError("CONTINUITY_RECEIPT_NOT_ACCEPT")


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _normalize_hex64(raw: str) -> str:
    value = raw.strip().lower()
    if value.startswith("sha256:"):
        value = value.split(":", 1)[1]
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise RuntimeError("KERNEL_HASH_INVALID")
    return value


def _expected_kernel_hash(meta_core_root: Path) -> str:
    kernel_hash_path = meta_core_root / "kernel" / "verifier" / "KERNEL_HASH"
    if not kernel_hash_path.exists():
        raise RuntimeError("KERNEL_HASH_MISSING")
    return _normalize_hex64(kernel_hash_path.read_text(encoding="utf-8"))


def _verifier_release_binary(meta_core_root: Path) -> Path:
    return meta_core_root / "kernel" / "verifier" / "target" / "release" / "verifier"


def _binary_hash_matches_expected(meta_core_root: Path, verifier_bin: Path) -> bool:
    expected = _expected_kernel_hash(meta_core_root)
    observed = _sha256_file(verifier_bin)
    return observed == expected


def _build_release_verifier(meta_core_root: Path) -> None:
    verifier_dir = meta_core_root / "kernel" / "verifier"
    subprocess.run(
        ["cargo", "build", "--release"],
        check=True,
        cwd=verifier_dir,
    )


def _kernel_hash_check_enabled() -> bool:
    raw = os.environ.get("META_CORE_ENFORCE_KERNEL_HASH", "")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _ensure_release_verifier(meta_core_root: Path) -> Path:
    verifier_bin = _verifier_release_binary(meta_core_root)
    check_hash = _kernel_hash_check_enabled()
    if verifier_bin.exists() and os.access(verifier_bin, os.X_OK):
        if (not check_hash) or _binary_hash_matches_expected(meta_core_root, verifier_bin):
            return verifier_bin

    _build_release_verifier(meta_core_root)
    if not verifier_bin.exists() or not os.access(verifier_bin, os.X_OK):
        raise RuntimeError("VERIFIER_BINARY_MISSING")
    if check_hash and not _binary_hash_matches_expected(meta_core_root, verifier_bin):
        raise RuntimeError("KERNEL_HASH_MISMATCH")
    return verifier_bin


def _run_rust_verifier(bundle_dir: Path, meta_core_root: Path, out_path: Path) -> None:
    _enforce_continuity_sidecar(bundle_dir)
    verifier_bin = _ensure_release_verifier(meta_core_root)
    subprocess.run(
        [
            str(verifier_bin),
            "verify-promotion",
            "--bundle-dir",
            str(bundle_dir),
            "--meta-core-root",
            str(meta_core_root),
            "--out",
            str(out_path),
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle_dir", required=True)
    parser.add_argument("--meta_core_root", required=False, default=os.environ.get("META_CORE_ROOT", ""))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    meta_core_root = Path(args.meta_core_root) if args.meta_core_root else Path(__file__).resolve().parents[2]
    _run_rust_verifier(Path(args.bundle_dir), meta_core_root, Path(args.out))


if __name__ == "__main__":
    main()
