from __future__ import annotations

from pathlib import Path
from typing import Any

from ...v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed


def canonical_json_bytes(path: Path) -> bytes:
    obj = load_canon_json(path)
    return canon_bytes(obj)


def canonical_json_hash(path: Path) -> str:
    return sha256_prefixed(canonical_json_bytes(path))


def compare_decision_files(ref_path: Path, kernel_path: Path) -> tuple[bool, str]:
    ref_bytes = canonical_json_bytes(ref_path)
    kernel_bytes = canonical_json_bytes(kernel_path)
    if ref_bytes == kernel_bytes:
        return True, "OK"
    return False, f"MISMATCH:{sha256_prefixed(ref_bytes)}:{sha256_prefixed(kernel_bytes)}"


def build_case_parity_row(case_id: str, ref_path: Path, kernel_path: Path) -> dict[str, Any]:
    ok, reason = compare_decision_files(ref_path, kernel_path)
    return {
        "case_id": case_id,
        "ok": ok,
        "reason": reason,
        "ref_hash": canonical_json_hash(ref_path),
        "kernel_hash": canonical_json_hash(kernel_path),
    }


__all__ = [
    "canonical_json_bytes",
    "canonical_json_hash",
    "compare_decision_files",
    "build_case_parity_row",
]
