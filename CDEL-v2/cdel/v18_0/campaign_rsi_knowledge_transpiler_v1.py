"""RSI knowledge transpiler campaign v1.

Consumes a SIP knowledge artifact hash + kernel spec and produces a deterministic
WASM-native promotion bundle for SHADOW installation.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v1_7r.canon import write_canon_json
from .omega_common_v1 import (
    canon_hash_obj,
    fail,
    load_canon_dict,
    repo_root,
    validate_schema,
    write_hashed_json,
)


_CAMPAIGN_ID = "rsi_knowledge_transpiler_v1"
_PACK_SCHEMA = "rsi_knowledge_transpiler_pack_v1"


def _load_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != _PACK_SCHEMA:
        fail("SCHEMA_FAIL")
    return payload


def _require_sha(value: Any) -> str:
    text = str(value).strip()
    if not text.startswith("sha256:") or len(text.split(":", 1)[1]) != 64:
        fail("SCHEMA_FAIL")
    return text


def _derive_polymath_kernel_spec_from_epistemic(epistemic_spec: dict[str, Any]) -> dict[str, Any]:
    kernel_spec_id = _require_sha(epistemic_spec.get("kernel_spec_id"))
    seed = int(kernel_spec_id.split(":", 1)[1][:16], 16)
    alpha_q32 = int((seed & 0x7FFFFFFF) - (1 << 30))
    beta_q32 = int(((seed >> 8) & 0x7FFFFFFF) - (1 << 30))
    bias_q32 = int(((seed >> 16) & 0x1FFFFFFF) - (1 << 26))
    return {
        "schema_version": "polymath_kernel_spec_v1",
        "kernel_kind": "Q32_AFFINE",
        "theory_id": "qxwmr_epistemic_kernel_v1",
        "alpha_q32": alpha_q32,
        "beta_q32": beta_q32,
        "bias_q32": bias_q32,
        "healthcheck_vectors": [
            {"x_q32": 0, "y_q32": 0},
            {"x_q32": 1 << 32, "y_q32": 0},
            {"x_q32": 0, "y_q32": 1 << 32},
            {"x_q32": -(1 << 31), "y_q32": (3 << 30)},
        ],
    }


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    pack = _load_pack(campaign_pack)
    root = repo_root().resolve()

    kernel_spec_rel = str(pack.get("kernel_spec_rel", "")).strip()
    rust_toolchain_rel = str(pack.get("rust_toolchain_manifest_rel", "")).strip()
    wasmtime_manifest_rel = str(pack.get("wasmtime_manifest_rel", "")).strip()
    sip_knowledge_artifact_hash = _require_sha(pack.get("sip_knowledge_artifact_hash"))
    sip_empirical_evidence_hash = _require_sha(pack.get("sip_empirical_evidence_hash"))
    if not kernel_spec_rel or not rust_toolchain_rel or not wasmtime_manifest_rel:
        fail("SCHEMA_FAIL")
    emit_metal_b = bool(pack.get("emit_metal_b", True))
    strict_metal_b = bool(pack.get("strict_metal_b", False))

    state_root = out_dir.resolve() / "daemon" / _CAMPAIGN_ID / "state"
    promotion_dir = state_root / "promotion"
    promotion_dir.mkdir(parents=True, exist_ok=True)

    kernel_spec_path = (root / kernel_spec_rel).resolve()
    kernel_spec_payload = load_canon_dict(kernel_spec_path)
    kernel_spec_for_transpile_path = kernel_spec_path
    kernel_schema_version = str(kernel_spec_payload.get("schema_version", "")).strip()
    if kernel_schema_version == "epistemic_kernel_spec_v1":
        from ..v19_0.common_v1 import validate_schema as validate_schema_v19

        validate_schema_v19(kernel_spec_payload, "epistemic_kernel_spec_v1")
        if str(kernel_spec_payload.get("input_schema", "")) != "qxwmr_graph_v1":
            fail("SCHEMA_FAIL")
        expected_kernel_spec_id = _require_sha(kernel_spec_payload.get("kernel_spec_id"))
        if expected_kernel_spec_id != canon_hash_obj({k: v for k, v in kernel_spec_payload.items() if k != "kernel_spec_id"}):
            fail("PIN_HASH_MISMATCH")
        normalized_dir = state_root / "native" / "kernel_specs"
        normalized_dir.mkdir(parents=True, exist_ok=True)
        write_canon_json(
            normalized_dir / f"sha256_{expected_kernel_spec_id.split(':', 1)[1]}.epistemic_kernel_spec_v1.json",
            kernel_spec_payload,
        )
        derived_kernel_spec = _derive_polymath_kernel_spec_from_epistemic(kernel_spec_payload)
        derived_hash = canon_hash_obj(derived_kernel_spec)
        kernel_spec_for_transpile_path = normalized_dir / f"sha256_{derived_hash.split(':', 1)[1]}.polymath_kernel_spec_v1.json"
        write_canon_json(kernel_spec_for_transpile_path, derived_kernel_spec)

    from tools.polymath.polymath_knowledge_transpiler_v1 import run_transpile

    result = run_transpile(
        state_root=state_root,
        sip_knowledge_artifact_hash=sip_knowledge_artifact_hash,
        kernel_spec_path=kernel_spec_for_transpile_path,
        rust_toolchain_manifest_path=(root / rust_toolchain_rel).resolve(),
        wasmtime_manifest_path=(root / wasmtime_manifest_rel).resolve(),
        emit_metal=bool(emit_metal_b),
        strict_metal=bool(strict_metal_b),
    )

    status = str(result.get("status", "")).strip()
    if status != "OK":
        # Fail-closed gate: artifacts are written by transpiler, no promotion bundle.
        print(status)
        return

    health_path = Path(str(result["healthcheck_receipt_path"]))
    health_payload = load_canon_dict(health_path)
    if str(health_payload.get("result", "")) != "PASS":
        print("HEALTHCHECK_FAIL")
        return

    source_merkle_hash = _require_sha(result.get("source_merkle_hash"))
    build_proof_hash = _require_sha(result.get("build_proof_hash"))
    restricted_ir_hash = _require_sha(result.get("restricted_ir_hash"))
    runtime_contract_hash = _require_sha(result.get("runtime_contract_hash"))
    healthcheck_vectors_hash = _require_sha(result.get("healthcheck_vectors_hash"))
    healthcheck_receipt_hash = _require_sha(result.get("healthcheck_receipt_hash"))
    native_binary_hash = _require_sha(result.get("native_binary_hash"))
    rust_toolchain_hash = _require_sha(result.get("rust_toolchain_hash"))

    optional_metal_fields: dict[str, str] = {}
    for field in (
        "metal_src_merkle_hash",
        "metal_build_proof_hash",
        "metal_healthcheck_vectors_hash",
        "metal_healthcheck_receipt_hash",
        "metal_binary_hash",
        "metal_toolchain_manifest_hash",
    ):
        raw = result.get(field)
        if raw is None:
            continue
        optional_metal_fields[field] = _require_sha(raw)

    native_module = {
        "op_id": str(result.get("op_id", "")).strip() or "omega_kernel_eval_v1",
        "abi_version_u32": 1,
        "abi_kind": "BLOBLIST_V1",
        "language": "RUST",
        "platform": "wasm32-unknown-unknown",
        "binary_sha256": native_binary_hash,
        "source_manifest_hash": source_merkle_hash,
        "vendor_manifest_hash": runtime_contract_hash,
        "build_receipt_hash": build_proof_hash,
        "hotspot_report_hash": restricted_ir_hash,
        "toolchain_manifest_hash": rust_toolchain_hash,
        "healthcheck_receipt_hash": healthcheck_receipt_hash,
        "bench_report_hash": healthcheck_vectors_hash,
    }

    bundle_payload = {
        "schema_version": "omega_promotion_bundle_native_transpiler_v1_1",
        "bundle_id": "sha256:" + ("0" * 64),
        "campaign_id": _CAMPAIGN_ID,
        "native_module": native_module,
        "restricted_ir_hash": restricted_ir_hash,
        "source_merkle_hash": source_merkle_hash,
        "build_proof_hash": build_proof_hash,
        "runtime_contract_hash": runtime_contract_hash,
        "healthcheck_vectors_hash": healthcheck_vectors_hash,
        "healthcheck_receipt_hash": healthcheck_receipt_hash,
        "sip_knowledge_artifact_hash": sip_knowledge_artifact_hash,
        "sip_empirical_evidence_hash": sip_empirical_evidence_hash,
        "native_binary_hash": native_binary_hash,
        "install_intent": "STATUS_SHADOW",
    }
    bundle_payload.update(optional_metal_fields)
    validate_schema(bundle_payload, "omega_promotion_bundle_native_transpiler_v1_1")

    _, bundle_obj, _ = write_hashed_json(
        promotion_dir,
        "omega_promotion_bundle_native_transpiler_v1_1.json",
        bundle_payload,
        id_field="bundle_id",
    )
    write_canon_json(promotion_dir / "omega_promotion_bundle_native_transpiler_v1_1.json", bundle_obj)
    print("OK")


def main() -> None:
    ap = argparse.ArgumentParser(prog="campaign_rsi_knowledge_transpiler_v1")
    ap.add_argument("--campaign_pack", required=True)
    ap.add_argument("--out_dir", required=True)
    args = ap.parse_args()
    run(campaign_pack=Path(args.campaign_pack).resolve(), out_dir=Path(args.out_dir).resolve())


if __name__ == "__main__":
    main()
