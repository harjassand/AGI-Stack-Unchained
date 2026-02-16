#!/usr/bin/env python3
"""Verify a release pack contains valid capsules, receipt, and certificate."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import shlex
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Dict

from genesis.capsules.canonicalize import canonical_bytes, capsule_hash, receipt_hash
from genesis.capsules.receipt import verify_receipt


def _load_public_keys(keystore_dir: Path) -> dict[str, bytes]:
    path = keystore_dir / "public_keys.jsonl"
    if not path.exists():
        return {}
    keys: dict[str, bytes] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        key_id = entry.get("key_id")
        secret_b64 = entry.get("secret_b64")
        if key_id and secret_b64:
            keys[str(key_id)] = base64.b64decode(secret_b64)
    return keys


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_certificate_signature(cert: dict, keys: dict[str, bytes]) -> bool:
    signature = cert.get("signature") or {}
    key_id = signature.get("key_id")
    alg = signature.get("alg")
    sig_b64 = signature.get("sig_b64")
    if not key_id or alg != "hmac-sha256" or not sig_b64:
        return False
    key = keys.get(str(key_id))
    if key is None:
        return False
    payload = dict(cert)
    payload.pop("signature", None)
    expected = hmac.new(key, canonical_bytes(payload), hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected).decode("utf-8")
    return hmac.compare_digest(sig_b64, expected_b64)


def _read_member(tar: tarfile.TarFile, name: str) -> bytes:
    member = tar.getmember(name)
    fp = tar.extractfile(member)
    if fp is None:
        raise ValueError(f"missing member: {name}")
    return fp.read()


def _revoked(cert_hash: str, receipt_hash_value: str, revocations_path: Path, keys: dict[str, bytes]) -> bool:
    if not revocations_path.exists():
        return False
    for line in revocations_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("receipt_hash") != receipt_hash_value and entry.get("certificate_hash") != cert_hash:
            continue
        signature = entry.get("signature") or {}
        key_id = signature.get("key_id")
        alg = signature.get("alg")
        sig_b64 = signature.get("sig_b64")
        if not key_id or alg != "hmac-sha256" or not sig_b64:
            return True
        key = keys.get(str(key_id))
        if key is None:
            return True
        payload = dict(entry)
        payload.pop("signature", None)
        sig = hmac.new(key, canonical_bytes(payload), hashlib.sha256).digest()
        if not hmac.compare_digest(sig_b64, base64.b64encode(sig).decode("utf-8")):
            return True
        return True
    return False


def _find_eval_bundle(files: dict) -> str | None:
    for name in files.keys():
        if name.startswith("eval_bundle_") and name.endswith(".tar.gz"):
            return name
    return None


def verify_release_pack(
    tar_path: Path,
    keystore_dir: Path,
    revocations_path: Path | None = None,
    cdel_verify_tool_cmd: str | None = None,
) -> None:
    keys = _load_public_keys(keystore_dir)
    with tarfile.open(tar_path, "r:gz") as tar:
        manifest_bytes = _read_member(tar, "release_pack_manifest.json")
        manifest = json.loads(manifest_bytes.decode("utf-8"))

        files = manifest.get("files") or {}
        for name, expected_hash in files.items():
            data = _read_member(tar, name)
            if _sha256_bytes(data) != expected_hash:
                raise ValueError(f"hash mismatch for {name}")

        system_capsule = json.loads(_read_member(tar, "system_capsule.json").decode("utf-8"))
        system_hash = capsule_hash(system_capsule)
        if system_hash != manifest.get("capsule_hash"):
            raise ValueError("system capsule hash mismatch")

        receipt = json.loads(_read_member(tar, "receipt.json").decode("utf-8"))
        ok, err = verify_receipt(receipt, system_capsule, receipt.get("epoch_id", ""))
        if not ok:
            raise ValueError(f"receipt verification failed: {err}")

        cert = json.loads(_read_member(tar, "promotion_certificate.json").decode("utf-8"))
        if cert.get("specpack_tag") != "v1.0.1":
            raise ValueError("certificate specpack tag mismatch")
        if cert.get("capsule_hash") != system_hash:
            raise ValueError("certificate capsule hash mismatch")
        if cert.get("receipt_hash") != receipt_hash(receipt):
            raise ValueError("certificate receipt hash mismatch")
        if not _verify_certificate_signature(cert, keys):
            raise ValueError("certificate signature invalid")
        if revocations_path and _revoked(_sha256_bytes(canonical_bytes(cert)), receipt_hash(receipt), revocations_path, keys):
            raise ValueError("certificate revoked")

        eval_bundle_name = _find_eval_bundle(files)
        if eval_bundle_name:
            if not cdel_verify_tool_cmd:
                raise ValueError("cdel_verify_tool_cmd required for eval bundle verification")
            bundle_bytes = _read_member(tar, eval_bundle_name)
            with tempfile.TemporaryDirectory() as tmp:
                bundle_path = Path(tmp) / eval_bundle_name
                bundle_path.write_bytes(bundle_bytes)
                cmd = shlex.split(cdel_verify_tool_cmd) + ["--bundle", str(bundle_path)]
                subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a Genesis release pack.")
    parser.add_argument("--pack", required=True)
    parser.add_argument("--keystore-dir", required=True)
    parser.add_argument("--revocations", default="")
    parser.add_argument("--cdel-verify-tool-cmd", default="")
    args = parser.parse_args()

    revocations = Path(args.revocations) if args.revocations else None
    verify_release_pack(
        Path(args.pack),
        Path(args.keystore_dir),
        revocations,
        cdel_verify_tool_cmd=args.cdel_verify_tool_cmd or None,
    )
    print("release pack OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
