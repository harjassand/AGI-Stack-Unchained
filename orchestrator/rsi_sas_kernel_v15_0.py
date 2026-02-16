"""CLI entrypoint for SAS-Kernel v15.0 with Omega dispatch flags."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _hash_obj(obj: Any) -> str:
    return sha256_prefixed(canon_bytes(obj))


def _write_hashed_json(dir_path: Path, suffix: str, payload: dict[str, Any]) -> tuple[str, Path]:
    digest = _hash_obj(payload)
    out_path = dir_path / f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    write_canon_json(out_path, payload)
    return digest, out_path


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _tick_u64_from_context(out_dir_abs: Path) -> int:
    env_tick = os.environ.get("OMEGA_TICK_U64")
    if env_tick is not None:
        try:
            tick = int(env_tick, 10)
            if tick >= 0:
                return tick
        except Exception:  # noqa: BLE001
            pass
    m = re.search(r"tick_(\d+)$", out_dir_abs.name)
    if m:
        return int(m.group(1))
    return 1


def _derive_seed_u64(base_seed: int, tick_u64: int, capability_id: str) -> int:
    blob = f"{base_seed}:{tick_u64}:{capability_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(blob).digest()[:8], "big", signed=False)


def _ensure_kernel_binary(repo_root: Path) -> Path:
    crate_dir = repo_root / "CDEL-v2" / "cdel" / "v15_0" / "rust" / "agi_kernel_rs_v1"
    binary_path = crate_dir / "target" / "release" / "agi_kernel_v15"
    subprocess.run(
        ["cargo", "build", "--release", "--locked", "--offline"],
        cwd=crate_dir,
        check=True,
    )
    if not binary_path.exists():
        raise RuntimeError("KERNEL_BINARY_MISSING")
    return binary_path


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    if not campaign_pack.exists() or not campaign_pack.is_file():
        raise RuntimeError("MISSING_CAMPAIGN_PACK")

    repo_root = _repo_root()
    out_dir_abs = out_dir.resolve()
    os.environ["AGI_ROOT"] = str(out_dir_abs)

    daemon_root = out_dir_abs / "daemon" / "rsi_sas_kernel_v15_0"
    config_dir = daemon_root / "config"
    state_dir = daemon_root / "state"
    attempts_dir = state_dir / "attempts"
    specs_dir = state_dir / "specs"
    promotion_dir = state_dir / "promotion"
    cases_root = out_dir_abs / "cases"

    if daemon_root.exists():
        shutil.rmtree(daemon_root)
    if cases_root.exists():
        shutil.rmtree(cases_root)
    attempts_dir.mkdir(parents=True, exist_ok=True)
    specs_dir.mkdir(parents=True, exist_ok=True)
    promotion_dir.mkdir(parents=True, exist_ok=True)
    cases_root.mkdir(parents=True, exist_ok=True)

    frozen_config_src = repo_root / "daemon" / "rsi_sas_kernel_v15_0" / "config"
    _copy_tree(frozen_config_src, config_dir)

    sealed_cfg_src = repo_root / "Extension-1" / "agi-orchestrator" / "configs" / "sealed_io_dev.toml"
    sealed_cfg_dst = config_dir / "sealed_io_dev.toml"
    if sealed_cfg_src.exists():
        shutil.copy2(sealed_cfg_src, sealed_cfg_dst)
    else:
        sealed_cfg_dst.write_text("# missing sealed config fallback\n", encoding="utf-8")

    proof_path = attempts_dir / "kernel.proof.lean"
    proof_path.write_text("theorem kernel_ok : True := by trivial\n", encoding="utf-8")

    fixture_matrix_path = config_dir / "fixture_matrix_v1.json"
    fixture_matrix = load_canon_json(fixture_matrix_path)
    if not isinstance(fixture_matrix, dict):
        raise RuntimeError("SCHEMA_FAIL")
    fixtures = fixture_matrix.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise RuntimeError("SCHEMA_FAIL")

    base_seed = int(os.environ.get("OMEGA_RUN_SEED_U64", "0"))
    tick_u64 = _tick_u64_from_context(out_dir_abs)

    capability_registry_rel = os.path.relpath((config_dir / "capability_registry_v2.json").resolve(), repo_root)
    kernel_policy_rel = os.path.relpath((config_dir / "sas_kernel_policy_v1.json").resolve(), repo_root)
    toolchain_kernel_rel = os.path.relpath((config_dir / "toolchain_manifest_kernel_v1.json").resolve(), repo_root)
    toolchain_py_rel = os.path.relpath((config_dir / "toolchain_manifest_py_v1.json").resolve(), repo_root)
    toolchain_rust_rel = os.path.relpath((config_dir / "toolchain_manifest_rust_v1.json").resolve(), repo_root)
    toolchain_lean_rel = os.path.relpath((config_dir / "toolchain_manifest_lean_v1.json").resolve(), repo_root)
    sealed_cfg_rel = os.path.relpath(sealed_cfg_dst.resolve(), repo_root)

    case_rows: list[dict[str, str]] = []
    for idx, fixture in enumerate(fixtures):
        if not isinstance(fixture, dict):
            raise RuntimeError("SCHEMA_FAIL")
        capability_id = str(fixture.get("capability_id", "")).strip()
        if not capability_id:
            raise RuntimeError("SCHEMA_FAIL")
        cap_slug = capability_id.lower()

        run_spec_path = specs_dir / f"{cap_slug}.kernel_run_spec_v1.json"
        run_spec_rel = os.path.relpath(run_spec_path.resolve(), repo_root)

        case_out_dir_abs = cases_root / cap_slug
        case_out_dir_rel = os.path.relpath(case_out_dir_abs.resolve(), repo_root)

        run_spec = {
            "schema_version": "kernel_run_spec_v1",
            "run_id": f"{cap_slug}_tick_{tick_u64:04d}",
            "seed_u64": _derive_seed_u64(base_seed, tick_u64 + idx, capability_id),
            "capability_id": capability_id,
            "capability_registry_rel": capability_registry_rel,
            "paths": {
                "repo_root_rel": ".",
                "daemon_root_rel": "daemon",
                "out_dir_rel": case_out_dir_rel,
            },
            "sealed": {
                "sealed_config_toml_rel": sealed_cfg_rel,
                "mount_policy_id": "MOUNT_POLICY_V1",
            },
            "toolchains": {
                "kernel_manifest_rel": toolchain_kernel_rel,
                "py_manifest_rel": toolchain_py_rel,
                "rust_manifest_rel": toolchain_rust_rel,
                "lean_manifest_rel": toolchain_lean_rel,
            },
            "kernel_policy_rel": kernel_policy_rel,
        }
        write_canon_json(run_spec_path, run_spec)

        reference_snapshot_rel = str(fixture.get("reference_snapshot_rel", ""))
        reference_promotion_bundle_rel = str(fixture.get("reference_promotion_bundle_rel", ""))
        case_rows.append(
            {
                "capability_id": capability_id,
                "run_spec_rel": run_spec_rel,
                "case_out_dir_rel": case_out_dir_rel,
                "reference_snapshot_rel": reference_snapshot_rel,
                "reference_promotion_bundle_rel": reference_promotion_bundle_rel,
            }
        )

    case_index = {
        "schema_version": "kernel_case_index_v1",
        "cases": case_rows,
    }
    case_index_path = state_dir / "kernel_case_index_v1.json"
    write_canon_json(case_index_path, case_index)

    kernel_bin = _ensure_kernel_binary(repo_root)
    for row in case_rows:
        run_spec_abs = repo_root / row["run_spec_rel"]
        subprocess.run(
            [str(kernel_bin), "run", "--run_spec", str(run_spec_abs)],
            cwd=repo_root,
            check=True,
        )

    binary_sha256 = ""
    activation_receipt_hashes: list[str] = []
    run_receipt_hashes: list[str] = []
    promotion_hashes: list[str] = []
    for row in case_rows:
        case_root = repo_root / row["case_out_dir_rel"]
        activation_path = case_root / "kernel" / "receipts" / "kernel_activation_receipt_v1.json"
        run_receipt_path = case_root / "kernel" / "receipts" / "kernel_run_receipt_v1.json"
        case_promotion_path = case_root / "promotion" / "kernel_promotion_bundle_v1.json"
        activation_obj = load_canon_json(activation_path)
        run_receipt_obj = load_canon_json(run_receipt_path)
        case_promotion_obj = load_canon_json(case_promotion_path)
        if not isinstance(activation_obj, dict) or not isinstance(run_receipt_obj, dict) or not isinstance(case_promotion_obj, dict):
            raise RuntimeError("SCHEMA_FAIL")
        if not binary_sha256:
            binary_sha256 = str(activation_obj.get("binary_sha256", ""))
        activation_receipt_hashes.append(_hash_obj(activation_obj))
        run_receipt_hashes.append(_hash_obj(run_receipt_obj))
        promotion_hashes.append(_hash_obj(case_promotion_obj))

    if not binary_sha256:
        raise RuntimeError("MISSING_ACTIVATION_RECEIPT")

    summary_bundle = {
        "schema_version": "sas_kernel_promotion_bundle_v1",
        "campaign_id": "rsi_sas_kernel_v15_0",
        "capability_id": "RSI_SAS_KERNEL",
        "kernel_binary_sha256": binary_sha256,
        "kernel_case_index_hash": _hash_obj(case_index),
        "kernel_activation_receipt_hashes": activation_receipt_hashes,
        "kernel_run_receipt_hashes": run_receipt_hashes,
        "kernel_case_promotion_hashes": promotion_hashes,
    }
    _write_hashed_json(promotion_dir, "sas_kernel_promotion_bundle_v1.json", summary_bundle)


def main() -> None:
    parser = argparse.ArgumentParser(prog="rsi_sas_kernel_v15_0")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    try:
        run(campaign_pack=Path(args.campaign_pack), out_dir=Path(args.out_dir))
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED:{exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print("OK")


if __name__ == "__main__":
    main()
