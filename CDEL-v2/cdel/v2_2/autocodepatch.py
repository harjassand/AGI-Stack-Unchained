"""CSI autocodepatch enumerator for v2.2."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed, write_canon_json
from .code_patch import compute_patch_id, next_pow2_clamp, tree_entries_v1, tree_hash_from_entries
from .constants import require_constants


def _ensure_import(lines: list[str]) -> list[str]:
    if any(line.strip() == "from functools import lru_cache" for line in lines):
        return lines
    insert_at = 0
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            insert_at = idx + 1
    lines = list(lines)
    lines.insert(insert_at, "from functools import lru_cache")
    return lines


def _ensure_decorator(lines: list[str], maxsize: int) -> list[str]:
    for idx, line in enumerate(lines):
        if line.startswith("def fingerprint_prompt_v1"):
            if idx > 0 and lines[idx - 1].strip().startswith("@lru_cache"):
                return lines
            lines = list(lines)
            lines.insert(idx, f"@lru_cache(maxsize={maxsize})")
            return lines
    raise CanonError("CSI_ENUM_EXHAUSTED")


def _apply_patch_text(source_text: str, maxsize: int) -> str:
    had_newline = source_text.endswith("\n")
    lines = source_text.splitlines()
    lines = _ensure_import(lines)
    lines = _ensure_decorator(lines, maxsize)
    out = "\n".join(lines)
    if had_newline:
        out += "\n"
    return out


def autocodepatch_enum_v1(
    base_tree_dir: Path,
    candidate_rank: int,
    concept_binding: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    if candidate_rank != 0:
        raise CanonError("CSI_ENUM_EXHAUSTED")

    constants = require_constants()
    allowed_roots = list(constants.get("CSI_ALLOWED_ROOTS", []))
    immutable_paths = list(constants.get("CSI_IMMUTABLE_PATHS", []))

    entries = tree_entries_v1(base_tree_dir, allowed_roots, immutable_paths)
    base_tree_hash = tree_hash_from_entries(entries)

    concept_output = concept_binding.get("concept_eval_output_int")
    if not isinstance(concept_output, int) or concept_output < 0:
        raise CanonError("CONCEPT_OUTPUT_INVALID")
    maxsize = next_pow2_clamp(int(concept_output), 1, 4096)

    relpath = "Extension-1/agi-orchestrator/orchestrator/proposer/csi_hotpath_v1.py"
    target_path = base_tree_dir / relpath
    if not target_path.exists():
        raise CanonError("MISSING_ARTIFACT")

    original_bytes = target_path.read_bytes()
    original_text = original_bytes.decode("utf-8")
    patched_text = _apply_patch_text(original_text, maxsize)
    patched_bytes = patched_text.encode("utf-8")

    before_sha = sha256_prefixed(original_bytes)
    after_sha = sha256_prefixed(patched_bytes)

    entries[relpath] = after_sha
    after_tree_hash = tree_hash_from_entries(entries)

    diff_lines = list(
        difflib.unified_diff(
            original_text.splitlines(),
            patched_text.splitlines(),
            fromfile=f"a/{relpath}",
            tofile=f"b/{relpath}",
            lineterm="",
        )
    )
    unified_diff = "\n".join(diff_lines) + "\n"

    patch = {
        "schema": "code_patch_v1",
        "patch_id": "__SELF__",
        "base_tree_hash": base_tree_hash,
        "after_tree_hash": after_tree_hash,
        "touched_files": [
            {
                "relpath": relpath,
                "before_sha256": before_sha,
                "after_sha256": after_sha,
                "unified_diff": unified_diff,
            }
        ],
        "concept_binding": concept_binding,
    }
    patch["patch_id"] = compute_patch_id(patch)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "code_patch.json"
    write_canon_json(out_path, patch)
    return patch


__all__ = ["autocodepatch_enum_v1"]
