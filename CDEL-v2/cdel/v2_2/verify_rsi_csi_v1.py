"""Verifier for RSI CSI v2.2 runs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, loads, sha256_prefixed, write_canon_json
from .code_patch import tree_entries_v1, tree_hash_from_entries
from .constants import meta_identities, require_constants
from .verify_rsi_demon_v8 import verify as verify_attempt


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _pack_hash(pack: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(pack))


def compute_run_id(pack_hash: str, constitution_hash: str) -> str:
    data = (pack_hash + constitution_hash + "csi_v2_2").encode("utf-8")
    return sha256_prefixed(data)


def _load_pack_used(state_dir: Path) -> dict[str, Any]:
    path = state_dir / "pack_used.json"
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    pack = load_canon_json(path)
    if pack.get("schema") != "rsi_real_csi_pack_v1":
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
    ledger_path = state_dir / "ledger" / "csi_ledger_v1.jsonl"
    if not ledger_path.exists():
        _fail("MISSING_ARTIFACT")
    entries: list[dict[str, Any]] = []
    for raw in ledger_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        entry = load_canon_json_from_line(raw)
        entries.append(entry)
    return entries


def load_canon_json_from_line(raw: str) -> dict[str, Any]:
    payload = loads(raw)
    if canon_bytes(payload).decode("utf-8") != raw:
        _fail("CANON_HASH_MISMATCH")
    if not isinstance(payload, dict):
        _fail("SCHEMA_INVALID")
    return payload


def _verify_ledger(entries: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    prev_hash = "sha256:" + "0" * 64
    seq = 0
    head = prev_hash
    accepts: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("schema") != "csi_ledger_event_v1":
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
        if entry.get("event") == "CSI_PATCH_ACCEPT_V1":
            accepts.append(entry)
    return head, accepts


def _find_attempt_dir(state_dir: Path, patch_id: str) -> Path | None:
    attempts_dir = state_dir / "attempts"
    if not attempts_dir.exists():
        return None
    for path in sorted(attempts_dir.glob("attempt_*")):
        patch_path = path / "autonomy" / "csi" / "code_patch.json"
        if not patch_path.exists():
            continue
        patch = load_canon_json(patch_path)
        if patch.get("patch_id") == patch_id:
            receipt_path = path / "diagnostics" / "rsi_demon_receipt_v8.json"
            if receipt_path.exists():
                receipt = load_canon_json(receipt_path)
                if receipt.get("verdict") != "VALID":
                    continue
            return path
    return None


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
    ledger_head_hash, accepts = _verify_ledger(entries)

    required_k = int(pack.get("K_required_patches", 0) or 0)
    if required_k != int(constants.get("K_CSI_ACCEPTED_PATCHES", 0) or 0):
        _fail("SCHEMA_INVALID")
    if len(accepts) < required_k:
        _fail("MISSING_ARTIFACT")

    allowed_roots = list(constants.get("CSI_ALLOWED_ROOTS", []))
    immutable_paths = list(constants.get("CSI_IMMUTABLE_PATHS", []))

    # Verify accepted patches and chain base/after hashes
    current_hash = None
    accepted_rows: list[dict[str, Any]] = []

    for entry in accepts:
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else None
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        patch_id = payload.get("patch_id")
        base_tree_hash = payload.get("base_tree_hash")
        after_tree_hash = payload.get("after_tree_hash")
        if not isinstance(patch_id, str) or not isinstance(base_tree_hash, str) or not isinstance(after_tree_hash, str):
            _fail("SCHEMA_INVALID")

        attempt_dir = _find_attempt_dir(state_dir, patch_id)
        if attempt_dir is None:
            _fail("MISSING_ARTIFACT")

        # Inner verifier must pass
        receipt = verify_attempt(attempt_dir)
        if receipt.get("verdict") != "VALID":
            _fail("MISSING_ARTIFACT")

        # Ensure base snapshot hash matches payload if available
        base_snapshot = attempt_dir / "base_snapshot"
        if base_snapshot.exists():
            base_hash = tree_hash_from_entries(tree_entries_v1(base_snapshot, allowed_roots, immutable_paths))
            if base_hash != base_tree_hash:
                _fail("CANON_HASH_MISMATCH")

        if current_hash is None:
            current_hash = base_tree_hash
        if base_tree_hash != current_hash:
            _fail("CANON_HASH_MISMATCH")
        current_hash = after_tree_hash

        accepted_rows.append(
            {
                "patch_id": patch_id,
                "concept_id": receipt.get("concept_id"),
                "attempt_relpath": f"attempts/{attempt_dir.name}",
                "base_tree_hash": base_tree_hash,
                "after_tree_hash": after_tree_hash,
                "rho_csi": receipt.get("rho_csi"),
            }
        )

    # Verify final active tree hash
    active_hash_path = state_dir / "active_tree" / "active_tree_hash.txt"
    if not active_hash_path.exists():
        _fail("MISSING_ARTIFACT")
    active_hash = active_hash_path.read_text(encoding="utf-8").strip()
    if current_hash is not None and active_hash != current_hash:
        _fail("CANON_HASH_MISMATCH")

    receipt = {
        "schema": "rsi_csi_receipt_v1",
        "run_id": run_id,
        "pack_hash": pack_hash,
        "constitution_hash": constitution_hash,
        "K_required_patches": required_k,
        "accepted_patches": accepted_rows,
        "verdict": "VALID",
        "reasons": [],
        "ledger_head_hash": ledger_head_hash,
    }
    return receipt


def _write_receipt(state_dir: Path, receipt: dict[str, Any]) -> None:
    out = state_dir / "diagnostics" / "rsi_csi_receipt_v1.json"
    write_canon_json(out, receipt)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify RSI CSI v2.2 run")
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        receipt = verify(Path(args.state_dir))
        _write_receipt(Path(args.state_dir), receipt)
    except Exception as exc:  # noqa: BLE001
        reason = str(exc) if str(exc) else "unknown"
        receipt = {
            "schema": "rsi_csi_receipt_v1",
            "run_id": "",
            "pack_hash": "",
            "constitution_hash": "",
            "K_required_patches": 0,
            "accepted_patches": [],
            "verdict": "INVALID",
            "reasons": [reason],
            "ledger_head_hash": "",
        }
        try:
            _write_receipt(Path(args.state_dir), receipt)
        except Exception:
            pass
        print(f"INVALID: {reason}")
        return

    print("VALID")


if __name__ == "__main__":
    main()
