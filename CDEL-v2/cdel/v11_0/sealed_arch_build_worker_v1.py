"""Sealed architecture build worker (v11.0)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from .architecture_builder_v1 import build_manifest, compute_arch_id, enforce_allowlist
from .topology_fingerprint_v1 import compute_fingerprint


def _hash_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _relpath(path: Path, state_dir: Path) -> str:
    return path.resolve().relative_to(state_dir.resolve()).as_posix()


def main() -> None:
    parser = argparse.ArgumentParser(prog="sealed_arch_build_worker_v1")
    parser.add_argument("--arch-ir", required=True)
    parser.add_argument("--allowlist", required=True)
    parser.add_argument("--family-registry", required=True)
    parser.add_argument("--opset-manifest", required=True)
    parser.add_argument("--toolchain", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--out-manifest", required=True)
    parser.add_argument("--out-fingerprint", required=True)
    parser.add_argument("--out-receipt", required=True)
    args = parser.parse_args()

    start = time.monotonic()
    state_dir = Path(args.state_dir)

    arch_ir = load_canon_json(Path(args.arch_ir))
    allowlist = load_canon_json(Path(args.allowlist))
    registry = load_canon_json(Path(args.family_registry))
    opset = load_canon_json(Path(args.opset_manifest))
    toolchain = load_canon_json(Path(args.toolchain))

    if not isinstance(allowlist, dict) or allowlist.get("schema_version") != "arch_allowlist_v1":
        raise SystemExit("invalid allowlist")
    if not isinstance(registry, dict) or registry.get("schema_version") != "sas_family_registry_v1":
        raise SystemExit("invalid registry")
    if not isinstance(opset, dict) or opset.get("schema_version") != "sas_opset_manifest_v1":
        raise SystemExit("invalid opset")
    if not isinstance(toolchain, dict) or toolchain.get("schema_version") != "arch_synthesis_toolchain_manifest_v1":
        raise SystemExit("invalid toolchain")

    # Enforce allowlist + registry
    enforce_allowlist(arch_ir, allowlist)

    arch_family = arch_ir.get("arch_family")
    registry_entry = None
    for entry in registry.get("families", []) or []:
        if isinstance(entry, dict) and entry.get("family_name") == arch_family:
            registry_entry = entry
            break
    if registry_entry is None:
        raise SystemExit("family not in registry")

    builder_version = str(registry_entry.get("builder_version", ""))
    if not builder_version:
        raise SystemExit("builder_version missing")

    if str(registry_entry.get("opset_hash")) != sha256_prefixed(canon_bytes(opset)):
        raise SystemExit("opset hash mismatch")

    toolchain_hash = sha256_prefixed(canon_bytes(toolchain))
    allowlist_hash = sha256_prefixed(canon_bytes(allowlist))
    registry_hash = sha256_prefixed(canon_bytes(registry))
    opset_hash = sha256_prefixed(canon_bytes(opset))

    manifest = build_manifest(arch_ir=arch_ir, builder_version=builder_version, toolchain_hash=toolchain_hash)
    fingerprint = compute_fingerprint(manifest)

    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    fingerprint_hash = sha256_prefixed(canon_bytes(fingerprint))

    out_manifest = Path(args.out_manifest)
    out_fingerprint = Path(args.out_fingerprint)
    out_receipt = Path(args.out_receipt)

    write_canon_json(out_manifest, manifest)
    write_canon_json(out_fingerprint, fingerprint)

    elapsed_ms = max(1, int((time.monotonic() - start) * 1000))

    # Emit minimal trace for stdout/stderr hashing.
    print(f"sealed_build_ok:{manifest.get('arch_id')}")
    print("sealed_build_trace:build_receipt", file=sys.stderr)

    receipt = {
        "schema_version": "sas_arch_build_receipt_v1",
        "arch_id": manifest.get("arch_id"),
        "arch_graph_hash": manifest.get("arch_graph_hash"),
        "init_weights_hash": manifest.get("init_weights_hash"),
        "arch_manifest_hash": manifest_hash,
        "fingerprint_hash": fingerprint_hash,
        "toolchain_hash": toolchain_hash,
        "allowlist_hash": allowlist_hash,
        "family_registry_hash": registry_hash,
        "opset_hash": opset_hash,
        "builder_version": builder_version,
        "arch_ir_path": _relpath(Path(args.arch_ir), state_dir),
        "arch_manifest_path": _relpath(out_manifest, state_dir),
        "fingerprint_path": _relpath(out_fingerprint, state_dir),
        "network_used": False,
        "time_ms": elapsed_ms,
    }
    write_canon_json(out_receipt, receipt)


if __name__ == "__main__":
    main()
