#!/usr/bin/env python3
"""Build a deterministic release pack for a promoted SYSTEM capsule."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import tarfile
from pathlib import Path
from typing import Dict, Tuple

from genesis.capsules.canonicalize import capsule_hash, receipt_hash
from genesis.core.component_store import ComponentStore


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _find_receipt(receipts_dir: Path, capsule_hash_value: str) -> Tuple[dict, str]:
    index_path = receipts_dir / "receipts.jsonl"
    if not index_path.exists():
        raise ValueError("receipts.jsonl not found")
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("capsule_hash") == capsule_hash_value:
            receipt_raw_hash = record.get("receipt_hash_raw") or ""
            if not receipt_raw_hash:
                raise ValueError("receipt_hash_raw missing for capsule")
            receipt_path = receipts_dir / f"receipt_{receipt_raw_hash}.json"
            if not receipt_path.exists():
                raise ValueError("receipt file not found")
            return _load_json(receipt_path), receipt_raw_hash
    raise ValueError("no receipt found for capsule hash")


def _write_file(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _build_manifest(
    files: Dict[str, Path],
    capsule_hash_value: str,
    receipt_hash_value: str,
    cert_hash: str,
    eval_bundle_hash: str | None,
) -> dict:
    file_hashes = {}
    for name, path in files.items():
        file_hashes[name] = _sha256_bytes(path.read_bytes())
    manifest = {
        "specpack_tag": "v1.0.1",
        "capsule_hash": capsule_hash_value,
        "receipt_hash": receipt_hash_value,
        "certificate_hash": cert_hash,
        "files": file_hashes,
    }
    if eval_bundle_hash:
        manifest["eval_bundle_hash"] = eval_bundle_hash
    return manifest


def _write_tarball(source_dir: Path, tar_path: Path) -> None:
    files = sorted([p for p in source_dir.rglob("*") if p.is_file()])
    with tarfile.open(tar_path, "w:gz") as tar:
        for path in files:
            rel = path.relative_to(source_dir)
            info = tar.gettarinfo(str(path), arcname=str(rel))
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            with path.open("rb") as fp:
                tar.addfile(info, fp)


def build_release_pack(
    capsule_hash_value: str,
    component_store_dir: Path,
    receipts_dir: Path,
    ledger_dir: Path,
    out_dir: Path,
    include_eval_bundle: bool = False,
    cdel_ledger_dir: Path | None = None,
    cdel_export_tool_cmd: str | None = None,
) -> Tuple[Path, Path, Path]:
    store = ComponentStore(component_store_dir)
    system_path = store.path_for_hash(capsule_hash_value)
    if not system_path.exists():
        raise ValueError("system capsule not found in component store")

    system_capsule = _load_json(system_path)
    if capsule_hash(system_capsule) != capsule_hash_value:
        raise ValueError("system capsule hash mismatch")
    components = system_capsule.get("x-system", {}).get("components", {})
    policy_hash = components.get("policy", {}).get("hash", "")
    world_model_hash = components.get("world_model", {}).get("hash", "")
    if not policy_hash or not world_model_hash:
        raise ValueError("missing component hashes in system capsule")

    policy_path = store.path_for_hash(policy_hash)
    world_model_path = store.path_for_hash(world_model_hash)
    if not policy_path.exists() or not world_model_path.exists():
        raise ValueError("component capsule missing in component store")

    receipt, receipt_raw_hash = _find_receipt(receipts_dir, capsule_hash_value)
    if receipt_hash(receipt) != receipt_raw_hash:
        raise ValueError("receipt hash mismatch")
    epoch_id = receipt.get("epoch_id", "")
    if not epoch_id:
        raise ValueError("receipt missing epoch_id")

    cert_path = ledger_dir / epoch_id / "certs" / f"{receipt_raw_hash}.json"
    if not cert_path.exists():
        raise ValueError("promotion certificate not found")

    cert_hash = _sha256_bytes(cert_path.read_bytes())

    pack_dir = out_dir / f"release_pack_{capsule_hash_value}"
    pack_dir.mkdir(parents=True, exist_ok=True)

    files: Dict[str, Path] = {}
    files["system_capsule.json"] = pack_dir / "system_capsule.json"
    files["components/policy.json"] = pack_dir / "components" / "policy.json"
    files["components/world_model.json"] = pack_dir / "components" / "world_model.json"
    files["receipt.json"] = pack_dir / "receipt.json"
    files["promotion_certificate.json"] = pack_dir / "promotion_certificate.json"
    files["provenance.json"] = pack_dir / "provenance.json"

    (pack_dir / "components").mkdir(parents=True, exist_ok=True)

    eval_bundle_hash = ""
    if include_eval_bundle:
        if not cdel_export_tool_cmd:
            raise ValueError("cdel_export_tool_cmd is required to include eval bundle")
        export_ledger_dir = cdel_ledger_dir or ledger_dir
        eval_bundle_name = f"eval_bundle_{receipt_raw_hash}.tar.gz"
        eval_bundle_path = pack_dir / eval_bundle_name
        cmd = shlex.split(cdel_export_tool_cmd) + [
            "--ledger-dir",
            str(export_ledger_dir),
            "--receipt-hash",
            receipt_raw_hash,
            "--out",
            str(eval_bundle_path),
        ]
        subprocess.run(cmd, check=True)
        eval_bundle_hash = _sha256_bytes(eval_bundle_path.read_bytes())
        eval_bundle_sha_path = pack_dir / "eval_bundle.sha256"
        eval_bundle_sha_path.write_text(
            f"{eval_bundle_hash}  {eval_bundle_name}\n",
            encoding="utf-8",
        )
        files[eval_bundle_name] = eval_bundle_path
        files["eval_bundle.sha256"] = eval_bundle_sha_path

    _write_file(files["system_capsule.json"], system_capsule)
    _write_file(files["components/policy.json"], _load_json(policy_path))
    _write_file(files["components/world_model.json"], _load_json(world_model_path))
    _write_file(files["receipt.json"], receipt)
    _write_file(files["promotion_certificate.json"], _load_json(cert_path))

    provenance = {
        "system": system_capsule.get("provenance", {}),
        "components": {
            "policy": _load_json(policy_path).get("provenance", {}),
            "world_model": _load_json(world_model_path).get("provenance", {}),
        },
    }
    _write_file(files["provenance.json"], provenance)

    manifest = _build_manifest(files, capsule_hash_value, receipt_raw_hash, cert_hash, eval_bundle_hash or None)
    manifest_path = pack_dir / "release_pack_manifest.json"
    _write_file(manifest_path, manifest)
    files["release_pack_manifest.json"] = manifest_path

    tar_path = out_dir / f"release_pack_{capsule_hash_value}.tar.gz"
    _write_tarball(pack_dir, tar_path)
    sha_path = out_dir / f"release_pack_{capsule_hash_value}.sha256"
    sha_path.write_text(f"{_sha256_bytes(tar_path.read_bytes())}  {tar_path.name}\n", encoding="utf-8")

    return tar_path, sha_path, manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a release pack for a promoted SYSTEM capsule.")
    parser.add_argument("--capsule-hash", required=True)
    parser.add_argument("--component-store-dir", required=True)
    parser.add_argument("--receipts-dir", required=True)
    parser.add_argument("--ledger-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--include-eval-bundle", action="store_true")
    parser.add_argument("--cdel-ledger-dir", default="")
    parser.add_argument("--cdel-export-tool-cmd", default="")
    args = parser.parse_args()

    cdel_ledger_dir = Path(args.cdel_ledger_dir) if args.cdel_ledger_dir else None
    cdel_export_cmd = args.cdel_export_tool_cmd or None

    tar_path, sha_path, manifest_path = build_release_pack(
        capsule_hash_value=args.capsule_hash,
        component_store_dir=Path(args.component_store_dir),
        receipts_dir=Path(args.receipts_dir),
        ledger_dir=Path(args.ledger_dir),
        out_dir=Path(args.out_dir),
        include_eval_bundle=bool(args.include_eval_bundle),
        cdel_ledger_dir=cdel_ledger_dir,
        cdel_export_tool_cmd=cdel_export_cmd,
    )
    print(str(tar_path))
    print(str(sha_path))
    print(str(manifest_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
