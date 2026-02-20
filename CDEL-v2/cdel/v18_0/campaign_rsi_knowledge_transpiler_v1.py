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

    state_root = out_dir.resolve() / "daemon" / _CAMPAIGN_ID / "state"
    promotion_dir = state_root / "promotion"
    promotion_dir.mkdir(parents=True, exist_ok=True)

    from tools.polymath.polymath_knowledge_transpiler_v1 import run_transpile

    result = run_transpile(
        state_root=state_root,
        sip_knowledge_artifact_hash=sip_knowledge_artifact_hash,
        kernel_spec_path=(root / kernel_spec_rel).resolve(),
        rust_toolchain_manifest_path=(root / rust_toolchain_rel).resolve(),
        wasmtime_manifest_path=(root / wasmtime_manifest_rel).resolve(),
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
