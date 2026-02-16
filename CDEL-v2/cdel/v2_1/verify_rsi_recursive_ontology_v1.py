"""Verifier for RSI recursive ontology v2.1 runs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, loads, sha256_prefixed
from .constants import meta_identities, require_constants
from .opt_ontology import concept_uses_call, validate_call_order
from .verify_rsi_demon_v7 import verify as verify_attempt


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _pack_hash(pack: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(pack))


def compute_run_id(pack_hash: str, constitution_hash: str) -> str:
    data = (pack_hash + constitution_hash + "recursive_ontology_v2_1").encode("utf-8")
    return sha256_prefixed(data)


def _load_pack_used(state_dir: Path) -> dict[str, Any]:
    pack_path = state_dir / "pack_used.json"
    if not pack_path.exists():
        _fail("MISSING_ARTIFACT")
    raw = pack_path.read_text(encoding="utf-8").strip()
    pack = loads(raw)
    if canon_bytes(pack).decode("utf-8") != raw:
        _fail("CANON_HASH_MISMATCH")
    if pack.get("schema") != "rsi_real_recursive_ontology_pack_v1":
        _fail("SCHEMA_INVALID")
    if "schema_version" in pack and int(pack.get("schema_version", 0)) != 1:
        _fail("SCHEMA_INVALID")
    return pack


def _load_constitution_hash(state_dir: Path) -> str:
    path = state_dir / "constitution_hash.txt"
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        _fail("SCHEMA_INVALID")
    return value


def _load_ledger(state_dir: Path) -> list[dict[str, Any]]:
    ledger_path = state_dir / "opt_ontology" / "opt_ontology_ledger_v1.jsonl"
    if not ledger_path.exists():
        _fail("MISSING_ARTIFACT")
    entries: list[dict[str, Any]] = []
    for raw in ledger_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        payload = loads(raw)
        if canon_bytes(payload).decode("utf-8") != raw:
            _fail("CANON_HASH_MISMATCH")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        entries.append(payload)
    return entries


def _verify_ledger(entries: list[dict[str, Any]]) -> str:
    prev_hash = "sha256:" + "0" * 64
    seq = 0
    head = prev_hash
    for entry in entries:
        if entry.get("schema") != "opt_ontology_ledger_event_v1":
            _fail("SCHEMA_INVALID")
        if int(entry.get("seq", -1)) != seq:
            _fail("SCHEMA_INVALID")
        if entry.get("prev_entry_hash") != prev_hash:
            _fail("CANON_HASH_MISMATCH")
        payload = dict(entry)
        payload.pop("entry_hash", None)
        expected = sha256_prefixed(canon_bytes(payload))
        if entry.get("entry_hash") != expected:
            _fail("CANON_HASH_MISMATCH")
        prev_hash = expected
        head = expected
        seq += 1
    return head


def _load_active_set(state_dir: Path) -> dict[str, Any]:
    path = state_dir / "opt_ontology" / "opt_ontology_active_set_v1.json"
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    raw = path.read_text(encoding="utf-8").strip()
    payload = loads(raw)
    if canon_bytes(payload).decode("utf-8") != raw:
        _fail("CANON_HASH_MISMATCH")
    if payload.get("schema") != "opt_ontology_active_set_v1":
        _fail("SCHEMA_INVALID")
    head = dict(payload)
    head.pop("active_set_head_hash", None)
    if payload.get("active_set_head_hash") != sha256_prefixed(canon_bytes(head)):
        _fail("CANON_HASH_MISMATCH")
    return payload


def _load_concept_patch(state_dir: Path, patch_id: str) -> dict[str, Any]:
    concepts_dir = state_dir / "opt_ontology" / "concepts"
    if not concepts_dir.exists():
        _fail("MISSING_ARTIFACT")
    for path in sorted(concepts_dir.glob("*.json")):
        raw = path.read_text(encoding="utf-8").strip()
        payload = loads(raw)
        if payload.get("patch_id") == patch_id:
            if canon_bytes(payload).decode("utf-8") != raw:
                _fail("CANON_HASH_MISMATCH")
            return payload
    _fail("MISSING_ARTIFACT")
    return {}


def verify(state_dir: Path) -> dict[str, Any]:
    constants = require_constants()
    meta = meta_identities()

    pack = _load_pack_used(state_dir)
    constitution_hash = _load_constitution_hash(state_dir)
    if constitution_hash != meta.get("META_HASH"):
        _fail("META_DRIFT")

    pack_hash = _pack_hash(pack)
    run_id = compute_run_id(pack_hash, constitution_hash)

    entries = _load_ledger(state_dir)
    ledger_head_hash = _verify_ledger(entries)

    active_set = _load_active_set(state_dir)
    accepted_concepts = active_set.get("accepted_concepts") if isinstance(active_set.get("accepted_concepts"), list) else []

    required_k = int(pack.get("K_required_concepts", 0) or 0)
    if required_k != int(constants.get("K_RO_CONCEPTS", 0) or 0):
        _fail("SCHEMA_INVALID")

    uses_recursive_required = bool(constants.get("REQUIRES_RECURSIVE_CALL", False))

    accepted_rows: list[dict[str, Any]] = []
    uses_recursive = False

    active_ids = [
        entry.get("concept_id")
        for entry in accepted_concepts
        if isinstance(entry, dict) and isinstance(entry.get("concept_id"), str)
    ]

    for idx, entry in enumerate(accepted_concepts):
        if not isinstance(entry, dict):
            _fail("SCHEMA_INVALID")
        concept_id = entry.get("concept_id")
        patch_id = entry.get("patch_id")
        if not isinstance(concept_id, str) or not isinstance(patch_id, str):
            _fail("SCHEMA_INVALID")

        patch = _load_concept_patch(state_dir, patch_id)
        concept = patch.get("concept") if isinstance(patch.get("concept"), dict) else None
        if not isinstance(concept, dict):
            _fail("SCHEMA_INVALID")
        if concept.get("concept_id") != concept_id:
            _fail("CANON_HASH_MISMATCH")
        expr = concept.get("expr")
        if not isinstance(expr, dict):
            _fail("SCHEMA_INVALID")
        if concept.get("created_in_run_id") != run_id:
            _fail("CANON_HASH_MISMATCH")
        validate_call_order(expr, active_ids, caller_index=idx)
        if concept_uses_call(expr):
            uses_recursive = True

        # find corresponding accept entry for receipts
        source_receipt_relpath = None
        target_receipt_relpath = None
        rho_source = None
        rho_target = None
        for ledger_entry in entries:
            if ledger_entry.get("event") != "OPT_ONTO_CONCEPT_ACCEPT_V1":
                continue
            payload = ledger_entry.get("payload") if isinstance(ledger_entry.get("payload"), dict) else None
            if not isinstance(payload, dict):
                continue
            if payload.get("concept_id") == concept_id and payload.get("patch_id") == patch_id:
                source_receipt_relpath = payload.get("source_receipt_relpath")
                target_receipt_relpath = payload.get("target_receipt_relpath")
                rho_source = payload.get("rho_source")
                rho_target = payload.get("rho_target")
                break
        if not isinstance(source_receipt_relpath, str) or not isinstance(target_receipt_relpath, str):
            _fail("MISSING_ARTIFACT")

        source_receipt_path = state_dir / source_receipt_relpath
        target_receipt_path = state_dir / target_receipt_relpath
        if not source_receipt_path.exists() or not target_receipt_path.exists():
            _fail("MISSING_ARTIFACT")

        def _attempt_dir_from_receipt(path: Path) -> Path:
            parts = list(path.parts)
            if "epochs" not in parts:
                _fail("SCHEMA_INVALID")
            idx = parts.index("epochs")
            return Path(*parts[:idx])

        source_attempt_dir = _attempt_dir_from_receipt(source_receipt_path)
        target_attempt_dir = _attempt_dir_from_receipt(target_receipt_path)

        source_receipt, _epochs = verify_attempt(source_attempt_dir)
        target_receipt, _epochs2 = verify_attempt(target_attempt_dir)

        if source_receipt.get("concept_id") != concept_id or target_receipt.get("concept_id") != concept_id:
            _fail("CANON_HASH_MISMATCH")
        if source_receipt.get("patch_id") != patch_id or target_receipt.get("patch_id") != patch_id:
            _fail("CANON_HASH_MISMATCH")

        accepted_rows.append(
            {
                "concept_id": concept_id,
                "patch_id": patch_id,
                "source_attempt_relpath": str(source_attempt_dir.relative_to(state_dir)),
                "target_attempt_relpath": str(target_attempt_dir.relative_to(state_dir)),
                "rho_source": rho_source if isinstance(rho_source, dict) else source_receipt.get("rho_met"),
                "rho_target": rho_target if isinstance(rho_target, dict) else target_receipt.get("rho_met"),
                "uses_recursive_call": bool(concept_uses_call(expr)),
            }
        )

    if len(accepted_rows) < required_k:
        _fail("CONCEPT_ENUM_EXHAUSTED")
    if uses_recursive_required and not uses_recursive:
        _fail("CONCEPT_SAFETY_FAIL")

    receipt = {
        "schema": "rsi_recursive_ontology_receipt_v1",
        "run_id": run_id,
        "pack_hash": pack_hash,
        "constitution_hash": constitution_hash,
        "K_required_concepts": int(required_k),
        "accepted_concepts": accepted_rows,
        "verdict": "VALID",
        "reasons": [],
        "ledger_head_hash": ledger_head_hash,
    }

    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify RSI recursive ontology v2.1 run")
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        verify(Path(args.state_dir))
    except Exception as exc:  # noqa: BLE001
        reason = str(exc) if str(exc) else "unknown"
        print(f"INVALID: {reason}")
        return
    print("VALID")


if __name__ == "__main__":
    main()
