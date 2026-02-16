import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_wrapper_module():
    module_path = Path(__file__).resolve().parents[1] / "kernel" / "verify_promotion_bundle.py"
    spec = importlib.util.spec_from_file_location("verify_promotion_bundle_wrapper", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load verify_promotion_bundle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_canon_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_ref(wrapper: object, bundle_dir: Path, relpath: str, payload: dict, *, id_field: str | None = None) -> dict[str, str]:
    obj = dict(payload)
    if id_field is not None:
        no_id = dict(obj)
        no_id.pop(id_field, None)
        obj[id_field] = wrapper._canon_hash(no_id)
    abs_path = bundle_dir / relpath
    _write_canon_json(abs_path, obj)
    return {
        "artifact_id": wrapper._canon_hash(obj),
        "artifact_relpath": relpath,
    }


def _build_axis_bundle(wrapper: object, bundle_dir: Path, *, continuity_outcome: str) -> dict:
    sigma_old_ref = _write_ref(wrapper, bundle_dir, "omega/sigma_old.json", {"state": "old"})
    sigma_new_ref = _write_ref(wrapper, bundle_dir, "omega/sigma_new.json", {"state": "new"})
    objective_ref = _write_ref(wrapper, bundle_dir, "omega/j_profile.json", {"profile": "j"})

    def _regime(prefix: str) -> dict[str, dict[str, str]]:
        return {
            "C": _write_ref(wrapper, bundle_dir, f"omega/{prefix}_C.json", {"kind": "C"}),
            "K": _write_ref(wrapper, bundle_dir, f"omega/{prefix}_K.json", {"kind": "K"}),
            "E": _write_ref(wrapper, bundle_dir, f"omega/{prefix}_E.json", {"kind": "E"}),
            "W": _write_ref(wrapper, bundle_dir, f"omega/{prefix}_W.json", {"kind": "W"}),
            "T": _write_ref(wrapper, bundle_dir, f"omega/{prefix}_T.json", {"kind": "T"}),
        }

    old_regime = _regime("old")
    new_regime = _regime("new")
    morphism_ref = _write_ref(wrapper, bundle_dir, "omega/morphism.json", {"kind": "M"})
    overlap_ref = _write_ref(wrapper, bundle_dir, "omega/overlap.json", {"kind": "O"})
    translator_ref = _write_ref(wrapper, bundle_dir, "omega/translator.json", {"kind": "T"})
    totality_ref = _write_ref(wrapper, bundle_dir, "omega/totality.json", {"kind": "TOT"})
    continuity_ref = _write_ref(
        wrapper,
        bundle_dir,
        "omega/continuity_receipt.json",
        {
            "schema_name": "continuity_receipt_v1",
            "schema_version": "v19_0",
            "final_outcome": continuity_outcome,
        },
    )
    axis_wo_id = {
        "schema_name": "axis_upgrade_bundle_v1",
        "schema_version": "v19_0",
        "sigma_old_ref": sigma_old_ref,
        "sigma_new_ref": sigma_new_ref,
        "regime_old_ref": old_regime,
        "regime_new_ref": new_regime,
        "objective_J_profile_ref": objective_ref,
        "continuity_budget": {"policy": "SAFE_HALT"},
        "morphisms": [
            {
                "morphism_ref": morphism_ref,
                "overlap_profile_ref": overlap_ref,
                "translator_bundle_ref": translator_ref,
                "totality_cert_ref": totality_ref,
                "continuity_receipt_ref": continuity_ref,
                "axis_specific_proof_refs": [],
            }
        ],
    }
    axis = dict(axis_wo_id)
    axis["axis_bundle_id"] = wrapper._canon_hash(axis_wo_id)
    return axis


class TestVerifyPromotionBundleWrapper(unittest.TestCase):
    def test_ensure_release_verifier_uses_existing_binary_when_hash_matches(self) -> None:
        wrapper = _load_wrapper_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "meta-core"
            verifier_bin = root / "kernel" / "verifier" / "target" / "release" / "verifier"
            verifier_bin.parent.mkdir(parents=True, exist_ok=True)
            verifier_bytes = b"verifier-bin"
            verifier_bin.write_bytes(verifier_bytes)
            os.chmod(verifier_bin, 0o755)
            (root / "kernel" / "verifier" / "KERNEL_HASH").write_text(
                _sha256_hex(verifier_bytes) + "\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"META_CORE_ENFORCE_KERNEL_HASH": "1"}), patch.object(
                wrapper, "_build_release_verifier"
            ) as mocked_build:
                resolved = wrapper._ensure_release_verifier(root)

            self.assertEqual(resolved, verifier_bin)
            mocked_build.assert_not_called()

    def test_ensure_release_verifier_rebuilds_on_mismatch(self) -> None:
        wrapper = _load_wrapper_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "meta-core"
            verifier_bin = root / "kernel" / "verifier" / "target" / "release" / "verifier"
            verifier_bin.parent.mkdir(parents=True, exist_ok=True)
            verifier_bin.write_bytes(b"old-binary")
            os.chmod(verifier_bin, 0o755)
            expected_bytes = b"new-binary"
            (root / "kernel" / "verifier" / "KERNEL_HASH").write_text(
                _sha256_hex(expected_bytes) + "\n",
                encoding="utf-8",
            )

            def _fake_build(meta_core_root: Path) -> None:
                self.assertEqual(meta_core_root, root)
                verifier_bin.write_bytes(expected_bytes)
                os.chmod(verifier_bin, 0o755)

            with patch.dict(os.environ, {"META_CORE_ENFORCE_KERNEL_HASH": "1"}), patch.object(
                wrapper, "_build_release_verifier", side_effect=_fake_build
            ) as mocked_build:
                resolved = wrapper._ensure_release_verifier(root)

            self.assertEqual(resolved, verifier_bin)
            mocked_build.assert_called_once()

    def test_enforce_continuity_sidecar_missing_artifact(self) -> None:
        wrapper = _load_wrapper_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_dir = Path(tmpdir) / "bundle"
            axis = _build_axis_bundle(wrapper, bundle_dir, continuity_outcome="ACCEPT")
            axis["morphisms"][0]["continuity_receipt_ref"] = {
                "artifact_id": "sha256:" + ("a" * 64),
                "artifact_relpath": "omega/missing_continuity_receipt.json",
            }
            axis_no_id = dict(axis)
            axis_no_id.pop("axis_bundle_id", None)
            axis["axis_bundle_id"] = wrapper._canon_hash(axis_no_id)
            _write_canon_json(bundle_dir / "omega" / "axis_upgrade_bundle_v1.json", axis)

            with self.assertRaisesRegex(RuntimeError, "CONTINUITY_MISSING_ARTIFACT"):
                wrapper._enforce_continuity_sidecar(bundle_dir)

    def test_enforce_continuity_sidecar_non_canonical_json(self) -> None:
        wrapper = _load_wrapper_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_dir = Path(tmpdir) / "bundle"
            axis = _build_axis_bundle(wrapper, bundle_dir, continuity_outcome="ACCEPT")
            axis_path = bundle_dir / "omega" / "axis_upgrade_bundle_v1.json"
            axis_path.parent.mkdir(parents=True, exist_ok=True)
            axis_path.write_text(json.dumps(axis, indent=2) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "CONTINUITY_SCHEMA_FAIL"):
                wrapper._enforce_continuity_sidecar(bundle_dir)

    def test_enforce_continuity_sidecar_receipt_not_accept(self) -> None:
        wrapper = _load_wrapper_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_dir = Path(tmpdir) / "bundle"
            axis = _build_axis_bundle(wrapper, bundle_dir, continuity_outcome="REJECT")
            _write_canon_json(bundle_dir / "omega" / "axis_upgrade_bundle_v1.json", axis)

            with self.assertRaisesRegex(RuntimeError, "CONTINUITY_RECEIPT_NOT_ACCEPT"):
                wrapper._enforce_continuity_sidecar(bundle_dir)


if __name__ == "__main__":
    unittest.main()
