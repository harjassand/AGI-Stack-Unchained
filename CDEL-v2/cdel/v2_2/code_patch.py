"""CSI code patch utilities for v2.2."""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Any, Iterable

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed
from .constants import require_constants


MAX_U64 = (1 << 64) - 1


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return f"sha256:{h.hexdigest()}"


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def tree_entries_v1(root_dir: Path, allowed_roots: list[str], immutable_paths: list[str]) -> dict[str, str]:
    entries: dict[str, str] = {}
    for root in allowed_roots:
        root_path = root_dir / root
        if not root_path.exists():
            raise CanonError("MISSING_ARTIFACT")
        for path in sorted(root_path.rglob("*")):
            if not path.is_file():
                continue
            relpath = path.relative_to(root_dir).as_posix()
            if _is_immutable(relpath, immutable_paths):
                continue
            entries[relpath] = _sha256_file(path)
    return entries


def tree_hash_from_entries(entries: dict[str, str]) -> str:
    files = [{"relpath": relpath, "sha256": sha} for relpath, sha in sorted(entries.items())]
    payload = {"files": files}
    return sha256_prefixed(canon_bytes(payload))


def tree_hash_v1(root_dir: Path, allowed_roots: list[str], immutable_paths: list[str]) -> str:
    entries = tree_entries_v1(root_dir, allowed_roots, immutable_paths)
    return tree_hash_from_entries(entries)


def compute_patch_id(patch: dict[str, Any]) -> str:
    payload = dict(patch)
    payload.pop("patch_id", None)
    return sha256_prefixed(canon_bytes(payload))


def _is_immutable(relpath: str, immutable_paths: Iterable[str]) -> bool:
    for prefix in immutable_paths:
        if relpath.startswith(prefix):
            return True
    return False


def _allowed_path(relpath: str, allowed_roots: Iterable[str]) -> bool:
    return any(relpath.startswith(root) for root in allowed_roots)


def _diff_stats(unified_diff: str) -> tuple[int, int, int]:
    added = 0
    removed = 0
    total_bytes = len(unified_diff.encode("utf-8"))
    for line in unified_diff.splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed, total_bytes


def _parse_hunk_header(line: str) -> tuple[int, int, int, int]:
    m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
    if not m:
        raise CanonError("PATCH_APPLY_INVALID")
    a_start = int(m.group(1))
    a_count = int(m.group(2) or "1")
    b_start = int(m.group(3))
    b_count = int(m.group(4) or "1")
    return a_start, a_count, b_start, b_count


def apply_unified_diff(original_text: str, diff_text: str) -> str:
    orig_lines = original_text.splitlines()
    had_trailing_newline = original_text.endswith("\n")
    diff_lines = diff_text.splitlines()

    out_lines: list[str] = []
    idx = 0
    line_idx = 0
    while line_idx < len(diff_lines):
        line = diff_lines[line_idx]
        if line.startswith("---") or line.startswith("+++"):
            line_idx += 1
            continue
        if not line.startswith("@@"):
            line_idx += 1
            continue
        a_start, _a_count, _b_start, _b_count = _parse_hunk_header(line)
        target_index = a_start - 1
        if target_index < idx:
            raise CanonError("PATCH_APPLY_INVALID")
        while idx < target_index:
            out_lines.append(orig_lines[idx])
            idx += 1
        line_idx += 1
        while line_idx < len(diff_lines) and not diff_lines[line_idx].startswith("@@"):
            hline = diff_lines[line_idx]
            if hline.startswith(" "):
                content = hline[1:]
                if idx >= len(orig_lines) or orig_lines[idx] != content:
                    raise CanonError("PATCH_APPLY_INVALID")
                out_lines.append(orig_lines[idx])
                idx += 1
            elif hline.startswith("-"):
                content = hline[1:]
                if idx >= len(orig_lines) or orig_lines[idx] != content:
                    raise CanonError("PATCH_APPLY_INVALID")
                idx += 1
            elif hline.startswith("+"):
                out_lines.append(hline[1:])
            elif hline.startswith("\\"):
                # "No newline at end of file" marker
                pass
            else:
                raise CanonError("PATCH_APPLY_INVALID")
            line_idx += 1
    while idx < len(orig_lines):
        out_lines.append(orig_lines[idx])
        idx += 1
    result = "\n".join(out_lines)
    if had_trailing_newline:
        result += "\n"
    return result


def scan_forbidden(
    source_text: str,
    *,
    forbidden_imports: set[str],
    forbidden_syntax: set[str],
) -> tuple[bool, bool]:
    """Return (has_forbidden_import, has_forbidden_syntax)."""
    try:
        tree = ast.parse(source_text)
    except Exception as exc:  # noqa: BLE001
        raise CanonError("FORBIDDEN_SYNTAX") from exc

    has_forbidden_import = False
    has_forbidden_syntax = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                if name in forbidden_imports:
                    has_forbidden_import = True
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                name = node.module.split(".")[0]
                if name in forbidden_imports:
                    has_forbidden_import = True
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in forbidden_syntax:
                has_forbidden_syntax = True
            elif isinstance(func, ast.Attribute) and func.attr in forbidden_syntax:
                has_forbidden_syntax = True
    return has_forbidden_import, has_forbidden_syntax


def validate_patch_constraints(
    patch: dict[str, Any],
    *,
    allowed_roots: list[str],
    immutable_paths: list[str],
    max_files: int,
    max_patch_bytes: int,
    max_lines_added: int,
    max_lines_removed: int,
) -> None:
    touched = patch.get("touched_files")
    if not isinstance(touched, list):
        raise CanonError("SCHEMA_INVALID")
    if len(touched) > max_files:
        raise CanonError("PATCH_SIZE_VIOLATION")

    total_added = 0
    total_removed = 0
    total_bytes = 0

    for entry in touched:
        if not isinstance(entry, dict):
            raise CanonError("SCHEMA_INVALID")
        relpath = entry.get("relpath")
        if not isinstance(relpath, str):
            raise CanonError("SCHEMA_INVALID")
        if not _allowed_path(relpath, allowed_roots) or _is_immutable(relpath, immutable_paths):
            raise CanonError("PATCH_TARGET_VIOLATION")
        diff = entry.get("unified_diff")
        if not isinstance(diff, str):
            raise CanonError("SCHEMA_INVALID")
        added, removed, bytes_len = _diff_stats(diff)
        total_added += added
        total_removed += removed
        total_bytes += bytes_len

    if total_bytes > max_patch_bytes or total_added > max_lines_added or total_removed > max_lines_removed:
        raise CanonError("PATCH_SIZE_VIOLATION")


def apply_patch_to_tree(
    base_dir: Path,
    patch: dict[str, Any],
) -> dict[str, bytes]:
    """Apply patch to base_dir and return updated file contents (in-memory)."""
    touched = patch.get("touched_files")
    if not isinstance(touched, list):
        raise CanonError("SCHEMA_INVALID")
    updated: dict[str, bytes] = {}

    for entry in touched:
        if not isinstance(entry, dict):
            raise CanonError("SCHEMA_INVALID")
        relpath = entry.get("relpath")
        if not isinstance(relpath, str):
            raise CanonError("SCHEMA_INVALID")
        file_path = base_dir / relpath
        if not file_path.exists():
            raise CanonError("PATCH_APPLY_INVALID")
        before_sha = entry.get("before_sha256")
        if not isinstance(before_sha, str):
            raise CanonError("SCHEMA_INVALID")
        original_bytes = file_path.read_bytes()
        if _sha256_bytes(original_bytes) != before_sha:
            raise CanonError("PATCH_APPLY_INVALID")
        diff = entry.get("unified_diff")
        if not isinstance(diff, str):
            raise CanonError("SCHEMA_INVALID")
        original_text = original_bytes.decode("utf-8")
        patched_text = apply_unified_diff(original_text, diff)
        patched_bytes = patched_text.encode("utf-8")
        after_sha = entry.get("after_sha256")
        if not isinstance(after_sha, str):
            raise CanonError("SCHEMA_INVALID")
        if _sha256_bytes(patched_bytes) != after_sha:
            raise CanonError("PATCH_APPLY_INVALID")
        updated[relpath] = patched_bytes

    return updated


def validate_concept_binding(patch: dict[str, Any]) -> None:
    if not isinstance(patch.get("concept_binding"), dict):
        raise CanonError("CONCEPT_MISSING")


def next_pow2_clamp(value: int, lo: int, hi: int) -> int:
    if value < lo:
        value = lo
    if value > hi:
        value = hi
    if value <= 1:
        return 1
    out = 1
    while out < value:
        if out > MAX_U64 // 2:
            raise CanonError("CONCEPT_OUTPUT_INVALID")
        out <<= 1
    return out


__all__ = [
    "apply_patch_to_tree",
    "apply_unified_diff",
    "compute_patch_id",
    "next_pow2_clamp",
    "scan_forbidden",
    "tree_entries_v1",
    "tree_hash_from_entries",
    "tree_hash_v1",
    "validate_concept_binding",
    "validate_patch_constraints",
]
