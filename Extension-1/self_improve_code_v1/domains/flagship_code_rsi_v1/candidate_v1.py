"""Candidate bundle helpers (v1)."""

from __future__ import annotations

import hashlib
from typing import Dict, Optional, Tuple

from ...canon.json_canon_v1 import canon_bytes

DOMAIN_SEP = b"repo_patch_candidate_v1\x00"


def compute_candidate_hashes(manifest: Dict, patch_bytes: bytes, policy_bytes: Optional[bytes]) -> Tuple[str, str, str, str]:
    manifest_for_hash = dict(manifest)
    manifest_for_hash.pop("candidate_id", None)
    manifest_canon = canon_bytes(manifest_for_hash)
    manifest_hash = hashlib.sha256(manifest_canon).hexdigest()
    patch_hash = hashlib.sha256(patch_bytes).hexdigest()
    policy_hash = hashlib.sha256(policy_bytes if policy_bytes is not None else b"").hexdigest()
    bundle_hash = hashlib.sha256(DOMAIN_SEP + bytes.fromhex(manifest_hash) + bytes.fromhex(patch_hash) + bytes.fromhex(policy_hash)).hexdigest()
    return manifest_hash, patch_hash, policy_hash, bundle_hash


def build_manifest(
    *,
    base_commit: str,
    eval_plan_id: str,
    patch_bytes: bytes,
    target_repo_id: str,
    patch_format: str = "unidiff",
) -> Dict:
    patch_hash = hashlib.sha256(patch_bytes).hexdigest()
    manifest = {
        "version": "repo_patch_candidate_v1",
        "format": "repo_patch_candidate_v1",
        "schema_version": "1",
        "candidate_id": "",
        "target_repo_id": target_repo_id,
        "base": {"git_commit": base_commit},
        "eval_plan_id": eval_plan_id,
        "patch": {
            "format": patch_format,
            "sha256": patch_hash,
            "byte_length": len(patch_bytes),
            "bytes": len(patch_bytes),
        },
    }
    _manifest_hash, _patch_hash, _policy_hash, candidate_id = compute_candidate_hashes(manifest, patch_bytes, None)
    manifest["candidate_id"] = candidate_id
    return manifest


__all__ = ["build_manifest", "compute_candidate_hashes", "DOMAIN_SEP"]
