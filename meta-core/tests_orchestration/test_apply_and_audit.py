import json
import os
import shutil
import sys
import tempfile
import unittest

ENGINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "engine"))
sys.path.insert(0, ENGINE_DIR)

from audit import audit_active  # noqa: E402
from atomic_fs import atomic_write_text  # noqa: E402
from activation import (  # noqa: E402
    canary_staged,
    commit_staged,
    rollback_active,
    stage_bundle,
    verify_staged,
)
from store import store_bundle  # noqa: E402
from verifier_client import run_verify  # noqa: E402


def _real_meta_core_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _symlink_or_copy(src: str, dest: str) -> None:
    try:
        os.symlink(src, dest)
    except OSError:
        shutil.copytree(src, dest)


def _setup_temp_meta_core(tmp_root: str) -> str:
    meta_root = os.path.join(tmp_root, "meta-core")
    os.makedirs(meta_root, exist_ok=True)
    os.makedirs(os.path.join(meta_root, "active", "ledger"), exist_ok=True)
    os.makedirs(os.path.join(meta_root, "store", "bundles"), exist_ok=True)

    real_root = _real_meta_core_root()
    real_kernel = os.path.join(real_root, "kernel", "verifier")
    real_meta = os.path.join(real_root, "meta_constitution", "v1")

    os.makedirs(os.path.join(meta_root, "kernel"), exist_ok=True)
    os.makedirs(os.path.join(meta_root, "meta_constitution"), exist_ok=True)
    os.makedirs(os.path.join(meta_root, "scripts"), exist_ok=True)

    _symlink_or_copy(real_kernel, os.path.join(meta_root, "kernel", "verifier"))
    _symlink_or_copy(real_meta, os.path.join(meta_root, "meta_constitution", "v1"))
    _symlink_or_copy(
        os.path.join(real_root, "scripts", "build.sh"),
        os.path.join(meta_root, "scripts", "build.sh"),
    )
    return meta_root


def _fixture_path(name: str) -> str:
    return os.path.join(
        _real_meta_core_root(), "kernel", "verifier", "tests", "fixtures", name
    )


def _seed_parent_bundle(meta_root: str) -> str:
    parent_dir = _fixture_path("parent_bundle")
    receipt_path = os.path.join(meta_root, "active", "parent_receipt.json")
    exit_code, receipt_bytes = run_verify(meta_root, parent_dir, None, receipt_path)
    if exit_code != 0:
        raise RuntimeError("failed to verify parent bundle")
    manifest_path = os.path.join(parent_dir, "constitution.manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        parent_hash = json.load(f)["bundle_hash"]
    store_bundle(meta_root, parent_hash, parent_dir, receipt_bytes)
    active_path = os.path.join(meta_root, "active", "ACTIVE_BUNDLE")
    atomic_write_text(active_path, parent_hash + "\n")
    return parent_hash


class TestApplyAndAudit(unittest.TestCase):
    def test_apply_valid_then_audit_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_root = _setup_temp_meta_core(tmpdir)
            bundle_dir = _fixture_path("valid_bundle")
            parent_hash = _seed_parent_bundle(meta_root)

            work_dir = os.path.join(meta_root, "active", "work")
            stage_code, stage_out = stage_bundle(meta_root, bundle_dir, work_dir)
            self.assertEqual(stage_code, 0)
            stage_path = stage_out["stage_path"]

            receipt_path = os.path.join(work_dir, "receipt.json")
            verify_code, _ = verify_staged(meta_root, stage_path, receipt_path)
            self.assertEqual(verify_code, 0)

            canary_code, _ = canary_staged(meta_root, stage_path, work_dir)
            self.assertEqual(canary_code, 0)

            commit_code, commit_out = commit_staged(meta_root, stage_path, receipt_path)
            self.assertEqual(commit_code, 0)
            self.assertEqual(commit_out.get("verdict"), "COMMITTED")

            audit_code, audit_out = audit_active(meta_root)
            self.assertEqual(audit_code, 0)
            self.assertEqual(audit_out.get("verdict"), "OK")
            self.assertEqual(audit_out.get("prev_active_bundle_hash"), parent_hash)

            active_path = os.path.join(meta_root, "active", "ACTIVE_BUNDLE")
            with open(active_path, "r", encoding="utf-8") as f:
                active_hash = f.read()
            self.assertEqual(active_hash, commit_out["active_bundle_hash"] + "\n")

            store_dir = os.path.join(
                meta_root, "store", "bundles", commit_out["active_bundle_hash"]
            )
            self.assertTrue(os.path.isdir(store_dir))

    def test_audit_survives_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_root = _setup_temp_meta_core(tmpdir)
            bundle_dir = _fixture_path("valid_bundle")
            parent_hash = _seed_parent_bundle(meta_root)

            work_dir = os.path.join(meta_root, "active", "work")
            stage_code, stage_out = stage_bundle(meta_root, bundle_dir, work_dir)
            self.assertEqual(stage_code, 0)
            stage_path = stage_out["stage_path"]

            receipt_path = os.path.join(work_dir, "receipt.json")
            verify_code, _ = verify_staged(meta_root, stage_path, receipt_path)
            self.assertEqual(verify_code, 0)

            canary_code, _ = canary_staged(meta_root, stage_path, work_dir)
            self.assertEqual(canary_code, 0)

            commit_code, _ = commit_staged(meta_root, stage_path, receipt_path)
            self.assertEqual(commit_code, 0)

            rollback_code, _ = rollback_active(meta_root, "test")
            self.assertEqual(rollback_code, 0)

            audit_code, audit_out = audit_active(meta_root)
            self.assertEqual(audit_code, 0)
            self.assertEqual(audit_out.get("verdict"), "OK")
            self.assertEqual(audit_out.get("active_bundle_hash"), parent_hash)


if __name__ == "__main__":
    unittest.main()
