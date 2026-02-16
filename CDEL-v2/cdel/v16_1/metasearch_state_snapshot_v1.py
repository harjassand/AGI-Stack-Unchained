"""State snapshot helpers for SAS-Metasearch v16.1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from ..v13_0.sas_science_dataset_v1 import (
    compute_dataset_receipt,
    compute_split_receipt,
    load_dataset,
    load_manifest,
)


def hash_json_obj(obj: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(obj))


def hash_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def ingest_dataset_snapshot(
    *,
    state_dir: Path,
    dataset_manifest_src: Path,
    dataset_csv_src: Path,
) -> dict[str, Any]:
    workspace = state_dir / "search_workspace"
    data_manifest_dir = workspace / "data" / "manifest"
    data_csv_dir = workspace / "data" / "csv"
    data_receipts_dir = workspace / "data" / "receipts"

    for path in [data_manifest_dir, data_csv_dir, data_receipts_dir]:
        path.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(dataset_manifest_src)
    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    manifest_out = data_manifest_dir / f"sha256_{manifest_hash.split(':',1)[1]}.sas_science_dataset_manifest_v1.json"
    write_canon_json(manifest_out, manifest)

    csv_bytes = dataset_csv_src.read_bytes()
    csv_hash = sha256_prefixed(csv_bytes)
    csv_out = data_csv_dir / f"sha256_{csv_hash.split(':',1)[1]}.dataset.csv"
    csv_out.write_bytes(csv_bytes)

    dataset_obj = load_dataset(csv_out, manifest)
    dataset_receipt = compute_dataset_receipt(manifest=manifest, csv_bytes=csv_bytes, row_count=len(dataset_obj.times_q32))
    dataset_receipt_hash = hash_json_obj(dataset_receipt)
    dataset_receipt_out = data_receipts_dir / f"sha256_{dataset_receipt_hash.split(':',1)[1]}.sas_science_dataset_receipt_v1.json"
    write_canon_json(dataset_receipt_out, dataset_receipt)

    split_receipt = compute_split_receipt(
        manifest=manifest,
        dataset_id=str(dataset_receipt["dataset_id"]),
        row_count=int(dataset_receipt["row_count"]),
    )
    split_receipt_hash = hash_json_obj(split_receipt)
    split_receipt_out = data_receipts_dir / f"sha256_{split_receipt_hash.split(':',1)[1]}.sas_science_split_receipt_v1.json"
    write_canon_json(split_receipt_out, split_receipt)

    return {
        "workspace": workspace,
        "manifest": manifest,
        "manifest_path": manifest_out,
        "manifest_hash": manifest_hash,
        "csv_path": csv_out,
        "csv_hash": csv_hash,
        "dataset_receipt": dataset_receipt,
        "dataset_receipt_path": dataset_receipt_out,
        "dataset_receipt_hash": dataset_receipt_hash,
        "split_receipt": split_receipt,
        "split_receipt_path": split_receipt_out,
        "split_receipt_hash": split_receipt_hash,
    }


def require_hashed_state_file(*, path: Path, expected_hash: str) -> None:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("MISSING_STATE_INPUT")
    got = hash_file(path)
    if got != expected_hash:
        raise ValueError("STATE_HASH_MISMATCH")


def load_json_by_hash(*, path: Path, expected_hash: str) -> dict[str, Any]:
    require_hashed_state_file(path=path, expected_hash=expected_hash)
    obj = load_canon_json(path)
    if not isinstance(obj, dict):
        raise ValueError("SCHEMA_FAIL")
    return obj


__all__ = [
    "hash_json_obj",
    "hash_file",
    "ingest_dataset_snapshot",
    "require_hashed_state_file",
    "load_json_by_hash",
]
