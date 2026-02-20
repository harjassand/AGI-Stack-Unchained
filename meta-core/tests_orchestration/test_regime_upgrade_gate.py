import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ENGINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "engine"))
sys.path.insert(0, ENGINE_DIR)

from regime_upgrade import commit_staged_regime_upgrade  # noqa: E402
from constants import FAILPOINT_AFTER_NEXT_WRITE, FAILPOINT_ENV  # noqa: E402


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, sort_keys=True)


class TestRegimeUpgradeGate(unittest.TestCase):
    def test_auto_swap_requires_tier_b_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta_root = os.path.join(tmp, "meta-core")
            stage_path = os.path.join(tmp, "stage.json")
            receipt_path = os.path.join(tmp, "receipt.json")
            readiness_path = os.path.join(tmp, "readiness.json")
            os.makedirs(meta_root, exist_ok=True)
            _write_json(
                stage_path,
                {"bundle_hash": "a" * 64},
            )
            _write_json(
                readiness_path,
                {
                    "schema_name": "shadow_regime_readiness_receipt_v1",
                    "schema_version": "v19_0",
                    "tier_a_pass_b": True,
                    "tier_b_pass_b": False,
                    "runtime_tier_b_pass_b": False,
                },
            )
            _write_json(receipt_path, {"ok": True})

            code, out = commit_staged_regime_upgrade(
                os.path.abspath(meta_root),
                os.path.abspath(stage_path),
                os.path.abspath(receipt_path),
                os.path.abspath(readiness_path),
                auto_swap_b=True,
            )
            self.assertEqual(code, 2)
            self.assertEqual(out.get("reason_code"), "TIER_B_REQUIRED_FOR_SWAP")

    def test_ready_receipt_allows_regime_upgrade_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta_root = os.path.join(tmp, "meta-core")
            os.makedirs(os.path.join(meta_root, "active", "ledger"), exist_ok=True)
            stage_path = os.path.join(tmp, "stage.json")
            receipt_path = os.path.join(tmp, "receipt.json")
            readiness_path = os.path.join(tmp, "readiness.json")
            bundle_hash = "b" * 64
            _write_json(stage_path, {"bundle_hash": bundle_hash})
            _write_json(receipt_path, {"ok": True})
            _write_json(
                readiness_path,
                {
                    "schema_name": "shadow_regime_readiness_receipt_v1",
                    "schema_version": "v19_0",
                    "tier_a_pass_b": True,
                    "tier_b_pass_b": True,
                    "runtime_tier_b_pass_b": True,
                },
            )

            with mock.patch("regime_upgrade.commit_staged", return_value=(0, {"verdict": "COMMITTED"})):
                with mock.patch("regime_upgrade.read_last_entry", return_value=(1, "0" * 64)):
                    with mock.patch("regime_upgrade.append_entry_crash_safe", return_value=None):
                        code, out = commit_staged_regime_upgrade(
                            os.path.abspath(meta_root),
                            os.path.abspath(stage_path),
                            os.path.abspath(receipt_path),
                            os.path.abspath(readiness_path),
                            auto_swap_b=True,
                        )
            self.assertEqual(code, 0)
            self.assertTrue(out.get("regime_upgrade_b"))

    def test_failpoint_after_next_write_returns_internal_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta_root = os.path.join(tmp, "meta-core")
            os.makedirs(os.path.join(meta_root, "active", "ledger"), exist_ok=True)
            stage_path = os.path.join(tmp, "stage.json")
            receipt_path = os.path.join(tmp, "receipt.json")
            readiness_path = os.path.join(tmp, "readiness.json")
            bundle_hash = "c" * 64
            _write_json(stage_path, {"bundle_hash": bundle_hash})
            _write_json(receipt_path, {"ok": True})
            _write_json(
                readiness_path,
                {
                    "schema_name": "shadow_regime_readiness_receipt_v1",
                    "schema_version": "v19_0",
                    "tier_a_pass_b": True,
                    "tier_b_pass_b": True,
                    "runtime_tier_b_pass_b": True,
                },
            )

            os.environ[FAILPOINT_ENV] = FAILPOINT_AFTER_NEXT_WRITE
            try:
                with mock.patch("regime_upgrade.commit_staged") as commit_mock:
                    code, out = commit_staged_regime_upgrade(
                        os.path.abspath(meta_root),
                        os.path.abspath(stage_path),
                        os.path.abspath(receipt_path),
                        os.path.abspath(readiness_path),
                        auto_swap_b=True,
                    )
                    commit_mock.assert_not_called()
            finally:
                os.environ.pop(FAILPOINT_ENV, None)

            self.assertEqual(code, 1)
            self.assertEqual(out.get("verdict"), "INTERNAL_ERROR")
            active_next_path = os.path.join(meta_root, "active", "ACTIVE_NEXT_BUNDLE")
            with open(active_next_path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), bundle_hash)


if __name__ == "__main__":
    unittest.main()
