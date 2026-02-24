"""Fail-closed verifier for APA kernel extension proposal winners."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from ..v18_0.authority.authority_hash_v1 import load_authority_pins
from ..v18_0.omega_common_v1 import OmegaV18Error, canon_hash_obj, load_canon_dict
from .common_v1 import validate_schema as validate_schema_v19


_MARKER_TOKENS = ("holdout", "hidden", "private", "secret", "masked")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _fail(reason: str) -> None:
    message = str(reason).strip() or "UNKNOWN"
    if not message.startswith("INVALID:"):
        message = f"INVALID:{message}"
    raise OmegaV18Error(message)


def _ensure_sha256(value: Any) -> str:
    text = str(value).strip()
    if _SHA256_RE.fullmatch(text) is None:
        _fail("EXT_SCHEMA_INVALID")
    return text


def _declared_id_matches(payload: dict[str, Any], id_field: str) -> bool:
    declared = _ensure_sha256(payload.get(id_field))
    material = dict(payload)
    material.pop(id_field, None)
    return str(canon_hash_obj(material)) == declared


def _normalize_relpath(path_value: Any) -> str:
    rel = str(path_value).strip().replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    path = Path(rel)
    if not rel or path.is_absolute() or ".." in path.parts:
        _fail("EXT_SCHEMA_INVALID")
    return rel


def _contains_marker(value: Any) -> bool:
    text = str(value).strip().lower()
    return any(token in text for token in _MARKER_TOKENS)


def _latest(path: Path, pattern: str) -> Path | None:
    rows = sorted(path.glob(pattern), key=lambda row: row.as_posix())
    return rows[-1] if rows else None


def _hash_from_filename(path: Path, suffix: str) -> str:
    name = path.name
    if not name.startswith("sha256_") or not name.endswith(suffix):
        _fail("EXT_SCHEMA_INVALID")
    digest = name[len("sha256_") : -len(suffix)]
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        _fail("EXT_SCHEMA_INVALID")
    return f"sha256:{digest}"


def _resolve_state_root(path: Path) -> Path:
    root = path.resolve()
    candidates = [
        root / "daemon" / "rsi_proposer_arena_v1" / "state",
        root,
    ]
    for candidate in candidates:
        if (candidate / "promotion").exists():
            return candidate
    _fail("EXT_SCHEMA_INVALID")
    return root


def _load_extension_payloads(promotion_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    ext_path = _latest(promotion_dir, "sha256_*.kernel_extension_spec_v1.json")
    manifest_path = _latest(promotion_dir, "sha256_*.benchmark_suite_manifest_v1.json")
    set_path = _latest(promotion_dir, "sha256_*.benchmark_suite_set_v1.json")
    if ext_path is None or manifest_path is None or set_path is None:
        _fail("EXT_SCHEMA_INVALID")

    ext_payload = load_canon_dict(ext_path)
    manifest_payload = load_canon_dict(manifest_path)
    set_payload = load_canon_dict(set_path)

    validate_schema_v19(ext_payload, "kernel_extension_spec_v1")
    validate_schema_v19(manifest_payload, "benchmark_suite_manifest_v1")
    validate_schema_v19(set_payload, "benchmark_suite_set_v1")

    if canon_hash_obj(ext_payload) != _hash_from_filename(ext_path, ".kernel_extension_spec_v1.json"):
        _fail("EXT_SCHEMA_INVALID")
    if canon_hash_obj(manifest_payload) != _hash_from_filename(manifest_path, ".benchmark_suite_manifest_v1.json"):
        _fail("EXT_SCHEMA_INVALID")
    if canon_hash_obj(set_payload) != _hash_from_filename(set_path, ".benchmark_suite_set_v1.json"):
        _fail("EXT_SCHEMA_INVALID")

    ext_id = _ensure_sha256(ext_payload.get("extension_spec_id"))
    manifest_id = _ensure_sha256(manifest_payload.get("suite_id"))
    set_id = _ensure_sha256(set_payload.get("suite_set_id"))
    if not _declared_id_matches(ext_payload, "extension_spec_id"):
        _fail("EXT_SCHEMA_INVALID")
    if not _declared_id_matches(manifest_payload, "suite_id"):
        _fail("EXT_SCHEMA_INVALID")
    if not _declared_id_matches(set_payload, "suite_set_id"):
        _fail("EXT_SCHEMA_INVALID")
    return ext_payload, manifest_payload, set_payload


def _phase1_public_only_guard(ext_payload: dict[str, Any], manifest_payload: dict[str, Any], set_payload: dict[str, Any]) -> None:
    visibility = str(manifest_payload.get("visibility", "")).strip().upper()
    if visibility != "PUBLIC":
        _fail("PHASE1_PUBLIC_ONLY_VIOLATION")
    if _contains_marker(manifest_payload.get("suite_name")):
        _fail("PHASE1_PUBLIC_ONLY_VIOLATION")
    if _contains_marker(ext_payload.get("extension_name")):
        _fail("PHASE1_PUBLIC_ONLY_VIOLATION")
    labels = manifest_payload.get("labels")
    if isinstance(labels, list):
        for row in labels:
            if _contains_marker(row):
                _fail("PHASE1_PUBLIC_ONLY_VIOLATION")
    for value in (
        manifest_payload.get("suite_runner_relpath"),
        ext_payload.get("suite_set_relpath"),
    ):
        if _contains_marker(value):
            _fail("PHASE1_PUBLIC_ONLY_VIOLATION")
    suites = set_payload.get("suites")
    if not isinstance(suites, list) or not suites:
        _fail("EXT_SCHEMA_INVALID")
    for row in suites:
        if not isinstance(row, dict):
            _fail("EXT_SCHEMA_INVALID")
        if _contains_marker(row.get("suite_manifest_relpath")):
            _fail("PHASE1_PUBLIC_ONLY_VIOLATION")


def _suite_uniqueness_and_order(manifest_payload: dict[str, Any], set_payload: dict[str, Any]) -> None:
    suites = set_payload.get("suites")
    if not isinstance(suites, list) or not suites:
        _fail("EXT_SCHEMA_INVALID")
    seen_ids: set[str] = set()
    tuples: list[tuple[int, str]] = []
    for row in suites:
        if not isinstance(row, dict):
            _fail("EXT_SCHEMA_INVALID")
        suite_id = _ensure_sha256(row.get("suite_id"))
        if suite_id in seen_ids:
            _fail("EXT_SCHEMA_INVALID")
        seen_ids.add(suite_id)
        ordinal = int(max(0, int(row.get("ordinal_u64", 0))))
        tuples.append((ordinal, suite_id))
        if _ensure_sha256(row.get("suite_manifest_id")) != _ensure_sha256(manifest_payload.get("suite_id")):
            _fail("EXT_SCHEMA_INVALID")
    if tuples != sorted(tuples):
        _fail("EXT_SCHEMA_INVALID")


def _forbidden_reference_guard(*, root: Path, ext_payload: dict[str, Any], manifest_payload: dict[str, Any], set_payload: dict[str, Any]) -> None:
    allowlists = load_canon_dict(root / "authority" / "ccap_patch_allowlists_v1.json")
    forbid_prefixes = allowlists.get("forbid_prefixes")
    if not isinstance(forbid_prefixes, list):
        _fail("EXT_SCHEMA_INVALID")
    referenced_paths: list[str] = []
    referenced_paths.append(_normalize_relpath(ext_payload.get("suite_set_relpath")))
    referenced_paths.append(_normalize_relpath(manifest_payload.get("suite_runner_relpath")))
    for row in list(set_payload.get("suites") or []):
        if isinstance(row, dict):
            referenced_paths.append(_normalize_relpath(row.get("suite_manifest_relpath")))
    for rel in referenced_paths:
        if any(rel.startswith(str(prefix)) for prefix in forbid_prefixes):
            _fail("EXT_SCHEMA_INVALID")


def _ledger_conflict_guard(*, root: Path, ext_payload: dict[str, Any], set_payload: dict[str, Any]) -> None:
    pins = load_authority_pins(root)
    active_ledger_id = _ensure_sha256(pins.get("active_kernel_extensions_ledger_id"))
    ext_id = _ensure_sha256(ext_payload.get("extension_spec_id"))
    suite_set_id = _ensure_sha256(set_payload.get("suite_set_id"))
    ledgers_dir = root / "authority" / "eval_kernel_ledgers"
    matches = []
    for path in sorted(ledgers_dir.glob("*.json"), key=lambda row: row.as_posix()):
        payload = load_canon_dict(path)
        if str(payload.get("schema_version", "")).strip() != "kernel_extension_ledger_v1":
            continue
        validate_schema_v19(payload, "kernel_extension_ledger_v1")
        if canon_hash_obj(payload) != _ensure_sha256(payload.get("ledger_id")):
            _fail("EXT_LEDGER_CONFLICT")
        if _ensure_sha256(payload.get("ledger_id")) == active_ledger_id:
            matches.append(payload)
    if len(matches) != 1:
        _fail("EXT_LEDGER_CONFLICT")
    ledger = matches[0]
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        _fail("EXT_LEDGER_CONFLICT")
    for idx, row in enumerate(entries):
        if not isinstance(row, dict):
            _fail("EXT_LEDGER_CONFLICT")
        if int(row.get("ordinal_u64", -1)) != idx:
            _fail("EXT_LEDGER_CONFLICT")
        if _ensure_sha256(row.get("extension_spec_id")) == ext_id:
            _fail("EXT_LEDGER_CONFLICT")
        if _ensure_sha256(row.get("suite_set_id")) == suite_set_id:
            _fail("EXT_LEDGER_CONFLICT")


def verify_extension_proposal_dir(*, promotion_dir: Path) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = Path(__file__).resolve().parents[3]
    ext_payload, manifest_payload, set_payload = _load_extension_payloads(promotion_dir)
    _phase1_public_only_guard(ext_payload, manifest_payload, set_payload)
    _suite_uniqueness_and_order(manifest_payload, set_payload)
    _forbidden_reference_guard(root=root, ext_payload=ext_payload, manifest_payload=manifest_payload, set_payload=set_payload)
    _ledger_conflict_guard(root=root, ext_payload=ext_payload, set_payload=set_payload)
    extension_id = _ensure_sha256(ext_payload.get("extension_spec_id"))
    return extension_id, ext_payload, manifest_payload, set_payload


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        _fail("MODE_UNSUPPORTED")
    state_root = _resolve_state_root(state_dir)
    promotion_dir = state_root / "promotion"
    _extension_id, _ext_payload, _manifest_payload, _set_payload = verify_extension_proposal_dir(
        promotion_dir=promotion_dir,
    )
    return "VALID"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="verify_kernel_extension_proposal_v1")
    parser.add_argument("--mode", default="full")
    parser.add_argument("--state_dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        print(verify(Path(args.state_dir).resolve(), mode=str(args.mode)))
    except OmegaV18Error as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
