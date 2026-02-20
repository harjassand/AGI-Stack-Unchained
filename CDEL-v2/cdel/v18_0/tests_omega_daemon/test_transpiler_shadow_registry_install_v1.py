from __future__ import annotations

import json
import os
import hashlib
from pathlib import Path

from cdel.v18_0.omega_activator_v1 import _install_native_shadow_registry, run_activation
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from orchestrator.native import native_router_v1
from orchestrator.native.wasm_shadow_soak_v1 import emit_shadow_soak_artifacts


def _write_canon(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")


def _seed_shadow_install_inputs(
    *,
    subrun_root: Path,
    wasm_bytes: bytes,
    runtime_host_triple: str,
) -> dict[str, str]:
    wasm_hash = "sha256:" + hashlib.sha256(wasm_bytes).hexdigest()
    wasm_path = (
        subrun_root
        / "daemon"
        / "rsi_knowledge_transpiler_v1"
        / "state"
        / "native"
        / "bin"
        / f"sha256_{wasm_hash.split(':', 1)[1]}.wasm"
    )
    wasm_path.parent.mkdir(parents=True, exist_ok=True)
    wasm_path.write_bytes(wasm_bytes)

    restricted_ir_hash = "sha256:" + ("2" * 64)
    src_merkle_hash = "sha256:" + ("3" * 64)
    build_proof_hash = "sha256:" + ("4" * 64)

    runtime_contract = {
        "schema_version": "native_wasm_runtime_contract_v1",
        "contract_id": "sha256:" + ("0" * 64),
        "runtime_engine": "wasmtime",
        "runtime_version": "node-test",
        "host_triple": runtime_host_triple,
        "runtime_binary_path": "/opt/homebrew/bin/node",
        "runtime_binary_sha256": "sha256:" + ("1" * 64),
        "argv_template": [
            "/opt/homebrew/bin/node",
            "runner",
            "{module_path}",
            "{arg0_i64}",
            "{arg1_i64}",
        ],
        "env_allowlist": [],
        "determinism_flags": {
            "disable_cache": True,
            "consume_fuel": True,
            "epoch_interruption": False,
            "canonicalize_nans": True,
        },
    }
    runtime_hash = canon_hash_obj(runtime_contract)
    runtime_path = (
        subrun_root
        / "daemon"
        / "rsi_knowledge_transpiler_v1"
        / "state"
        / "native"
        / "runtime"
        / f"sha256_{runtime_hash.split(':', 1)[1]}.native_wasm_runtime_contract_v1.json"
    )
    _write_canon(runtime_path, runtime_contract)

    vectors = {
        "schema_version": "native_wasm_healthcheck_vectors_v1",
        "vectors_id": "sha256:" + ("0" * 64),
        "op_id": "omega_kernel_eval_v1",
        "restricted_ir_hash": restricted_ir_hash,
        "vectors": [
            {
                "vector_id": "vec_0000",
                "argv_hex": ["0000000000000000", "0000000000000000"],
                "expected_output_sha256": "sha256:" + ("9" * 64),
            }
        ],
    }
    vectors_hash = canon_hash_obj(vectors)
    vectors_path = (
        subrun_root
        / "daemon"
        / "rsi_knowledge_transpiler_v1"
        / "state"
        / "native"
        / "vectors"
        / f"sha256_{vectors_hash.split(':', 1)[1]}.native_wasm_healthcheck_vectors_v1.json"
    )
    _write_canon(vectors_path, vectors)
    return {
        "wasm_hash": wasm_hash,
        "runtime_hash": runtime_hash,
        "vectors_hash": vectors_hash,
        "restricted_ir_hash": restricted_ir_hash,
        "src_merkle_hash": src_merkle_hash,
        "build_proof_hash": build_proof_hash,
    }


def _binding_payload_from_seed(seed: dict[str, str]) -> dict[str, object]:
    return {
        "campaign_id": "rsi_knowledge_transpiler_v1",
        "native_runtime_contract_hash": seed["runtime_hash"],
        "native_healthcheck_vectors_hash": seed["vectors_hash"],
        "native_restricted_ir_hash": seed["restricted_ir_hash"],
        "native_src_merkle_hash": seed["src_merkle_hash"],
        "native_build_proof_hash": seed["build_proof_hash"],
        "native_module": {
            "op_id": "omega_kernel_eval_v1",
            "binary_sha256": seed["wasm_hash"],
        },
    }


def test_transpiler_shadow_registry_install_writes_state_pointer(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    dispatch_dir = state_root / "dispatch" / "x1"
    dispatch_dir.mkdir(parents=True)

    subrun_root = state_root / "subruns" / "x1_rsi_knowledge_transpiler_v1"
    wasm_bytes = b"wasm-test-binary"
    wasm_hash = "sha256:" + hashlib.sha256(wasm_bytes).hexdigest()
    wasm_path = (
        subrun_root
        / "daemon"
        / "rsi_knowledge_transpiler_v1"
        / "state"
        / "native"
        / "bin"
        / f"sha256_{wasm_hash.split(':', 1)[1]}.wasm"
    )
    wasm_path.parent.mkdir(parents=True, exist_ok=True)
    wasm_path.write_bytes(wasm_bytes)

    restricted_ir_hash = "sha256:" + ("2" * 64)
    src_merkle_hash = "sha256:" + ("3" * 64)
    build_proof_hash = "sha256:" + ("4" * 64)

    runtime_contract = {
        "schema_version": "native_wasm_runtime_contract_v1",
        "contract_id": "sha256:" + ("0" * 64),
        "runtime_engine": "wasmtime",
        "runtime_version": "node-test",
        "host_triple": "arm64-apple-darwin",
        "runtime_binary_path": "/opt/homebrew/bin/node",
        "runtime_binary_sha256": "sha256:" + ("1" * 64),
        "argv_template": [
            "/opt/homebrew/bin/node",
            "runner",
            "{module_path}",
            "{arg0_i64}",
            "{arg1_i64}",
        ],
        "env_allowlist": [],
        "determinism_flags": {
            "disable_cache": True,
            "consume_fuel": True,
            "epoch_interruption": False,
            "canonicalize_nans": True,
        },
    }
    runtime_hash = canon_hash_obj(runtime_contract)
    runtime_path = (
        subrun_root
        / "daemon"
        / "rsi_knowledge_transpiler_v1"
        / "state"
        / "native"
        / "runtime"
        / f"sha256_{runtime_hash.split(':', 1)[1]}.native_wasm_runtime_contract_v1.json"
    )
    _write_canon(runtime_path, runtime_contract)

    vectors = {
        "schema_version": "native_wasm_healthcheck_vectors_v1",
        "vectors_id": "sha256:" + ("0" * 64),
        "op_id": "omega_kernel_eval_v1",
        "restricted_ir_hash": restricted_ir_hash,
        "vectors": [
            {
                "vector_id": "vec_0000",
                "argv_hex": ["0000000000000000", "0000000000000000"],
                "expected_output_sha256": "sha256:" + ("9" * 64),
            }
        ],
    }
    vectors_hash = canon_hash_obj(vectors)
    vectors_path = (
        subrun_root
        / "daemon"
        / "rsi_knowledge_transpiler_v1"
        / "state"
        / "native"
        / "vectors"
        / f"sha256_{vectors_hash.split(':', 1)[1]}.native_wasm_healthcheck_vectors_v1.json"
    )
    _write_canon(vectors_path, vectors)

    native_module = {
        "op_id": "omega_kernel_eval_v1",
        "abi_version_u32": 1,
        "abi_kind": "BLOBLIST_V1",
        "language": "RUST",
        "platform": "wasm32-unknown-unknown",
        "binary_sha256": wasm_hash,
        "source_manifest_hash": src_merkle_hash,
        "vendor_manifest_hash": runtime_hash,
        "build_receipt_hash": build_proof_hash,
        "hotspot_report_hash": restricted_ir_hash,
        "toolchain_manifest_hash": "sha256:" + ("5" * 64),
        "healthcheck_receipt_hash": "sha256:" + ("6" * 64),
        "bench_report_hash": vectors_hash,
    }
    binding_without_id = {
        "schema_version": "omega_activation_binding_v1",
        "tick_u64": 1,
        "campaign_id": "rsi_knowledge_transpiler_v1",
        "capability_id": "RSI_KNOWLEDGE_TRANSPILER",
        "promotion_bundle_hash": "sha256:" + ("a" * 64),
        "activation_key": "sha256:" + ("b" * 64),
        "source_run_root_rel": "run_x",
        "subverifier_receipt_hash": "sha256:" + ("c" * 64),
        "meta_core_promo_verify_receipt_hash": "sha256:" + ("d" * 64),
        "native_runtime_contract_hash": runtime_hash,
        "native_healthcheck_vectors_hash": vectors_hash,
        "native_restricted_ir_hash": restricted_ir_hash,
        "native_src_merkle_hash": src_merkle_hash,
        "native_build_proof_hash": build_proof_hash,
        "native_module": native_module,
    }
    binding_payload = dict(binding_without_id)
    binding_payload["binding_id"] = canon_hash_obj(binding_without_id)
    _write_canon(dispatch_dir / "promotion" / "omega_activation_binding_v1.json", binding_payload)

    marker = state_root / "health" / "pass.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("ok", encoding="utf-8")

    dispatch_ctx = {
        "dispatch_dir": dispatch_dir,
        "state_root": state_root,
        "subrun_root_abs": subrun_root,
    }
    promotion_receipt = {
        "result": {"status": "PROMOTED", "reason_code": None},
        "active_manifest_hash_after": "sha256:" + ("8" * 64),
    }
    suitepack = {
        "schema_version": "healthcheck_suitepack_v1",
        "checks": [
            {
                "check_id": "must_exist",
                "kind": "FILE_EXISTS",
                "target_rel": "health/pass.txt",
                "expected_hash": None,
                "required": True,
            }
        ],
    }

    prev_mode = os.environ.get("OMEGA_META_CORE_ACTIVATION_MODE")
    prev_allow = os.environ.get("OMEGA_ALLOW_SIMULATE_ACTIVATION")
    os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = "simulate"
    os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = "1"
    try:
        activation, _, rollback, _, _ = run_activation(
            tick_u64=1,
            dispatch_ctx=dispatch_ctx,
            promotion_receipt=promotion_receipt,
            healthcheck_suitepack=suitepack,
            healthcheck_suite_hash="sha256:" + ("7" * 64),
            active_manifest_hash_before="sha256:" + ("1" * 64),
        )
    finally:
        if prev_mode is None:
            os.environ.pop("OMEGA_META_CORE_ACTIVATION_MODE", None)
        else:
            os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = prev_mode
        if prev_allow is None:
            os.environ.pop("OMEGA_ALLOW_SIMULATE_ACTIVATION", None)
        else:
            os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = prev_allow

    assert rollback is None
    assert activation is not None
    assert activation["activation_success"] is True
    shadow_hash = str(activation.get("native_shadow_registry_hash", ""))
    assert shadow_hash.startswith("sha256:")

    pointer = state_root / "native" / "shadow" / "ACTIVE_SHADOW_REGISTRY"
    assert pointer.is_file()
    assert pointer.read_text(encoding="utf-8").strip() == shadow_hash

    registry_path = state_root / "native" / "shadow" / f"sha256_{shadow_hash.split(':', 1)[1]}.native_shadow_registry_v1.json"
    assert registry_path.is_file()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["schema_version"] == "native_shadow_registry_v1"
    assert registry["modules"][0]["status"] == "STATUS_SHADOW"
    assert registry["modules"][0]["binary_sha256"] == wasm_hash
    assert registry["modules"][0]["runtime_contract_hash"] == runtime_hash
    assert registry["modules"][0]["disabled_key"] == f"omega_kernel_eval_v1|{wasm_hash}"
    assert registry["modules"][0]["shadow_route_disabled_b"] is False
    assert registry["modules"][0]["shadow_route_disable_reason"] is None
    assert registry["modules"][0]["shadow_route_disable_tick_u64"] is None
    assert registry["modules"][0]["portability_status"] in {"RUNNABLE", "PORTABILITY_SKIP_RUN"}


def test_shadow_soak_summary_fails_when_portability_skip_run(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    shadow_dir = state_root / "native" / "shadow"
    shadow_dir.mkdir(parents=True, exist_ok=True)
    registry_payload = {
        "schema_version": "native_shadow_registry_v1",
        "registry_id": "sha256:" + ("0" * 64),
        "daemon_id": "rsi_omega_daemon_v19_0",
        "tick_u64": 7,
        "modules": [
            {
                "op_id": "omega_kernel_eval_v1",
                "binary_sha256": "sha256:" + ("1" * 64),
                "runtime_contract_hash": "sha256:" + ("2" * 64),
                "status": "STATUS_SHADOW",
                "campaign_id": "rsi_knowledge_transpiler_v1",
                "portability_status": "PORTABILITY_SKIP_RUN",
                "shadow_route_disabled_b": False,
                "shadow_route_disable_reason": None,
                "shadow_route_disable_tick_u64": None,
                "disabled_key": "omega_kernel_eval_v1|sha256:" + ("1" * 64),
            }
        ],
    }
    registry_payload["registry_id"] = canon_hash_obj({k: v for k, v in registry_payload.items() if k != "registry_id"})
    registry_hash = canon_hash_obj(registry_payload)
    _write_canon(
        shadow_dir / f"sha256_{registry_hash.split(':', 1)[1]}.native_shadow_registry_v1.json",
        registry_payload,
    )
    (shadow_dir / "ACTIVE_SHADOW_REGISTRY").write_text(f"{registry_hash}\n", encoding="utf-8")

    summary, _, receipt, _ = emit_shadow_soak_artifacts(state_root=state_root, tick_u64=7)
    assert summary["portability_status_snapshot"] == "PORTABILITY_SKIP_RUN"
    assert summary["shadow_ready_b"] is False
    assert summary["readiness_gate_result"] == "FAIL"
    assert "PORTABILITY_SKIP_RUN" in summary["readiness_reasons"]
    assert isinstance(receipt["rows"], list) and len(receipt["rows"]) == 1
    assert receipt["rows"][0]["route_disable_transition_b"] is False


def test_shadow_registry_new_binary_resets_route_disabled_state(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    subrun_one = state_root / "subruns" / "tick1"
    seed_one = _seed_shadow_install_inputs(
        subrun_root=subrun_one,
        wasm_bytes=b"wasm-one",
        runtime_host_triple="arm64-apple-darwin",
    )
    dispatch_ctx_one = {
        "state_root": state_root,
        "subrun_root_abs": subrun_one,
    }
    reg_hash_one = _install_native_shadow_registry(
        dispatch_ctx=dispatch_ctx_one,
        tick_u64=1,
        binding_payload=_binding_payload_from_seed(seed_one),
    )
    assert reg_hash_one.startswith("sha256:")

    monkeypatch.setenv("OMEGA_DAEMON_STATE_ROOT", str(state_root))
    monkeypatch.setenv("OMEGA_TICK_U64", "1")
    assert native_router_v1._disable_shadow_route(  # type: ignore[attr-defined]
        "omega_kernel_eval_v1",
        seed_one["wasm_hash"],
        reason="shadow_mismatch",
    )
    monkeypatch.setenv("OMEGA_TICK_U64", "2")
    assert (
        native_router_v1._disable_shadow_route(  # type: ignore[attr-defined]
            "omega_kernel_eval_v1",
            seed_one["wasm_hash"],
            reason="shadow_mismatch",
        )
        is False
    )

    subrun_two = state_root / "subruns" / "tick2"
    seed_two = _seed_shadow_install_inputs(
        subrun_root=subrun_two,
        wasm_bytes=b"wasm-two",
        runtime_host_triple="arm64-apple-darwin",
    )
    dispatch_ctx_two = {
        "state_root": state_root,
        "subrun_root_abs": subrun_two,
    }
    reg_hash_two = _install_native_shadow_registry(
        dispatch_ctx=dispatch_ctx_two,
        tick_u64=2,
        binding_payload=_binding_payload_from_seed(seed_two),
    )
    shadow_dir = state_root / "native" / "shadow"
    reg_path = shadow_dir / f"sha256_{reg_hash_two.split(':', 1)[1]}.native_shadow_registry_v1.json"
    registry = json.loads(reg_path.read_text(encoding="utf-8"))
    row = registry["modules"][0]
    assert row["binary_sha256"] == seed_two["wasm_hash"]
    assert row["disabled_key"] == f"omega_kernel_eval_v1|{seed_two['wasm_hash']}"
    assert row["shadow_route_disabled_b"] is False
    assert row["shadow_route_disable_reason"] is None
    assert row["shadow_route_disable_tick_u64"] is None
