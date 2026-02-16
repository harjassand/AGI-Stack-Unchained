import json
import os
import shutil
import sys
import tempfile
import unittest

ENGINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "engine"))
sys.path.insert(0, ENGINE_DIR)

from activation import (  # noqa: E402
    canary_staged,
    commit_staged,
    stage_bundle,
    verify_staged,
)
from atomic_fs import atomic_write_text  # noqa: E402
from hashing import (  # noqa: E402
    bundle_hash as compute_bundle_hash,
    manifest_hash,
    migration_hash,
    proof_bundle_hash,
    ruleset_hash,
    state_schema_hash,
    toolchain_merkle_root,
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


class TestRejectDoesNotMutateActive(unittest.TestCase):
    def test_reject_does_not_mutate_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_root = _setup_temp_meta_core(tmpdir)
            valid_bundle = _fixture_path("valid_bundle")
            invalid_bundle = _fixture_path("invalid_bundle_tamper")
            _seed_parent_bundle(meta_root)

            work_dir = os.path.join(meta_root, "active", "work")
            stage_code, stage_out = stage_bundle(meta_root, valid_bundle, work_dir)
            self.assertEqual(stage_code, 0)
            stage_path = stage_out["stage_path"]
            receipt_path = os.path.join(work_dir, "receipt.json")
            verify_code, _ = verify_staged(meta_root, stage_path, receipt_path)
            self.assertEqual(verify_code, 0)
            canary_code, _ = canary_staged(meta_root, stage_path, work_dir)
            self.assertEqual(canary_code, 0)
            commit_code, commit_out = commit_staged(meta_root, stage_path, receipt_path)
            self.assertEqual(commit_code, 0)
            active_hash = commit_out["active_bundle_hash"]

            stage_code, out_reject = stage_bundle(meta_root, invalid_bundle, work_dir)
            self.assertEqual(stage_code, 0)
            stage_path = out_reject["stage_path"]
            receipt_path = os.path.join(work_dir, "reject_receipt.json")
            verify_code, _ = verify_staged(meta_root, stage_path, receipt_path)
            self.assertEqual(verify_code, 2)

            active_path = os.path.join(meta_root, "active", "ACTIVE_BUNDLE")
            with open(active_path, "r", encoding="utf-8") as f:
                current_hash = f.read().strip()
            self.assertEqual(current_hash, active_hash)

            self.assertEqual(active_hash, current_hash)

    def test_parent_mismatch_rejects(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_root = _setup_temp_meta_core(tmpdir)
            parent_hash = _seed_parent_bundle(meta_root)

            valid_bundle = _fixture_path("valid_bundle")
            candidate_dir = os.path.join(tmpdir, "candidate_bundle")
            shutil.copytree(valid_bundle, candidate_dir)

            manifest_path = os.path.join(candidate_dir, "constitution.manifest.json")
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            mismatch_hash = "1" * 64 if parent_hash != "1" * 64 else "2" * 64
            manifest["parent_bundle_hash"] = mismatch_hash
            computed_manifest_hash = manifest_hash(manifest)
            computed_ruleset_hash = ruleset_hash(candidate_dir)
            computed_proof_hash = proof_bundle_hash(candidate_dir)
            computed_migration_hash = migration_hash(candidate_dir)
            computed_state_schema_hash = state_schema_hash(meta_root)
            computed_toolchain_root = toolchain_merkle_root(meta_root)
            computed_bundle_hash = compute_bundle_hash(
                computed_manifest_hash,
                computed_ruleset_hash,
                computed_proof_hash,
                computed_migration_hash,
                computed_state_schema_hash,
                computed_toolchain_root,
            )
            manifest["bundle_hash"] = computed_bundle_hash
            manifest["ruleset_hash"] = computed_ruleset_hash
            manifest["migration_hash"] = computed_migration_hash
            manifest["state_schema_hash"] = computed_state_schema_hash
            manifest["toolchain_merkle_root"] = computed_toolchain_root
            manifest.setdefault("proofs", {})["proof_bundle_hash"] = computed_proof_hash
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, separators=(",", ":"))

            work_dir = os.path.join(meta_root, "active", "work")
            stage_code, stage_out = stage_bundle(meta_root, candidate_dir, work_dir)
            self.assertEqual(stage_code, 0)
            stage_path = stage_out["stage_path"]
            receipt_path = os.path.join(work_dir, "receipt.json")
            verify_code, _ = verify_staged(meta_root, stage_path, receipt_path)
            self.assertEqual(verify_code, 2)

            active_path = os.path.join(meta_root, "active", "ACTIVE_BUNDLE")
            with open(active_path, "r", encoding="utf-8") as f:
                current_hash = f.read().strip()
            self.assertEqual(current_hash, parent_hash)

            self.assertEqual(current_hash, parent_hash)


if __name__ == "__main__":
    unittest.main()
