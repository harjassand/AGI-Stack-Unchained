#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT.parent))

from genesis.core.codesign import run_codesign  # noqa: E402
from genesis.promotion.server_manager import start_server, stop_server  # noqa: E402
from genesis.tools.release_pack import build_release_pack  # noqa: E402
from genesis.tools.release_registry import append_entry  # noqa: E402
from genesis.tools.verify_release_pack import verify_release_pack  # noqa: E402
from genesis.tools.path_utils import normalize_config_paths, resolve_path  # noqa: E402


def _load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _clean_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _read_log(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _find_pass_capsule_hash(records: list[dict]) -> str:
    for record in records:
        if record.get("promotion_result") == "PASS":
            return str(record.get("system_hash", ""))
    return ""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_certificate(cert_path: Path) -> dict:
    return json.loads(cert_path.read_text(encoding="utf-8"))


def _write_config(config: dict, path: Path) -> None:
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _run_pipeline(
    *,
    config: dict,
    config_path: Path,
    cdel_root: Path,
    ledger_dir: Path,
    receipts_dir: Path,
    component_store_dir: Path,
    run_log_path: Path,
    release_pack_dir: Path,
    keystore_dir: Path,
    allowlist: str,
) -> tuple[Path, dict, dict]:
    _clean_path(run_log_path)
    handle = start_server(
        cdel_root=cdel_root,
        ledger_dir=ledger_dir,
        fixture_dir=cdel_root,
        epoch_id=str(config.get("epoch_id", "epoch-1")),
        component_store_dir=component_store_dir,
        env_overrides={
            "CDEL_PASS_CAPSULE_IDS": allowlist,
            "CDEL_ALPHA_TOTAL": "0.001",
            "CDEL_EPSILON_TOTAL": "2",
            "CDEL_DELTA_TOTAL": "0",
            "CDEL_CERT_KEYSTORE_DIR": str(keystore_dir),
        },
    )
    try:
        env = os.environ.copy()
        env["CDEL_URL"] = f"{handle.base_url}/evaluate"
        subprocess.run(
            ["python3", str(ROOT / "system_run.py"), "--config", str(config_path)],
            check=True,
            env=env,
        )
    finally:
        stop_server(handle)

    records = _read_log(run_log_path)
    if not records:
        raise SystemExit("run log was empty")
    system_hash = _find_pass_capsule_hash(records)
    if not system_hash:
        raise SystemExit("expected at least one PASS promotion")

    release_pack_dir.mkdir(parents=True, exist_ok=True)
    export_cmd = f"python3 {cdel_root / 'tools' / 'export_eval_bundle.py'} --keystore-dir {keystore_dir}"
    tar_path, _, manifest_path = build_release_pack(
        capsule_hash_value=system_hash,
        component_store_dir=component_store_dir,
        receipts_dir=receipts_dir,
        ledger_dir=ledger_dir,
        out_dir=release_pack_dir,
        include_eval_bundle=True,
        cdel_ledger_dir=ledger_dir,
        cdel_export_tool_cmd=export_cmd,
    )

    verify_cmd = f"python3 {cdel_root / 'tools' / 'verify_eval_bundle.py'}"
    verify_release_pack(tar_path, keystore_dir, cdel_verify_tool_cmd=verify_cmd)

    manifest = _read_manifest(manifest_path)
    cert_path = release_pack_dir / f"release_pack_{system_hash}" / "promotion_certificate.json"
    cert = _read_certificate(cert_path)

    entry = {
        "system_capsule_hash": system_hash,
        "release_pack_hash": _sha256(tar_path),
        "receipt_hash": manifest.get("receipt_hash", ""),
        "certificate_hash": manifest.get("certificate_hash", ""),
        "eval_bundle_hash": manifest.get("eval_bundle_hash", ""),
        "eval_bundle_verified": True,
        "cdel_key_id": cert.get("signature", {}).get("key_id", ""),
        "verification_status": "PASS",
        "revocation_status": "unknown",
    }
    append_entry(Path(config.get("release_registry_path")), entry)

    return tar_path, manifest, cert


def main() -> int:
    parser = argparse.ArgumentParser(description="Genesis end-to-end v1.2 run")
    parser.add_argument("--system-config", default=str(ROOT / "configs" / "system_v1_2.json"))
    args = parser.parse_args()

    cdel_root = os.getenv("CDEL_ROOT")
    if not cdel_root:
        raise SystemExit("CDEL_ROOT is required")

    os.environ["PYTHONPATH"] = str(Path(cdel_root))

    config = _load_config(resolve_path(args.system_config, ROOT))
    config = normalize_config_paths(
        config,
        ROOT,
        keys=[
            "dataset_config",
            "policy_env_config",
            "run_log_path",
            "receipts_dir",
            "shadow_calibration_path",
            "protocol_budget_path",
            "component_store_dir",
            "release_pack_dir",
            "release_registry_path",
        ],
    )

    ledger_dir = Path(".cdel_ledger_e2e_v1_2")
    if not ledger_dir.is_absolute():
        ledger_dir = (ROOT / ledger_dir).resolve()
    receipts_dir = Path(config.get("receipts_dir", str(ROOT / "receipts_v1_2")))
    component_store_dir = Path(config.get("component_store_dir", str(ROOT / "components_v1_2")))
    calibration_path = Path(config.get("shadow_calibration_path", str(ROOT / "shadow_calibration_v1_2.json")))
    run_log_path = Path(config.get("run_log_path", str(ROOT.parent / "genesis_run_v1_2.jsonl")))
    protocol_budget_path = Path(config.get("protocol_budget_path", str(receipts_dir / "protocol_budget.json")))
    release_pack_dir = Path(config.get("release_pack_dir", str(ROOT / "release_packs_v1_2")))
    registry_path = Path(config.get("release_registry_path", str(ROOT / "release_registry_v1_2.jsonl")))
    keystore_dir = (ROOT / "cdel_keystore_v1_2").resolve()

    for path in [
        ledger_dir,
        receipts_dir,
        component_store_dir,
        calibration_path,
        run_log_path,
        protocol_budget_path,
        release_pack_dir,
        registry_path,
    ]:
        _clean_path(path)

    if not keystore_dir.exists():
        gen_env = os.environ.copy()
        gen_env["PYTHONPATH"] = str(Path(cdel_root))
        subprocess.run(
            [
                "python3",
                str(Path(cdel_root) / "tools" / "gen_signing_key.py"),
                "--keystore-dir",
                str(keystore_dir),
            ],
            check=True,
            env=gen_env,
        )

    preflight = run_codesign(config)
    allowlist = ",".join([event.system_capsule["capsule_id"] for event in preflight["events"]])

    tmp_config = config.copy()
    tmp_config["receipts_dir"] = str(receipts_dir)
    tmp_config["component_store_dir"] = str(component_store_dir)
    tmp_config["run_log_path"] = str(run_log_path)
    tmp_config["release_pack_dir"] = str(release_pack_dir)
    tmp_config["release_registry_path"] = str(registry_path)
    tmp_config_path = (ROOT / "configs" / "system_v1_2_tmp.json").resolve()
    _write_config(tmp_config, tmp_config_path)

    _run_pipeline(
        config=tmp_config,
        config_path=tmp_config_path,
        cdel_root=Path(cdel_root),
        ledger_dir=ledger_dir,
        receipts_dir=receipts_dir,
        component_store_dir=component_store_dir,
        run_log_path=run_log_path,
        release_pack_dir=release_pack_dir,
        keystore_dir=keystore_dir,
        allowlist=allowlist,
    )

    tmp_config_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
