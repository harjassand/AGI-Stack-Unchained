import json
import os
import shutil
import sys
import tempfile
import unittest

ENGINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "engine"))
sys.path.insert(0, ENGINE_DIR)

from apply import apply_bundle  # noqa: E402
from audit import audit_active  # noqa: E402
from atomic_fs import atomic_write_text  # noqa: E402
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


def _run_apply(meta_root: str) -> tuple[dict, dict, str]:
    bundle_dir = _fixture_path("valid_bundle")
    parent_hash = _seed_parent_bundle(meta_root)
    code, out = apply_bundle(meta_root, bundle_dir)
    if code != 0:
        raise RuntimeError("apply failed")
    audit_code, audit_out = audit_active(meta_root)
    if audit_code != 0:
        raise RuntimeError("audit failed")
    return out, audit_out, parent_hash


class TestApplyDeterminism(unittest.TestCase):
    def test_apply_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            meta_root_1 = _setup_temp_meta_core(tmp1)
            meta_root_2 = _setup_temp_meta_core(tmp2)

            out1, audit1, parent1 = _run_apply(meta_root_1)
            out2, audit2, parent2 = _run_apply(meta_root_2)

            self.assertEqual(parent1, parent2)
            self.assertEqual(out1, out2)
            self.assertEqual(audit1, audit2)


if __name__ == "__main__":
    unittest.main()
