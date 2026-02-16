from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from cdel.v18_0.omega_promoter_v1 import _build_meta_core_activation_bundle

from .utils import repo_root


ENGINE_DIR = (repo_root() / "meta-core" / "engine").resolve()
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from activation import stage_bundle  # noqa: E402


def _symlink_or_copy(src: Path, dest: Path) -> None:
    try:
        os.symlink(src, dest)
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def _setup_temp_meta_core(tmp_path: Path) -> Path:
    real_root = (repo_root() / "meta-core").resolve()
    meta_root = tmp_path / "meta-core"
    (meta_root / "active" / "ledger").mkdir(parents=True, exist_ok=True)
    (meta_root / "store" / "bundles").mkdir(parents=True, exist_ok=True)
    (meta_root / "kernel").mkdir(parents=True, exist_ok=True)
    (meta_root / "meta_constitution").mkdir(parents=True, exist_ok=True)
    (meta_root / "scripts").mkdir(parents=True, exist_ok=True)

    _symlink_or_copy(real_root / "kernel" / "verifier", meta_root / "kernel" / "verifier")
    _symlink_or_copy(real_root / "meta_constitution" / "v1", meta_root / "meta_constitution" / "v1")
    _symlink_or_copy(real_root / "scripts" / "build.sh", meta_root / "scripts" / "build.sh")
    _symlink_or_copy(real_root / "engine", meta_root / "engine")

    parent_bundle_dir = real_root / "kernel" / "verifier" / "tests" / "fixtures" / "parent_bundle"
    parent_manifest = json.loads((parent_bundle_dir / "constitution.manifest.json").read_text(encoding="utf-8"))
    parent_hash = str(parent_manifest["bundle_hash"])
    shutil.copytree(parent_bundle_dir, meta_root / "store" / "bundles" / parent_hash)
    (meta_root / "active" / "ACTIVE_BUNDLE").write_text(parent_hash + "\n", encoding="utf-8")
    return meta_root


def test_activation_bundle_hashes_accept_by_meta_core_stage(tmp_path, monkeypatch) -> None:
    meta_root = _setup_temp_meta_core(tmp_path)
    monkeypatch.setenv("OMEGA_META_CORE_ROOT", str(meta_root))

    binding_payload = {
        "schema_version": "omega_activation_binding_v1",
        "binding_id": "sha256:" + ("a" * 64),
        "tick_u64": 1,
        "campaign_id": "rsi_sas_code_v12_0",
        "capability_id": "RSI_SAS_CODE",
        "promotion_bundle_hash": "sha256:" + ("b" * 64),
        "activation_key": "algo_v1",
        "source_run_root_rel": "rsi_omega_test_v18_0",
        "subverifier_receipt_hash": "sha256:" + ("c" * 64),
        "meta_core_promo_verify_receipt_hash": "sha256:" + ("d" * 64),
    }

    activation_bundle_dir, _ = _build_meta_core_activation_bundle(
        out_dir=tmp_path / "out",
        binding_payload=binding_payload,
        binding_hash_hex8="deadbeef",
    )

    work_dir = (tmp_path / "work").resolve()
    code, out = stage_bundle(
        str(meta_root.resolve()),
        str(activation_bundle_dir.resolve()),
        str(work_dir),
    )

    assert code == 0
    assert str(out.get("verdict")) == "STAGED"

