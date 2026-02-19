"""Fail-closed verifier for polymath SIP ingestion L0 campaign artifacts (v1)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19
from cdel.v19_0.common_v1 import verify_object_id as verify_object_id_v19

from .omega_common_v1 import OmegaV18Error, canon_hash_obj, fail, hash_file_stream, load_canon_dict, validate_schema
from .polymath_sip_ingestion_l0_v1 import compute_producer_run_id


def _resolve_state(path: Path) -> Path:
    root = path.resolve()
    candidates = [
        root / "daemon" / "rsi_polymath_sip_ingestion_l0_v1" / "state",
        root,
    ]
    for candidate in candidates:
        if (candidate / "polymath" / "ingestion").is_dir():
            return candidate
    fail("SCHEMA_FAIL")
    return root


def _ensure_sha256(value: Any) -> str:
    text = str(value).strip()
    if len(text) != 71 or not text.startswith("sha256:"):
        fail("SCHEMA_FAIL")
    digest = text.split(":", 1)[1]
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        fail("SCHEMA_FAIL")
    return text


def _verify_hashed_filename(path: Path) -> str:
    name = path.name
    if not name.startswith("sha256_"):
        fail("NONDETERMINISTIC")
    digest_hex = name.split(".", 1)[0].split("_", 1)[1]
    if len(digest_hex) != 64 or any(ch not in "0123456789abcdef" for ch in digest_hex):
        fail("NONDETERMINISTIC")
    expected = f"sha256:{digest_hex}"
    payload = load_canon_dict(path)
    observed = canon_hash_obj(payload)
    if observed != expected:
        fail("NONDETERMINISTIC")
    return expected


def _blob_path(*, ingestion_root: Path, content_id: str) -> Path:
    digest = _ensure_sha256(content_id).split(":", 1)[1]
    blob_path = ingestion_root / "blobs" / "sha256" / digest
    if not blob_path.exists() or not blob_path.is_file():
        fail("MISSING_STATE_INPUT")
    if hash_file_stream(blob_path) != content_id:
        fail("NONDETERMINISTIC")
    return blob_path


def _entropy_q16(data: bytes) -> int:
    import math

    if not data:
        return 0
    counts = [0] * 256
    for byte in data:
        counts[byte] += 1
    total = len(data)
    entropy = 0.0
    for count in counts:
        if count == 0:
            continue
        p = count / total
        entropy -= p * math.log2(p)
    return int(round(entropy * (1 << 16)))


def _load_manifest(*, ingestion_root: Path, manifest_id: str) -> dict[str, Any]:
    target_id = _ensure_sha256(manifest_id)
    paths = sorted((ingestion_root / "manifests").glob("sha256_*.world_snapshot_manifest_v1.json"), key=lambda p: p.as_posix())
    matches: list[dict[str, Any]] = []
    for path in paths:
        _ = _verify_hashed_filename(path)
        payload = load_canon_dict(path)
        validate_schema_v19(payload, "world_snapshot_manifest_v1")
        observed_id = verify_object_id_v19(payload, id_field="manifest_id")
        if observed_id == target_id:
            matches.append(payload)
    if len(matches) != 1:
        fail("MISSING_STATE_INPUT")
    return matches[0]


def _load_receipt(*, ingestion_root: Path, receipt_id: str) -> dict[str, Any]:
    target_id = _ensure_sha256(receipt_id)
    paths = sorted((ingestion_root / "receipts").glob("sha256_*.sealed_ingestion_receipt_v1.json"), key=lambda p: p.as_posix())
    matches: list[dict[str, Any]] = []
    for path in paths:
        _ = _verify_hashed_filename(path)
        payload = load_canon_dict(path)
        validate_schema_v19(payload, "sealed_ingestion_receipt_v1")
        observed_id = verify_object_id_v19(payload, id_field="receipt_id")
        if observed_id == target_id:
            matches.append(payload)
    if len(matches) != 1:
        fail("MISSING_STATE_INPUT")
    return matches[0]


def _manifest_entry_by_content_id(manifest: dict[str, Any], content_id: str) -> dict[str, Any]:
    rows = manifest.get("entries")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    matches = [row for row in rows if isinstance(row, dict) and str(row.get("content_id", "")).strip() == content_id]
    if len(matches) != 1:
        fail("NONDETERMINISTIC")
    return matches[0]


def _verify_success(*, ingestion_root: Path, artifact_path: Path) -> str:
    _ = _verify_hashed_filename(artifact_path)
    artifact = load_canon_dict(artifact_path)
    validate_schema(artifact, "sip_knowledge_artifact_v1")

    dataset_name = str(artifact.get("dataset_name", "")).strip()
    tick_u64 = int(artifact.get("tick_u64", -1))
    if not dataset_name or tick_u64 < 0:
        fail("SCHEMA_FAIL")

    raw_id = _ensure_sha256(artifact.get("raw_bytes_content_id"))
    canon_id = _ensure_sha256(artifact.get("canonical_jsonl_content_id"))
    manifest_id = _ensure_sha256(artifact.get("sip_manifest_id"))
    receipt_id = _ensure_sha256(artifact.get("sip_seal_receipt_id"))

    manifest = _load_manifest(ingestion_root=ingestion_root, manifest_id=manifest_id)
    receipt = _load_receipt(ingestion_root=ingestion_root, receipt_id=receipt_id)

    if str(receipt.get("outcome", "")).strip() != "ACCEPT":
        fail("VERIFY_ERROR")
    if str(receipt.get("reason_code", "")).strip() != "GATES_PASS":
        fail("VERIFY_ERROR")
    if str(receipt.get("world_manifest_ref", "")).strip() != manifest_id:
        fail("NONDETERMINISTIC")

    leakage_gate = (receipt.get("gate_results") or {}).get("leakage_gate")
    non_interference_gate = (receipt.get("gate_results") or {}).get("non_interference_gate")
    if not isinstance(leakage_gate, dict) or not isinstance(non_interference_gate, dict):
        fail("SCHEMA_FAIL")
    if str(leakage_gate.get("outcome", "")).strip() != "ACCEPT":
        fail("VERIFY_ERROR")
    if str(non_interference_gate.get("outcome", "")).strip() != "ACCEPT":
        fail("VERIFY_ERROR")

    raw_blob = _blob_path(ingestion_root=ingestion_root, content_id=raw_id).read_bytes()
    canon_blob = _blob_path(ingestion_root=ingestion_root, content_id=canon_id).read_bytes()

    raw_manifest_row = _manifest_entry_by_content_id(manifest, raw_id)
    canon_manifest_row = _manifest_entry_by_content_id(manifest, canon_id)
    if int(raw_manifest_row.get("content_length_bytes", -1)) != len(raw_blob):
        fail("NONDETERMINISTIC")
    if int(canon_manifest_row.get("content_length_bytes", -1)) != len(canon_blob):
        fail("NONDETERMINISTIC")

    if int(artifact.get("bytes_u64", -1)) != len(canon_blob):
        fail("NONDETERMINISTIC")
    observed_rows = sum(1 for row in canon_blob.splitlines() if row)
    if int(artifact.get("record_count_u64", -1)) != int(observed_rows):
        fail("NONDETERMINISTIC")
    if int(artifact.get("entropy_q16", -1)) != _entropy_q16(canon_blob):
        fail("NONDETERMINISTIC")

    expected_run_id = compute_producer_run_id(
        dataset_name=dataset_name,
        tick_u64=tick_u64,
        raw_bytes_content_id=raw_id,
        canonical_jsonl_content_id=canon_id,
    )
    if str(artifact.get("producer_run_id", "")).strip() != expected_run_id:
        fail("NONDETERMINISTIC")

    if bool(artifact.get("leakage_scan_passed_b")) is not True:
        fail("VERIFY_ERROR")

    return "VALID"


def _verify_refutation(*, ingestion_root: Path, artifact_path: Path) -> str:
    _ = _verify_hashed_filename(artifact_path)
    artifact = load_canon_dict(artifact_path)
    validate_schema(artifact, "sip_knowledge_refutation_v1")

    reason = str(artifact.get("reason_code", "")).strip()
    dataset_name = str(artifact.get("dataset_name", "")).strip()
    tick_u64 = int(artifact.get("tick_u64", -1))
    if not dataset_name or tick_u64 < 0:
        fail("SCHEMA_FAIL")

    raw_id = _ensure_sha256(artifact.get("raw_bytes_content_id"))
    canonical_raw = artifact.get("canonical_jsonl_content_id")
    manifest_raw = artifact.get("sip_manifest_id")
    receipt_raw = artifact.get("sip_seal_receipt_id")

    canonical_id = None
    if canonical_raw is not None:
        canonical_id = _ensure_sha256(canonical_raw)

    _ = _blob_path(ingestion_root=ingestion_root, content_id=raw_id)
    if canonical_id is not None:
        _ = _blob_path(ingestion_root=ingestion_root, content_id=canonical_id)

    expected_run_id = compute_producer_run_id(
        dataset_name=dataset_name,
        tick_u64=tick_u64,
        raw_bytes_content_id=raw_id,
        canonical_jsonl_content_id=canonical_id,
    )
    if str(artifact.get("producer_run_id", "")).strip() != expected_run_id:
        fail("NONDETERMINISTIC")

    if reason in {"INPUT_HASH_MISMATCH", "CANON_JSONL_PARSE_FAIL"}:
        if manifest_raw is not None or receipt_raw is not None:
            fail("VERIFY_ERROR")
        return "VALID"

    if manifest_raw is None or receipt_raw is None:
        fail("MISSING_STATE_INPUT")

    manifest_id = _ensure_sha256(manifest_raw)
    receipt_id = _ensure_sha256(receipt_raw)
    manifest = _load_manifest(ingestion_root=ingestion_root, manifest_id=manifest_id)
    receipt = _load_receipt(ingestion_root=ingestion_root, receipt_id=receipt_id)

    if str(receipt.get("world_manifest_ref", "")).strip() != manifest_id:
        fail("NONDETERMINISTIC")

    outcome = str(receipt.get("outcome", "")).strip()
    if reason == "SIP_REJECTED" and outcome != "REJECT":
        fail("VERIFY_ERROR")
    if reason == "SIP_SAFE_HALT" and outcome != "SAFE_HALT":
        fail("VERIFY_ERROR")
    if reason == "BUDGET_EXHAUSTED" and str(receipt.get("reason_code", "")).strip() != "BUDGET_EXHAUSTED":
        fail("VERIFY_ERROR")

    # Keep manifest linked to declared content IDs for replayability.
    _ = _manifest_entry_by_content_id(manifest, raw_id)
    if canonical_id is not None:
        _ = _manifest_entry_by_content_id(manifest, canonical_id)

    return "VALID"


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        fail("MODE_UNSUPPORTED")

    state_root = _resolve_state(state_dir)
    ingestion_root = state_root / "polymath" / "ingestion"

    knowledge_paths = sorted((ingestion_root / "knowledge").glob("sha256_*.sip_knowledge_artifact_v1.json"), key=lambda p: p.as_posix())
    refutation_paths = sorted((ingestion_root / "refutations").glob("sha256_*.sip_knowledge_refutation_v1.json"), key=lambda p: p.as_posix())

    if len(knowledge_paths) + len(refutation_paths) != 1:
        fail("SCHEMA_FAIL")

    if knowledge_paths:
        return _verify_success(ingestion_root=ingestion_root, artifact_path=knowledge_paths[0])
    return _verify_refutation(ingestion_root=ingestion_root, artifact_path=refutation_paths[0])


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_polymath_sip_ingestion_l0_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        print(verify(Path(args.state_dir), mode=str(args.mode)))
    except OmegaV18Error as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
