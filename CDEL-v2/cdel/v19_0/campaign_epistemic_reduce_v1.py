"""Campaign entrypoint for v19 epistemic reduce/capsule sealing."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v18_0.omega_common_v1 import repo_root, write_hashed_json
from .common_v1 import canon_hash_obj, ensure_sha256, load_canon_dict, validate_schema, verify_object_id
from .epistemic.capsule_v1 import build_epistemic_capsule, write_capsule_bundle
from .epistemic.sip_adapter_stub_v1 import ensure_disabled


def _tick_from_env() -> int:
    import os

    raw = str(os.environ.get("OMEGA_TICK_U64", "")).strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except Exception:  # noqa: BLE001
        return 0
    return max(0, value)


def _reason_from_exc(exc: Exception) -> str:
    text = str(exc).strip()
    if text.startswith("INVALID:"):
        text = text.split(":", 1)[1].strip()
    known = {
        "INDEX_CHAIN_MISMATCH",
        "INDEX_SELECTION_EMPTY",
        "EPISODE_NOT_COMPLETE",
        "EPISODE_MARKER_MISMATCH",
        "MOB_FORMAT_REJECTED",
        "MOB_SCHEMA_UNSUPPORTED",
        "REDUCE_REPLAY_MISMATCH",
        "BUDGET_EXHAUSTED",
        "NONDETERMINISTIC",
        "TYPE_GOVERNANCE_FAIL",
        "CERT_GATE_FAIL",
    }
    if text in known:
        return text
    if "SIP" in text and "REJECT" in text:
        return "SIP_REJECTED"
    if "SIP" in text and "SAFE_HALT" in text:
        return "SIP_SAFE_HALT"
    return "NONDETERMINISTIC"


def _write_refutation(*, state_root: Path, tick_u64: int, selector: dict[str, Any], reason: str, detail: str) -> tuple[dict[str, Any], str]:
    episode_id = str(selector.get("episode_id", "sha256:" + ("0" * 64))).strip() if isinstance(selector, dict) else "sha256:" + ("0" * 64)
    if not episode_id.startswith("sha256:"):
        episode_id = "sha256:" + ("0" * 64)
    payload = {
        "schema_version": "epistemic_capsule_refutation_v1",
        "refutation_id": "sha256:" + ("0" * 64),
        "episode_id": episode_id,
        "tick_u64": int(tick_u64),
        "reason_code": str(reason),
        "detail": str(detail)[:16384],
    }
    return write_hashed_json(
        state_root / "epistemic" / "refutations",
        "epistemic_capsule_refutation_v1.json",
        payload,
        id_field="refutation_id",
    )[1:]


def _load_optional_pinned(
    *,
    root: Path,
    pack: dict[str, Any],
    rel_key: str,
    id_key: str,
    schema_name: str,
    id_field: str,
) -> dict[str, Any] | None:
    rel = str(pack.get(rel_key, "")).strip()
    declared_id_raw = pack.get(id_key)
    if not rel and (declared_id_raw is None or str(declared_id_raw).strip() == ""):
        return None
    if not rel or declared_id_raw is None:
        raise RuntimeError("SCHEMA_FAIL")
    payload = load_canon_dict((root / rel).resolve())
    validate_schema(payload, schema_name)
    if str(pack.get(id_key, "")).strip() != verify_object_id(payload, id_field=id_field):
        raise RuntimeError("PIN_HASH_MISMATCH")
    return payload


def run(*, campaign_pack: Path, out_dir: Path) -> dict[str, Any]:
    ensure_disabled()
    pack = load_canon_dict(campaign_pack)
    validate_schema(pack, "rsi_epistemic_reduce_pack_v1")
    selector = dict(pack.get("episode_selector") or {})
    validate_schema(selector, "epistemic_episode_selector_v1")
    accepted_mob_schema_versions_raw = pack.get("accepted_mob_schema_versions")
    if accepted_mob_schema_versions_raw is None:
        accepted_mob_schema_versions = ["epistemic_model_output_v1"]
    elif isinstance(accepted_mob_schema_versions_raw, list):
        accepted_mob_schema_versions = [str(row).strip() for row in accepted_mob_schema_versions_raw if str(row).strip()]
    else:
        raise RuntimeError("SCHEMA_FAIL")
    if not accepted_mob_schema_versions:
        raise RuntimeError("SCHEMA_FAIL")

    reduce_contract_rel = str(pack.get("reduce_contract_rel", "")).strip()
    instruction_strip_contract_rel = str(pack.get("instruction_strip_contract_rel", "")).strip()
    confidence_calibration_rel = str(pack.get("confidence_calibration_rel", "")).strip()
    if not reduce_contract_rel or not instruction_strip_contract_rel or not confidence_calibration_rel:
        raise RuntimeError("SCHEMA_FAIL")

    root = repo_root()
    reduce_contract = load_canon_dict((root / reduce_contract_rel).resolve())
    instruction_strip_contract = load_canon_dict((root / instruction_strip_contract_rel).resolve())
    confidence_calibration = load_canon_dict((root / confidence_calibration_rel).resolve())
    validate_schema(reduce_contract, "epistemic_reduce_contract_v1")
    validate_schema(instruction_strip_contract, "epistemic_instruction_strip_contract_v1")
    validate_schema(confidence_calibration, "epistemic_confidence_calibration_v1")

    if str(pack.get("reduce_contract_id", "")).strip() != verify_object_id(reduce_contract, id_field="contract_id"):
        raise RuntimeError("PIN_HASH_MISMATCH")
    if str(pack.get("instruction_strip_contract_id", "")).strip() != verify_object_id(instruction_strip_contract, id_field="contract_id"):
        raise RuntimeError("PIN_HASH_MISMATCH")
    if str(pack.get("confidence_calibration_id", "")).strip() != verify_object_id(confidence_calibration, id_field="calibration_id"):
        raise RuntimeError("PIN_HASH_MISMATCH")
    if ensure_sha256(reduce_contract.get("instruction_strip_contract_id"), reason="SCHEMA_FAIL") != ensure_sha256(
        instruction_strip_contract.get("contract_id"),
        reason="SCHEMA_FAIL",
    ):
        raise RuntimeError("PIN_HASH_MISMATCH")

    outbox_root = (root / str(pack.get("outbox_root_rel", ""))).resolve()
    sip_profile = dict(pack.get("sip_profile") or {})
    sip_budget_spec = dict(pack.get("sip_budget_spec") or {})
    cert_gate_mode = str(pack.get("cert_gate_mode", "WARN")).strip().upper()
    if cert_gate_mode not in {"OFF", "WARN", "ENFORCE"}:
        raise RuntimeError("SCHEMA_FAIL")

    type_registry = _load_optional_pinned(
        root=root,
        pack=pack,
        rel_key="type_registry_rel",
        id_key="type_registry_id",
        schema_name="epistemic_type_registry_v1",
        id_field="registry_id",
    )
    parent_type_registry = _load_optional_pinned(
        root=root,
        pack=pack,
        rel_key="parent_type_registry_rel",
        id_key="parent_type_registry_id",
        schema_name="epistemic_type_registry_v1",
        id_field="registry_id",
    )
    retention_policy = _load_optional_pinned(
        root=root,
        pack=pack,
        rel_key="retention_policy_rel",
        id_key="retention_policy_id",
        schema_name="epistemic_retention_policy_v1",
        id_field="policy_id",
    )

    objective_profile_id: str | None = None
    objective_profile_id_raw = str(pack.get("objective_profile_id", "")).strip()
    objective_profile_rel = str(pack.get("objective_profile_rel", "")).strip()
    if objective_profile_id_raw:
        objective_profile_id = ensure_sha256(objective_profile_id_raw, reason="SCHEMA_FAIL")
    if objective_profile_rel:
        objective_payload = load_canon_dict((root / objective_profile_rel).resolve())
        observed = objective_payload.get("profile_id")
        if isinstance(observed, str) and observed.strip():
            observed_id = ensure_sha256(observed, reason="SCHEMA_FAIL")
        else:
            observed_id = canon_hash_obj(objective_payload)
        if objective_profile_id is None:
            objective_profile_id = observed_id
        elif objective_profile_id != observed_id:
            raise RuntimeError("PIN_HASH_MISMATCH")

    cert_profile = _load_optional_pinned(
        root=root,
        pack=pack,
        rel_key="cert_profile_rel",
        id_key="cert_profile_id",
        schema_name="epistemic_cert_profile_v1",
        id_field="cert_profile_id",
    )

    epistemic_kernel_spec: dict[str, Any] | None = None
    kernel_spec_rel = str(pack.get("epistemic_kernel_spec_rel", "")).strip()
    kernel_spec_id = str(pack.get("epistemic_kernel_spec_id", "")).strip()
    if kernel_spec_rel or kernel_spec_id:
        if not kernel_spec_rel or not kernel_spec_id:
            raise RuntimeError("SCHEMA_FAIL")
        epistemic_kernel_spec = load_canon_dict((root / kernel_spec_rel).resolve())
        validate_schema(epistemic_kernel_spec, "epistemic_kernel_spec_v1")
        if str(kernel_spec_id) != verify_object_id(epistemic_kernel_spec, id_field="kernel_spec_id"):
            raise RuntimeError("PIN_HASH_MISMATCH")

    state_root = out_dir.resolve() / "daemon" / "rsi_epistemic_reduce_v1" / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    tick_u64 = _tick_from_env()
    try:
        bundle = build_epistemic_capsule(
            tick_u64=tick_u64,
            outbox_root=outbox_root,
            selector=selector,
            accepted_mob_schema_versions=accepted_mob_schema_versions,
            reduce_contract=reduce_contract,
            instruction_strip_contract=instruction_strip_contract,
            confidence_calibration=confidence_calibration,
            sip_profile=sip_profile,
            sip_budget_spec=sip_budget_spec,
            type_registry=type_registry,
            parent_type_registry=parent_type_registry,
            objective_profile_id=objective_profile_id,
            cert_profile=cert_profile,
            cert_gate_mode=cert_gate_mode,
            retention_policy=retention_policy,
            sampling_seed_u64=int(tick_u64),
            epistemic_kernel_spec=epistemic_kernel_spec,
        )
        paths = write_capsule_bundle(state_root=state_root, bundle=bundle)
        out = {
            "status": "OK",
            "capsule_hash": paths["capsule_hash"],
            "world_snapshot_hash": paths["world_snapshot_hash"],
            "sip_receipt_hash": paths["sip_receipt_hash"],
        }
        for key in (
            "type_registry_hash",
            "type_binding_hash",
            "epistemic_ecac_hash",
            "epistemic_eufc_hash",
            "retention_deletion_plan_hash",
            "retention_sampling_manifest_hash",
            "retention_summary_proof_hash",
            "epistemic_kernel_spec_hash",
        ):
            if paths.get(key) is not None:
                out[key] = paths.get(key)
        return out
    except Exception as exc:  # noqa: BLE001
        reason = _reason_from_exc(exc)
        refutation, ref_hash = _write_refutation(
            state_root=state_root,
            tick_u64=tick_u64,
            selector=selector,
            reason=reason,
            detail=str(exc),
        )
        return {
            "status": "REFUTED",
            "reason_code": str(refutation.get("reason_code", reason)),
            "refutation_hash": ref_hash,
        }


def main() -> None:
    parser = argparse.ArgumentParser(prog="campaign_epistemic_reduce_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()

    result = run(campaign_pack=Path(args.campaign_pack), out_dir=Path(args.out_dir))
    print("OK")
    if result.get("status") == "REFUTED":
        print(f"REFUTED:{result.get('reason_code', 'UNKNOWN')}")


if __name__ == "__main__":
    main()
