"""Manifest builder (v1)."""

from __future__ import annotations

from typing import Dict

from .candidate_hash_v1 import compute_candidate_id, patch_sha256_hex


def build_manifest(base_commit: str, eval_plan_id: str, patch_text: str, stats: Dict[str, int]) -> Dict:
    patch_bytes = patch_text.encode("utf-8")
    patch_hash = patch_sha256_hex(patch_bytes)
    manifest = {
        "candidate_id": "",
        "base": {"git_commit": base_commit},
        "eval_plan_id": eval_plan_id,
        "patch": {
            "sha256": patch_hash,
            "byte_length": len(patch_bytes),
            "files_changed": int(stats.get("files_changed", 0)),
            "lines_added": int(stats.get("lines_added", 0)),
            "lines_removed": int(stats.get("lines_removed", 0)),
        },
    }
    candidate_id, _, _, _ = compute_candidate_id(manifest, patch_bytes)
    manifest["candidate_id"] = candidate_id
    return manifest


__all__ = ["build_manifest"]
