from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _omega_cache_root() -> Path:
    return _repo_root() / ".omega_cache"


def _rm_tree(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    import shutil

    shutil.rmtree(path)


@pytest.fixture()
def clean_native_cache():
    root = _omega_cache_root()
    _rm_tree(root / "native_blobs")
    _rm_tree(root / "native_runtime")
    yield
    _rm_tree(root / "native_blobs")
    _rm_tree(root / "native_runtime")


def test_repro_build_determinism_smoke(tmp_path: Path):
    from tools.omega.native.rust_codegen_v1 import generate_fnv1a64_cdylib
    from tools.omega.native.rust_vendor_v1 import vendor_crate
    from tools.omega.native.rust_build_repro_v1 import build_reproducible_cdylib, load_rust_toolchain_manifest

    crate_dir = tmp_path / "crate"
    meta = generate_fnv1a64_cdylib(op_id="omega_demo_fnv1a64_v1", out_dir=crate_dir)
    vendor_crate(crate_dir=crate_dir)

    toolchain_path = _repo_root() / "campaigns" / "rsi_omega_native_module_v0_1" / "toolchain_manifest_rust_v1.json"
    tool = load_rust_toolchain_manifest(toolchain_path)

    _bin, _receipt = build_reproducible_cdylib(crate_dir=crate_dir, crate_name=meta["crate_name"], toolchain_manifest=tool)

    # Negative: deterministic mismatch probe (forces different metadata per build).
    with pytest.raises(RuntimeError):
        build_reproducible_cdylib(
            crate_dir=crate_dir,
            crate_name=meta["crate_name"],
            toolchain_manifest=tool,
            _negative_force_mismatch=True,
        )


def test_router_fallback_then_native(clean_native_cache, tmp_path: Path):
    from orchestrator.native import demo_fnv1a64_v1
    from orchestrator.native import native_router_v1

    op_id = "omega_demo_fnv1a64_v1"
    data = b"hello"
    expected = demo_fnv1a64_v1.omega_demo_fnv1a64_v1(data)

    # No registry: python path.
    out = native_router_v1.route(op_id, data)
    assert out == expected

    # Build and install native blob + registry.
    from tools.omega.native.rust_codegen_v1 import generate_fnv1a64_cdylib
    from tools.omega.native.rust_vendor_v1 import vendor_crate
    from tools.omega.native.rust_build_repro_v1 import build_reproducible_cdylib, load_rust_toolchain_manifest

    crate_dir = tmp_path / "crate"
    meta = generate_fnv1a64_cdylib(op_id=op_id, out_dir=crate_dir)
    vendor_crate(crate_dir=crate_dir)
    toolchain_path = _repo_root() / "campaigns" / "rsi_omega_native_module_v0_1" / "toolchain_manifest_rust_v1.json"
    tool = load_rust_toolchain_manifest(toolchain_path)
    built_path, receipt = build_reproducible_cdylib(crate_dir=crate_dir, crate_name=meta["crate_name"], toolchain_manifest=tool)

    sha = receipt["binary_sha256"]
    hex64 = sha.split(":", 1)[1]
    ext = ".dylib" if sys.platform == "darwin" else ".so"
    cache_blob = _omega_cache_root() / "native_blobs" / f"sha256_{hex64}{ext}"
    cache_blob.parent.mkdir(parents=True, exist_ok=True)
    cache_blob.write_bytes(built_path.read_bytes())

    active = {"schema_version": "omega_native_active_registry_v1", "ops": {op_id: {"binary_sha256": sha}}}
    reg_path = _omega_cache_root() / "native_runtime" / "active_registry_v1.json"
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(json.dumps(active, sort_keys=True, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    # Prove native execution by breaking the python reference impl.
    orig = demo_fnv1a64_v1.omega_demo_fnv1a64_v1

    def _boom(_data: bytes) -> bytes:
        raise RuntimeError("python impl should not run when native active")

    demo_fnv1a64_v1.omega_demo_fnv1a64_v1 = _boom  # type: ignore[assignment]
    try:
        out2 = native_router_v1.route(op_id, data)
        assert out2 == expected
    finally:
        demo_fnv1a64_v1.omega_demo_fnv1a64_v1 = orig  # type: ignore[assignment]


def test_shadow_mode_disables_on_mismatch(clean_native_cache, tmp_path: Path):
    from orchestrator.native import native_router_v1

    op_id = "omega_demo_fnv1a64_v1"
    policy_path = _repo_root() / "orchestrator" / "native" / "native_policy_registry_v1.json"
    original = policy_path.read_text(encoding="utf-8")
    try:
        policy = json.loads(original)
        for row in policy["ops"]:
            if row["op_id"] == op_id:
                row["verification_mode"] = "SHADOW"
                row["shadow_calls_u32"] = 3
        policy_path.write_text(json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

        # Build a deliberately wrong native binary by tweaking the generated code.
        from tools.omega.native.rust_codegen_v1 import generate_fnv1a64_cdylib
        from tools.omega.native.rust_vendor_v1 import vendor_crate
        from tools.omega.native.rust_build_repro_v1 import build_reproducible_cdylib, load_rust_toolchain_manifest

        crate_dir = tmp_path / "crate"
        meta = generate_fnv1a64_cdylib(op_id=op_id, out_dir=crate_dir)
        lib_rs = crate_dir / "src" / "lib.rs"
        text = lib_rs.read_text(encoding="utf-8")
        # Make output wrong deterministically.
        text = text.replace("Ok(h.to_le_bytes().to_vec())", "Ok((h.wrapping_add(1)).to_le_bytes().to_vec())")
        lib_rs.write_text(text, encoding="utf-8")
        vendor_crate(crate_dir=crate_dir)

        toolchain_path = _repo_root() / "campaigns" / "rsi_omega_native_module_v0_1" / "toolchain_manifest_rust_v1.json"
        tool = load_rust_toolchain_manifest(toolchain_path)
        built_path, receipt = build_reproducible_cdylib(crate_dir=crate_dir, crate_name=meta["crate_name"], toolchain_manifest=tool)

        sha = receipt["binary_sha256"]
        hex64 = sha.split(":", 1)[1]
        ext = ".dylib" if sys.platform == "darwin" else ".so"
        cache_blob = _omega_cache_root() / "native_blobs" / f"sha256_{hex64}{ext}"
        cache_blob.parent.mkdir(parents=True, exist_ok=True)
        cache_blob.write_bytes(built_path.read_bytes())

        active = {"schema_version": "omega_native_active_registry_v1", "ops": {op_id: {"binary_sha256": sha}}}
        reg_path = _omega_cache_root() / "native_runtime" / "active_registry_v1.json"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text(json.dumps(active, sort_keys=True, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

        out = native_router_v1.route(op_id, b"hello")
        # Must not raise; mismatch should disable and return python output.
        assert isinstance(out, (bytes, bytearray))

        disabled_path = _omega_cache_root() / "native_runtime" / "disabled_v1.json"
        disabled = json.loads(disabled_path.read_text(encoding="utf-8"))
        assert disabled["disabled"].get(f"{op_id}|{sha}")
    finally:
        policy_path.write_text(original, encoding="utf-8")


def test_verifier_valid_then_corrupt_rejected(tmp_path: Path):
    from cdel.v18_0.campaign_omega_native_module_v0_1 import run as run_campaign
    from cdel.v18_0.verify_rsi_omega_native_module_v0_1 import verify
    from cdel.v18_0.omega_common_v1 import OmegaV18Error

    pack = _repo_root() / "campaigns" / "rsi_omega_native_module_v0_1" / "rsi_omega_native_module_pack_v0_1.json"
    run_campaign(campaign_pack=pack, out_dir=tmp_path)

    state_dir = tmp_path / "daemon" / "rsi_omega_native_module_v0_1" / "state"
    assert verify(state_dir, mode="full") == "VALID"

    # Corrupt the produced blob and ensure verifier fails closed.
    blobs = sorted((state_dir / "native" / "blobs").glob("sha256_*.*"), key=lambda p: p.as_posix())
    assert blobs
    blob = blobs[0]
    raw = bytearray(blob.read_bytes())
    raw[0] ^= 0x01
    blob.write_bytes(bytes(raw))

    with pytest.raises(OmegaV18Error):
        verify(state_dir, mode="full")


def test_activation_gate_rollback_on_missing_binary(clean_native_cache, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from cdel.v18_0.omega_activator_v1 import run_activation
    from cdel.v18_0.omega_common_v1 import canon_hash_obj

    monkeypatch.setenv("OMEGA_ALLOW_SIMULATE_ACTIVATION", "1")
    monkeypatch.setenv("OMEGA_META_CORE_ACTIVATION_MODE", "simulate")

    dispatch_dir = tmp_path / "daemon" / "rsi_omega_daemon_v18_0" / "state" / "dispatch" / "disp_0001"
    (dispatch_dir / "promotion").mkdir(parents=True, exist_ok=True)
    (dispatch_dir / "activation").mkdir(parents=True, exist_ok=True)

    # Create binding with native_module but no produced binary in subrun root.
    native_module = {
        "op_id": "omega_demo_fnv1a64_v1",
        "abi_version_u32": 1,
        "abi_kind": "BLOBLIST_V1",
        "language": "RUST",
        "platform": "aarch64-apple-darwin",
        "binary_sha256": "sha256:" + ("1" * 64),
        "source_manifest_hash": "sha256:" + ("0" * 64),
        "vendor_manifest_hash": "sha256:" + ("0" * 64),
        "build_receipt_hash": "sha256:" + ("0" * 64),
        "hotspot_report_hash": "sha256:" + ("0" * 64),
        "toolchain_manifest_hash": "sha256:" + ("0" * 64),
        "healthcheck_receipt_hash": "sha256:" + ("0" * 64),
        "bench_report_hash": "sha256:" + ("0" * 64),
    }
    binding_wo_id = {
        "schema_version": "omega_activation_binding_v1",
        "tick_u64": 1,
        "campaign_id": "rsi_omega_native_module_v0_1",
        "capability_id": "RSI_OMEGA_NATIVE_MODULE",
        "promotion_bundle_hash": "sha256:" + ("2" * 64),
        "activation_key": native_module["binary_sha256"],
        "source_run_root_rel": "run_0000",
        "subverifier_receipt_hash": "sha256:" + ("3" * 64),
        "meta_core_promo_verify_receipt_hash": "sha256:" + ("4" * 64),
        "native_module": native_module,
    }
    binding = dict(binding_wo_id)
    binding["binding_id"] = canon_hash_obj(binding_wo_id)
    (dispatch_dir / "promotion" / "omega_activation_binding_v1.json").write_text(
        json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )

    promotion_receipt = {
        "schema_version": "omega_promotion_receipt_v1",
        "receipt_id": "sha256:" + ("5" * 64),
        "tick_u64": 1,
        "promotion_bundle_hash": "sha256:" + ("6" * 64),
        "execution_mode": "STRICT",
        "meta_core_verifier_fingerprint": {"constitution_meta_hash": "x", "binary_hash_or_build_id": "y"},
        "native_module": native_module,
        "result": {"status": "PROMOTED", "reason_code": None},
        "active_manifest_hash_after": "sha256:" + ("7" * 64),
    }

    dispatch_ctx = {
        "dispatch_dir": str(dispatch_dir),
        "subrun_root_abs": str(tmp_path / "subrun_missing"),
        "meta_core_activation_bundle_dir": str(tmp_path / "fake_bundle"),
        "activation_binding_id": binding["binding_id"],
    }

    suite = {"schema_version": "healthcheck_suitepack_v1", "checks": []}
    activation_receipt, _activation_hash, rollback_receipt, _rollback_hash, _final_hash = run_activation(
        tick_u64=1,
        dispatch_ctx=dispatch_ctx,
        promotion_receipt=promotion_receipt,
        healthcheck_suitepack=suite,
        healthcheck_suite_hash="sha256:" + ("8" * 64),
        active_manifest_hash_before="sha256:" + ("0" * 64),
    )
    assert activation_receipt is not None
    assert rollback_receipt is not None
    assert activation_receipt["native_activation_gate_result"] == "FAIL"
    assert activation_receipt["native_gate_reason"] == "NATIVE_GATE_BINARY_MISSING"
    assert "NATIVE_GATE_FAILED" in activation_receipt["reasons"]
