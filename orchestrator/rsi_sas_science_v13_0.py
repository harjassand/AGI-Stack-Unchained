"""CLI entrypoint for SAS-Science v13.0 with Omega payload-pack support."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict, repo_root, require_relpath, validate_schema
from cdel.v1_7r.canon import write_canon_json

from .sas_science_v13_0.controller_v1 import run_sas_science


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _file_hash(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise RuntimeError("MISSING_STATE_INPUT")
    return _sha256_prefixed(path.read_bytes())


def _resolve_repo_rel(value: object) -> Path:
    rel = require_relpath(value)
    return repo_root() / rel


def _legacy_mode(args: argparse.Namespace) -> bool:
    return bool(args.dataset_csv and args.dataset_manifest and args.state_dir)


def _parse_v13_max_theories() -> int | None:
    raw = str(os.environ.get("V13_MAX_THEORIES", "")).strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("INVALID:V13_MAX_THEORIES") from exc
    if parsed < 1 or parsed > 100000:
        raise RuntimeError("INVALID:V13_MAX_THEORIES")
    return parsed


def _write_intensity_receipt(control_dir: Path, max_theories: int | None) -> None:
    if max_theories is None:
        return
    control_dir.mkdir(parents=True, exist_ok=True)
    write_canon_json(
        control_dir / "omega_intensity_receipt_v1.json",
        {
            "schema_version": "omega_intensity_receipt_v1",
            "campaign_id": "rsi_sas_science_v13_0",
            "env": {"V13_MAX_THEORIES": str(max_theories)},
            "applied": {"max_theories": int(max_theories)},
        },
    )


def _run_legacy(args: argparse.Namespace) -> int:
    max_theories = _parse_v13_max_theories()
    result = run_sas_science(
        dataset_csv=Path(args.dataset_csv),
        dataset_manifest=Path(args.dataset_manifest),
        campaign_pack=Path(args.campaign_pack),
        state_dir=Path(args.state_dir),
        campaign_tag="rsi_sas_science_v13_0",
        max_theories=max_theories,
    )
    _write_intensity_receipt(Path(args.state_dir) / "state" / "control", max_theories)
    print(result.get("status", "OK"))
    for key, value in result.items():
        if key == "status":
            continue
        print(f"{key}: {value}")
    return 0


def _validate_pack_and_paths(pack_path: Path) -> tuple[dict[str, object], Path, Path, Path]:
    pack = load_canon_dict(pack_path)
    validate_schema(pack, "rsi_sas_science_omega_pack_v1")
    if pack.get("schema_version") != "rsi_sas_science_omega_pack_v1":
        raise RuntimeError("SCHEMA_FAIL")

    base_pack_path = _resolve_repo_rel(pack.get("base_campaign_pack_rel"))
    dataset_csv_path = _resolve_repo_rel(pack.get("dataset_csv_rel"))
    dataset_manifest_path = _resolve_repo_rel(pack.get("dataset_manifest_rel"))

    base_pack_obj = load_canon_dict(base_pack_path)
    expected_base_hash = str(pack.get("base_campaign_pack_hash", ""))
    got_base_hash = canon_hash_obj(base_pack_obj)
    if got_base_hash != expected_base_hash:
        raise RuntimeError("BASE_PACK_HASH_MISMATCH")

    expected_csv_hash = str(pack.get("dataset_csv_hash", ""))
    got_csv_hash = _file_hash(dataset_csv_path)
    if got_csv_hash != expected_csv_hash:
        raise RuntimeError("DATASET_CSV_HASH_MISMATCH")

    expected_manifest_hash = str(pack.get("dataset_manifest_hash", ""))
    got_manifest_hash = _file_hash(dataset_manifest_path)
    if got_manifest_hash != expected_manifest_hash:
        raise RuntimeError("DATASET_MANIFEST_HASH_MISMATCH")

    return pack, base_pack_path, dataset_csv_path, dataset_manifest_path


def _write_control_flags(control_dir: Path) -> None:
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "ENABLE_RESEARCH").write_text("enable\n", encoding="utf-8")
    (control_dir / "ENABLE_SAS_SCIENCE").write_text("enable\n", encoding="utf-8")
    write_canon_json(
        control_dir / "SAS_SCIENCE_LEASE.json",
        {
            "schema_version": "sas_science_lease_v1",
            "lease_id": "omega_v18_science_fixture",
            "grants": ["HELDOUT_EVAL"],
        },
    )


def _run_omega(args: argparse.Namespace) -> int:
    if not args.out_dir:
        raise RuntimeError("MISSING_OUT_DIR")

    out_dir_abs = Path(args.out_dir).resolve()
    os.environ["AGI_ROOT"] = str(out_dir_abs)

    daemon_root = out_dir_abs / "daemon" / "rsi_sas_science_v13_0"
    config_dir = daemon_root / "config"
    state_dir = daemon_root / "state"
    control_dir = state_dir / "control"
    config_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    _write_control_flags(control_dir)
    max_theories = _parse_v13_max_theories()

    _, base_pack_path, dataset_csv_path, dataset_manifest_path = _validate_pack_and_paths(Path(args.campaign_pack).resolve())

    run_sas_science(
        dataset_csv=dataset_csv_path,
        dataset_manifest=dataset_manifest_path,
        campaign_pack=base_pack_path,
        state_dir=daemon_root,
        campaign_tag="rsi_sas_science_v13_0",
        max_theories=max_theories,
    )
    _write_intensity_receipt(control_dir, max_theories)
    print("OK")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="rsi_sas_science_v13_0")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=False)
    parser.add_argument("--dataset_csv", required=False)
    parser.add_argument("--dataset_manifest", required=False)
    parser.add_argument("--state_dir", required=False)
    args = parser.parse_args()

    try:
        if _legacy_mode(args):
            raise SystemExit(_run_legacy(args))
        raise SystemExit(_run_omega(args))
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED:{exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
