#!/usr/bin/env python3
"""Content-addressed proposer model/dataset store helpers (v1)."""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict, repo_root
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _fail(reason: str) -> None:
    raise RuntimeError(reason)


def ensure_sha256_id(value: Any, *, reason: str = "SCHEMA_FAIL") -> str:
    text = str(value).strip()
    if _SHA256_RE.fullmatch(text) is None:
        _fail(reason)
    return text


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _hex_part(sha256_id: str) -> str:
    return ensure_sha256_id(sha256_id).split(":", 1)[1]


def blob_filename(sha256_id: str, *, kind: str, ext: str) -> str:
    hexd = _hex_part(sha256_id)
    kind_norm = str(kind).strip().lower() or "blob"
    ext_norm = str(ext).strip().lower().lstrip(".") or "bin"
    return f"sha256_{hexd}.{kind_norm}.{ext_norm}"


def _ext_from_relpath(relpath: str) -> str:
    suffix = Path(str(relpath)).suffix.lower().lstrip(".")
    return suffix or "bin"


def default_model_store_root() -> Path:
    return (repo_root() / "daemon" / "proposer_models" / "store").resolve()


def default_dataset_store_root() -> Path:
    return (repo_root() / "daemon" / "proposer_models" / "datasets").resolve()


def ensure_model_store_layout(store_root: Path) -> dict[str, Path]:
    root = store_root.resolve()
    blobs = (root / "blobs" / "sha256").resolve()
    manifests = (root / "manifests").resolve()
    tmp = (root / "tmp").resolve()
    for path in (root, blobs, manifests, tmp):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "store_root": root,
        "blobs_root": blobs,
        "manifests_root": manifests,
        "tmp_root": tmp,
    }


def ensure_dataset_store_layout(dataset_root: Path) -> dict[str, Path]:
    root = dataset_root.resolve()
    blobs = (root / "blobs" / "sha256").resolve()
    manifests = (root / "manifests").resolve()
    for path in (root, blobs, manifests):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "dataset_root": root,
        "blobs_root": blobs,
        "manifests_root": manifests,
    }


def manifest_path_for_id(manifests_root: Path, *, digest: str, schema_name: str) -> Path:
    return manifests_root / f"sha256_{_hex_part(digest)}.{schema_name}.json"


def write_manifest(manifests_root: Path, *, schema_name: str, payload: dict[str, Any], digest: str | None = None) -> tuple[str, Path]:
    manifests_root.mkdir(parents=True, exist_ok=True)
    id_value = ensure_sha256_id(digest) if digest is not None else str(canon_hash_obj(payload))
    path = manifest_path_for_id(manifests_root, digest=id_value, schema_name=schema_name)
    write_canon_json(path, payload)
    return id_value, path


def load_manifest_by_id(manifests_root: Path, *, digest: str, schema_name: str | None = None) -> dict[str, Any]:
    digest_norm = ensure_sha256_id(digest)
    if schema_name:
        path = manifest_path_for_id(manifests_root, digest=digest_norm, schema_name=schema_name)
        if not path.exists() or not path.is_file():
            _fail("MISSING_STATE_INPUT")
        payload = load_canon_dict(path)
        if schema_name == "proposer_model_bundle_v1":
            validate_schema_v19(payload, "proposer_model_bundle_v1")
        elif schema_name == "proposer_model_train_config_v1":
            validate_schema_v19(payload, "proposer_model_train_config_v1")
        elif schema_name == "proposer_model_train_receipt_v1":
            validate_schema_v19(payload, "proposer_model_train_receipt_v1")
        return payload

    rows = sorted(manifests_root.glob(f"sha256_{_hex_part(digest_norm)}.*.json"), key=lambda p: p.as_posix())
    if len(rows) != 1:
        _fail("MISSING_STATE_INPUT")
    return load_canon_dict(rows[0])


def copy_file_to_blob_store(*, source_path: Path, store_root: Path, kind: str, relpath: str) -> dict[str, str]:
    if not source_path.exists() or not source_path.is_file():
        _fail("MISSING_STATE_INPUT")
    layout = ensure_model_store_layout(store_root)
    blobs_root = layout["blobs_root"]
    relpath_norm = str(Path(relpath).as_posix())
    digest = sha256_file(source_path)
    ext = _ext_from_relpath(relpath_norm)
    blob_name = blob_filename(digest, kind=kind, ext=ext)
    blob_path = (blobs_root / blob_name).resolve()
    if not blob_path.exists():
        shutil.copyfile(source_path, blob_path)
    return {
        "relpath": relpath_norm,
        "sha256": digest,
        "store_relpath": f"blobs/sha256/{blob_name}",
    }


def _resolve_adapter_blob_path(*, store_root: Path, adapter_entry: dict[str, Any]) -> Path:
    digest = ensure_sha256_id(adapter_entry.get("sha256"), reason="SCHEMA_FAIL")
    relpath = str(adapter_entry.get("relpath", "")).strip()
    if not relpath:
        _fail("SCHEMA_FAIL")

    ext = _ext_from_relpath(relpath)
    blobs_root = ensure_model_store_layout(store_root)["blobs_root"]
    candidate = blobs_root / blob_filename(digest, kind="adapter", ext=ext)
    if candidate.exists() and candidate.is_file():
        return candidate

    # Backward-compatible lookup for matching digest with unknown extension.
    rows = sorted(blobs_root.glob(f"sha256_{_hex_part(digest)}.adapter.*"), key=lambda p: p.as_posix())
    if not rows:
        _fail("BUNDLE_ADAPTER_MISSING")
    return rows[0]


def load_bundle_manifest(*, store_root: Path, bundle_id: str) -> dict[str, Any]:
    layout = ensure_model_store_layout(store_root)
    payload = load_manifest_by_id(
        layout["manifests_root"],
        digest=ensure_sha256_id(bundle_id),
        schema_name="proposer_model_bundle_v1",
    )
    declared = ensure_sha256_id(payload.get("bundle_id"), reason="SCHEMA_FAIL")
    if declared != ensure_sha256_id(bundle_id):
        _fail("BUNDLE_ID_MISMATCH")
    return payload


def verify_bundle_adapter_hashes(*, store_root: Path, bundle: dict[str, Any]) -> list[Path]:
    adapter_rows = bundle.get("adapter_files")
    if not isinstance(adapter_rows, list):
        _fail("SCHEMA_FAIL")

    resolved: list[Path] = []
    for row in adapter_rows:
        if not isinstance(row, dict):
            _fail("SCHEMA_FAIL")
        path = _resolve_adapter_blob_path(store_root=store_root, adapter_entry=row)
        expected = ensure_sha256_id(row.get("sha256"), reason="SCHEMA_FAIL")
        observed = sha256_file(path)
        if observed != expected:
            _fail("BUNDLE_HASH_MISMATCH")
        resolved.append(path)
    return resolved


def resolve_dataset_blob_by_sha(*, dataset_root: Path, blob_id: str) -> Path:
    digest = ensure_sha256_id(blob_id)
    layout = ensure_dataset_store_layout(dataset_root)
    blobs_root = layout["blobs_root"]
    rows = sorted(blobs_root.glob(f"sha256_{_hex_part(digest)}.*"), key=lambda p: p.as_posix())
    if not rows:
        _fail("MISSING_DATASET_BLOB")
    return rows[0]


__all__ = [
    "blob_filename",
    "copy_file_to_blob_store",
    "default_dataset_store_root",
    "default_model_store_root",
    "ensure_dataset_store_layout",
    "ensure_model_store_layout",
    "ensure_sha256_id",
    "load_bundle_manifest",
    "load_manifest_by_id",
    "manifest_path_for_id",
    "resolve_dataset_blob_by_sha",
    "sha256_bytes",
    "sha256_file",
    "verify_bundle_adapter_hashes",
    "write_manifest",
]
