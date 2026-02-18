"""Omega native module producer campaign (v0.1).

Phase 1: build one Rust cdylib implementing exactly one op_id under a fixed ABI.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

from ..v1_7r.canon import write_canon_json
from .omega_common_v1 import (
    canon_hash_obj,
    fail,
    hash_file,
    load_canon_dict,
    repo_root,
    validate_schema,
    write_hashed_json,
)


_CAMPAIGN_ID = "rsi_omega_native_module_v0_1"
_PACK_SCHEMA = "rsi_omega_native_module_pack_v0_1"


def _load_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != _PACK_SCHEMA:
        fail("SCHEMA_FAIL")
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        fail("SCHEMA_FAIL")
    return raw


def _toolchain_manifest_hash(path: Path) -> str:
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    return hash_file(path)


def _platform_ext() -> str:
    return ".dylib" if os.uname().sysname.lower() == "darwin" else ".so"


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    pack = _load_pack(campaign_pack)
    root = repo_root().resolve()

    optimizer_rel = str(pack.get("optimizer_config_rel", "")).strip()
    toolchain_rel = str(pack.get("toolchain_manifest_rel", "")).strip()
    if not optimizer_rel or not toolchain_rel:
        fail("SCHEMA_FAIL")
    optimizer_path = (root / optimizer_rel).resolve()
    toolchain_path = (root / toolchain_rel).resolve()
    optimizer = _load_json(optimizer_path)
    toolchain_hash = _toolchain_manifest_hash(toolchain_path)

    state_root = out_dir.resolve() / "daemon" / _CAMPAIGN_ID / "state"
    hotspot_dir = state_root / "native" / "hotspot"
    src_dir = state_root / "native" / "src"
    vendor_dir = state_root / "native" / "vendor"
    build_dir = state_root / "native" / "build"
    health_dir = state_root / "native" / "health"
    bench_dir = state_root / "native" / "bench"
    blobs_dir = state_root / "native" / "blobs"
    promotion_dir = state_root / "promotion"
    for p in [hotspot_dir, src_dir, vendor_dir, build_dir, health_dir, bench_dir, blobs_dir, promotion_dir]:
        p.mkdir(parents=True, exist_ok=True)

    pinned_workload = optimizer.get("pinned_workload")
    if not isinstance(pinned_workload, dict):
        fail("SCHEMA_FAIL")
    candidate_ops = optimizer.get("candidate_ops")
    if not isinstance(candidate_ops, list) or not candidate_ops:
        fail("SCHEMA_FAIL")
    candidate_ops = [str(x) for x in candidate_ops if str(x).strip()]
    if not candidate_ops:
        fail("SCHEMA_FAIL")

    from tools.omega.native.native_profiler_v1 import profile_pinned_workload

    hotspot_report = profile_pinned_workload(
        repo_root=root,
        pinned_workload=pinned_workload,
        candidate_ops=candidate_ops,
    )
    validate_schema(hotspot_report, "omega_native_hotspot_report_v1")
    _, hotspot_obj, hotspot_hash = write_hashed_json(
        hotspot_dir,
        "omega_native_hotspot_report_v1.json",
        hotspot_report,
        id_field="report_id",
    )

    override = str(optimizer.get("selected_op", "")).strip()
    op_id = override or str(hotspot_obj.get("selected_op_id") or "").strip()
    if not op_id:
        fail("SCHEMA_FAIL")

    # Step 3: codegen.
    work_crate_dir = state_root / "native" / "work" / "crate"
    if work_crate_dir.exists():
        shutil.rmtree(work_crate_dir)
    work_crate_dir.mkdir(parents=True, exist_ok=True)

    from tools.omega.native.rust_codegen_v1 import generate_cdylib
    from tools.omega.native.rust_vendor_v1 import tree_hash as vendor_tree_hash, vendor_crate
    from tools.omega.native.rust_build_repro_v1 import build_reproducible_cdylib, load_rust_toolchain_manifest

    codegen_meta = generate_cdylib(op_id=op_id, out_dir=work_crate_dir)
    crate_name = str(codegen_meta.get("crate_name", "")).strip()
    if not crate_name:
        fail("SCHEMA_FAIL")

    # Load pinned toolchain early so cargo vendor/build both use the manifest.
    toolchain = load_rust_toolchain_manifest(toolchain_path)

    # Source manifest is a content-addressed summary; sources live under native/work/crate/.
    # The verifier will rebuild from this exact directory.
    source_files: list[dict[str, Any]] = []
    for path in sorted(work_crate_dir.rglob("*"), key=lambda p: p.as_posix()):
        if path.is_dir() or path.name.startswith("."):
            continue
        rel = path.relative_to(work_crate_dir).as_posix()
        raw = path.read_bytes()
        source_files.append({"path_rel": rel, "sha256": hash_file(path), "bytes_u64": int(len(raw))})
    source_payload = {
        "schema_version": "omega_native_source_manifest_v1",
        "manifest_id": "sha256:" + ("0" * 64),
        "op_id": op_id,
        "crate_tree_hash": vendor_tree_hash(work_crate_dir),
        "files": source_files,
    }
    validate_schema(source_payload, "omega_native_source_manifest_v1")
    _, source_obj, source_hash = write_hashed_json(
        src_dir,
        "omega_native_source_manifest_v1.json",
        source_payload,
        id_field="manifest_id",
    )

    # Step 4: vendor deps (offline).
    vendor_manifest = vendor_crate(crate_dir=work_crate_dir, cargo_exe=Path(str(toolchain.get("cargo_executable"))))
    validate_schema(vendor_manifest, "omega_native_vendor_manifest_v1")
    _, vendor_obj, vendor_hash = write_hashed_json(
        vendor_dir,
        "omega_native_vendor_manifest_v1.json",
        vendor_manifest,
        id_field="manifest_id",
    )

    # Step 5: reproducible build.
    built_path, build_receipt = build_reproducible_cdylib(
        crate_dir=work_crate_dir,
        crate_name=crate_name,
        toolchain_manifest=toolchain,
    )
    build_receipt["op_id"] = op_id
    build_receipt["toolchain_manifest_hash"] = toolchain_hash
    validate_schema(build_receipt, "omega_native_build_receipt_v1")
    _, build_obj, build_hash = write_hashed_json(
        build_dir,
        "omega_native_build_receipt_v1.json",
        build_receipt,
        id_field="receipt_id",
    )

    # Copy binary into content-addressed blob dir.
    binary_sha = hash_file(built_path)
    hex64 = binary_sha.split(":", 1)[1]
    out_blob = blobs_dir / f"sha256_{hex64}{_platform_ext()}"
    out_blob.write_bytes(built_path.read_bytes())
    if hash_file(out_blob) != binary_sha:
        fail("NONDETERMINISTIC")

    # Step 6: deterministic healthcheck using tracked vectors.
    from orchestrator.native.native_router_v1 import healthcheck_vectors

    health = healthcheck_vectors(op_id, out_blob)
    validate_schema(health, "omega_native_healthcheck_receipt_v1")
    _, health_obj, health_hash = write_hashed_json(
        health_dir,
        "omega_native_healthcheck_receipt_v1.json",
        health,
        id_field="receipt_id",
    )
    if str(health_obj.get("result", "")) != "PASS":
        fail("VERIFY_ERROR")

    # Step 7: informational benchmark (not verifier-gated).
    try:
        from tools.omega.native.native_benchmark_v1 import benchmark_pinned_workload

        bench_payload = benchmark_pinned_workload(
            repo_root=root,
            op_id=op_id,
            binary_path=out_blob,
            pinned_workload=pinned_workload,
        )
    except Exception:
        bench_payload = {
            "schema_version": "omega_native_benchmark_report_v1",
            "report_id": "sha256:" + ("0" * 64),
            "op_id": op_id,
            "binary_sha256": binary_sha,
            "notes": "informational benchmark unavailable",
        }
    validate_schema(bench_payload, "omega_native_benchmark_report_v1")
    _, bench_obj, bench_hash = write_hashed_json(
        bench_dir,
        "omega_native_benchmark_report_v1.json",
        bench_payload,
        id_field="report_id",
    )

    # Step 8: promotion bundle (avoid path-like keys entirely).
    platform = str(build_obj.get("platform", "")).strip() or "unknown"
    native_module = {
        "op_id": op_id,
        "abi_version_u32": 1,
        "abi_kind": "BLOBLIST_V1",
        "language": "RUST",
        "platform": platform,
        "binary_sha256": binary_sha,
        "source_manifest_hash": source_hash,
        "vendor_manifest_hash": vendor_hash,
        "build_receipt_hash": build_hash,
        "hotspot_report_hash": hotspot_hash,
        "toolchain_manifest_hash": toolchain_hash,
        "healthcheck_receipt_hash": health_hash,
        "bench_report_hash": bench_hash,
    }
    bundle_payload = {
        "schema_version": "omega_native_module_promotion_bundle_v1",
        "bundle_id": "sha256:" + ("0" * 64),
        "campaign_id": _CAMPAIGN_ID,
        "native_module": native_module,
    }
    validate_schema(bundle_payload, "omega_native_module_promotion_bundle_v1")
    _, bundle_obj, _ = write_hashed_json(
        promotion_dir,
        "omega_native_module_promotion_bundle_v1.json",
        bundle_payload,
        id_field="bundle_id",
    )
    write_canon_json(promotion_dir / "omega_native_module_promotion_bundle_v1.json", bundle_obj)
    print("OK")


def main() -> None:
    ap = argparse.ArgumentParser(prog="campaign_omega_native_module_v0_1")
    ap.add_argument("--campaign_pack", required=True)
    ap.add_argument("--out_dir", required=True)
    args = ap.parse_args()
    run(campaign_pack=Path(args.campaign_pack).resolve(), out_dir=Path(args.out_dir).resolve())


if __name__ == "__main__":
    main()
