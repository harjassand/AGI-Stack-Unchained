import hashlib
import json
import os
from typing import Any, Dict

import gcj1_min


TOOLCHAIN_FILES = [
    "kernel/verifier/toolchain.lock",
    "kernel/verifier/Cargo.lock",
    "kernel/verifier/KERNEL_HASH",
    "kernel/verifier/build.sh",
    "meta_constitution/v1/META_HASH",
    "meta_constitution/v1/build_meta_hash.sh",
    "scripts/build.sh",
]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _canonical_bytes(obj: Any) -> bytes:
    return gcj1_min.dumps_bytes(obj)


def manifest_for_hash(manifest: Dict[str, Any]) -> Dict[str, Any]:
    out = json.loads(json.dumps(manifest, separators=(",", ":")))
    out["bundle_hash"] = ""
    if "manifest_hash" in out:
        out["manifest_hash"] = ""
    return out


def manifest_hash(manifest: Dict[str, Any]) -> str:
    payload = _canonical_bytes(manifest_for_hash(manifest))
    return _sha256_bytes(payload)


def ruleset_hash(bundle_dir: str) -> str:
    accept = _canonical_bytes(_read_json(os.path.join(bundle_dir, "ruleset", "accept.ir.json")))
    cost = _canonical_bytes(_read_json(os.path.join(bundle_dir, "ruleset", "costvec.ir.json")))
    migrate = _canonical_bytes(_read_json(os.path.join(bundle_dir, "ruleset", "migrate.ir.json")))
    payload = accept + b"\0" + cost + b"\0" + migrate
    return _sha256_bytes(payload)


def proof_bundle_hash(bundle_dir: str) -> str:
    proof_manifest = _read_json(os.path.join(bundle_dir, "proofs", "proof_bundle.manifest.json"))
    payload = _canonical_bytes(proof_manifest)
    return _sha256_bytes(payload)


def migration_hash(bundle_dir: str) -> str:
    migrate = _canonical_bytes(_read_json(os.path.join(bundle_dir, "ruleset", "migrate.ir.json")))
    return _sha256_bytes(migrate)


def state_schema_hash(meta_core_root: str) -> str:
    path = os.path.join(meta_core_root, "meta_constitution", "v1", "schemas", "migration.schema.json")
    with open(path, "rb") as f:
        data = f.read()
    return _sha256_bytes(data)


def toolchain_merkle_root(meta_core_root: str) -> str:
    files = []
    for rel in TOOLCHAIN_FILES:
        path = os.path.join(meta_core_root, rel)
        with open(path, "rb") as f:
            data = f.read()
        files.append({"path": rel, "sha256": _sha256_bytes(data), "bytes": len(data)})
    files.sort(key=lambda item: item["path"])
    payload = {"version": 1, "files": files}
    return _sha256_bytes(_canonical_bytes(payload))


def bundle_hash(
    manifest_hash_hex: str,
    ruleset_hash_hex: str,
    proof_bundle_hash_hex: str,
    migration_hash_hex: str,
    state_schema_hash_hex: str,
    toolchain_merkle_root_hex: str,
) -> str:
    parts = [
        bytes.fromhex(manifest_hash_hex),
        b"\0",
        bytes.fromhex(ruleset_hash_hex),
        b"\0",
        bytes.fromhex(proof_bundle_hash_hex),
        b"\0",
        bytes.fromhex(migration_hash_hex),
        b"\0",
        bytes.fromhex(state_schema_hash_hex),
        b"\0",
        bytes.fromhex(toolchain_merkle_root_hex),
    ]
    return _sha256_bytes(b"".join(parts))
