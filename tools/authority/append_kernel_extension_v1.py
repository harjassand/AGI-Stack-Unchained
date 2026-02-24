#!/usr/bin/env python3
"""Append a kernel extension spec to the active kernel extension ledger (Phase 1)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    value = str(_entry)
    if value not in sys.path:
        sys.path.insert(0, value)

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.authority.authority_hash_v1 import load_authority_pins
from cdel.v18_0.omega_common_v1 import canon_hash_obj


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _ensure_sha256(value: Any, *, field: str) -> str:
    text = str(value).strip()
    if len(text) != 71 or not text.startswith("sha256:"):
        raise RuntimeError(f"SCHEMA_FAIL:{field}")
    hexd = text.split(":", 1)[1]
    if any(ch not in "0123456789abcdef" for ch in hexd):
        raise RuntimeError(f"SCHEMA_FAIL:{field}")
    return text


def _normalize_relpath(path_value: Any) -> str:
    rel = str(path_value).strip().replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    path = Path(rel)
    if not rel or path.is_absolute() or ".." in path.parts:
        raise RuntimeError("SCHEMA_FAIL:relpath")
    return rel


def _verify_declared_id(payload: dict[str, Any], *, id_field: str) -> str:
    declared = _ensure_sha256(payload.get(id_field), field=id_field)
    no_id = dict(payload)
    no_id.pop(id_field, None)
    if canon_hash_obj(no_id) != declared:
        raise RuntimeError(f"NONDETERMINISM:{id_field}")
    return declared


def _resolve_within_authority(repo_root: Path, relpath: str) -> Path:
    authority_root = (repo_root / "authority").resolve()
    candidate = (repo_root / _normalize_relpath(relpath)).resolve()
    try:
        candidate.relative_to(authority_root)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("SCHEMA_FAIL:authority_path_escape") from exc
    return candidate


def _load_ledger_by_id(repo_root: Path, ledger_id: str) -> tuple[dict[str, Any], Path]:
    ledger_id = _ensure_sha256(ledger_id, field="ledger_id")
    root = repo_root / "authority" / "eval_kernel_ledgers"
    matches: list[tuple[dict[str, Any], Path]] = []
    for path in sorted(root.glob("*.json"), key=lambda row: row.as_posix()):
        payload = _load_json(path)
        if str(payload.get("schema_version", "")).strip() != "kernel_extension_ledger_v1":
            continue
        if str(payload.get("ledger_id", "")).strip() != ledger_id:
            continue
        _verify_declared_id(payload, id_field="ledger_id")
        matches.append((payload, path))
    if len(matches) != 1:
        raise RuntimeError("MISSING_STATE_INPUT:active_ledger")
    return matches[0]


def _phase1_public_only_guard(repo_root: Path, suite_set: dict[str, Any]) -> None:
    suites = suite_set.get("suites")
    if not isinstance(suites, list) or not suites:
        raise RuntimeError("SCHEMA_FAIL:suite_set")
    for row in suites:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL:suite_row")
        manifest_relpath = _normalize_relpath(row.get("suite_manifest_relpath"))
        manifest_path = _resolve_within_authority(repo_root, manifest_relpath)
        if not manifest_path.exists() or not manifest_path.is_file():
            raise RuntimeError("MISSING_STATE_INPUT:suite_manifest")
        manifest = _load_json(manifest_path)
        if str(manifest.get("schema_version", "")).strip() != "benchmark_suite_manifest_v1":
            raise RuntimeError("SCHEMA_FAIL:suite_manifest")
        _verify_declared_id(manifest, id_field="suite_id")

        visibility = str(manifest.get("visibility", "")).strip().upper()
        if visibility and visibility != "PUBLIC":
            raise RuntimeError("PHASE1_PUBLIC_ONLY_VIOLATION:visibility")

        labels = manifest.get("labels")
        if isinstance(labels, list):
            for label in labels:
                text = str(label).strip().lower()
                if any(token in text for token in ("holdout", "hidden", "private", "secret", "masked")):
                    raise RuntimeError("PHASE1_PUBLIC_ONLY_VIOLATION:labels")


def _write_hashed(path_dir: Path, suffix: str, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    obj = dict(payload)
    digest = canon_hash_obj(obj)
    path_dir.mkdir(parents=True, exist_ok=True)
    out = path_dir / f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    write_canon_json(out, obj)
    return out, obj, digest


def main() -> None:
    parser = argparse.ArgumentParser(prog="append_kernel_extension_v1")
    parser.add_argument("--repo_root", default=str(_REPO_ROOT))
    parser.add_argument("--extension_spec_relpath", required=True)
    args = parser.parse_args()

    repo_root = Path(str(args.repo_root)).resolve()
    extension_spec_relpath = _normalize_relpath(args.extension_spec_relpath)

    pins = load_authority_pins(repo_root)
    active_ledger_id = _ensure_sha256(pins.get("active_kernel_extensions_ledger_id"), field="active_kernel_extensions_ledger_id")
    active_ek_id = _ensure_sha256(pins.get("active_ek_id"), field="active_ek_id")

    ledger, _ledger_path = _load_ledger_by_id(repo_root, active_ledger_id)
    if _ensure_sha256(ledger.get("anchor_ek_id"), field="anchor_ek_id") != active_ek_id:
        raise RuntimeError("SCHEMA_FAIL:anchor_ek_id")

    extension_spec_path = _resolve_within_authority(repo_root, extension_spec_relpath)
    if not extension_spec_path.exists() or not extension_spec_path.is_file():
        raise RuntimeError("MISSING_STATE_INPUT:extension_spec")
    extension_spec = _load_json(extension_spec_path)
    if str(extension_spec.get("schema_version", "")).strip() != "kernel_extension_spec_v1":
        raise RuntimeError("SCHEMA_FAIL:extension_spec")
    extension_spec_id = _verify_declared_id(extension_spec, id_field="extension_spec_id")
    if _ensure_sha256(extension_spec.get("anchor_ek_id"), field="anchor_ek_id") != active_ek_id:
        raise RuntimeError("SCHEMA_FAIL:anchor_ek_id")
    if not bool(extension_spec.get("additive_only_b", False)):
        raise RuntimeError("SCHEMA_FAIL:additive_only_b")

    suite_set_id = _ensure_sha256(extension_spec.get("suite_set_id"), field="suite_set_id")
    suite_set_relpath = _normalize_relpath(extension_spec.get("suite_set_relpath"))
    suite_set_path = _resolve_within_authority(repo_root, suite_set_relpath)
    if not suite_set_path.exists() or not suite_set_path.is_file():
        raise RuntimeError("MISSING_STATE_INPUT:suite_set")
    suite_set = _load_json(suite_set_path)
    if str(suite_set.get("schema_version", "")).strip() != "benchmark_suite_set_v1":
        raise RuntimeError("SCHEMA_FAIL:suite_set")
    if _ensure_sha256(suite_set.get("suite_set_id"), field="suite_set_id") != suite_set_id:
        raise RuntimeError("SCHEMA_FAIL:suite_set_id")
    if str(suite_set.get("suite_set_kind", "")).strip() != "EXTENSION":
        raise RuntimeError("SCHEMA_FAIL:suite_set_kind")

    _phase1_public_only_guard(repo_root, suite_set)

    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError("SCHEMA_FAIL:entries")
    for idx, row in enumerate(entries):
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL:entry")
        if int(row.get("ordinal_u64", -1)) != idx:
            raise RuntimeError("SCHEMA_FAIL:ordinal")

    next_ordinal_u64 = int(len(entries))
    next_entry = {
        "ordinal_u64": int(next_ordinal_u64),
        "extension_spec_id": str(extension_spec_id),
        "extension_spec_relpath": str(extension_spec_relpath),
        "suite_set_id": str(suite_set_id),
        "suite_set_relpath": str(suite_set_relpath),
    }

    next_ledger_no_id = {
        "schema_version": "kernel_extension_ledger_v1",
        "ledger_id": "sha256:" + ("0" * 64),
        "anchor_ek_id": str(active_ek_id),
        "parent_ledger_id": str(active_ledger_id),
        "entries": [dict(row) for row in entries] + [next_entry],
    }
    next_ledger = dict(next_ledger_no_id)
    next_ledger_no_id.pop("ledger_id", None)
    next_ledger["ledger_id"] = canon_hash_obj(next_ledger_no_id)

    ledgers_dir = repo_root / "authority" / "eval_kernel_ledgers"
    ledger_path, _ledger_payload, new_ledger_id = _write_hashed(
        ledgers_dir,
        "kernel_extension_ledger_v1.json",
        next_ledger,
    )
    write_canon_json(ledgers_dir / "kernel_extension_ledger_active_v1.json", next_ledger)

    append_receipt_no_id = {
        "schema_version": "kernel_extension_append_receipt_v1",
        "append_receipt_id": "sha256:" + ("0" * 64),
        "active_ek_id": str(active_ek_id),
        "prior_ledger_id": str(active_ledger_id),
        "new_ledger_id": str(new_ledger_id),
        "extension_spec_id": str(extension_spec_id),
        "suite_set_id": str(suite_set_id),
        "ordinal_u64": int(next_ordinal_u64),
    }
    append_receipt = dict(append_receipt_no_id)
    append_receipt_no_id.pop("append_receipt_id", None)
    append_receipt["append_receipt_id"] = canon_hash_obj(append_receipt_no_id)
    receipts_dir = ledgers_dir / "receipts"
    receipt_path, _receipt_payload, _receipt_id = _write_hashed(
        receipts_dir,
        "kernel_extension_append_receipt_v1.json",
        append_receipt,
    )
    write_canon_json(receipts_dir / "kernel_extension_append_receipt_v1.json", append_receipt)

    print("VALID")
    print(f"NEW_LEDGER_ID={new_ledger_id}")
    print(f"NEW_LEDGER_PATH={ledger_path}")
    print(f"APPEND_RECEIPT_PATH={receipt_path}")


if __name__ == "__main__":
    main()
