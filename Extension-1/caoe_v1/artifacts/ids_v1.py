"""Hashing and ID derivations for CAOE v1 proposer."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[1]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from api_v1 import canonical_json_bytes  # noqa: E402


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_json(obj: Any) -> str:
    return sha256_hex(canonical_json_bytes(obj))


def ontology_hash(spec: Any) -> str:
    spec_copy = dict(spec)
    if "ontology_hash" in spec_copy:
        spec_copy["ontology_hash"] = "0" * 64
    return hash_json(spec_copy)


def mechanism_hash(registry: Any) -> str:
    return hash_json(registry)


def candidate_id(
    manifest: Any,
    ontology_patch: Any,
    mechanism_diff: Any | None,
    programs_by_path: dict[str, bytes],
) -> str:
    manifest_copy = dict(manifest)
    if "candidate_id" in manifest_copy:
        manifest_copy["candidate_id"] = "0" * 64
    manifest_bytes = canonical_json_bytes(manifest_copy)
    patch_hash_bytes = bytes.fromhex(hash_json(ontology_patch))
    if mechanism_diff is None:
        mechanism_diff = {}
    mech_hash_bytes = bytes.fromhex(hash_json(mechanism_diff))
    concat_programs = b""
    for path in sorted(programs_by_path):
        concat_programs += programs_by_path[path]
    programs_hash_bytes = bytes.fromhex(sha256_hex(concat_programs))
    payload = manifest_bytes + patch_hash_bytes + mech_hash_bytes + programs_hash_bytes
    return sha256_hex(payload)
