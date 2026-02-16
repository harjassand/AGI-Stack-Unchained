from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json


def canon_hash(payload: Any) -> str:
    return sha256_prefixed(canon_bytes(payload))


def budget(policy: str = "SAFE_HALT", *, max_steps: int = 1000) -> dict[str, Any]:
    return {
        "schema_name": "budget_spec_v1",
        "schema_version": "v19_0",
        "max_steps": int(max_steps),
        "max_bytes_read": 10_000_000,
        "max_bytes_write": 10_000_000,
        "max_items": 10_000,
        "seed": 7,
        "policy": policy,
    }


def write_object(root: Path, relpath: str, payload: dict[str, Any], *, id_field: str | None = None) -> dict[str, str]:
    obj = dict(payload)
    if id_field is not None:
        no_id = dict(obj)
        no_id.pop(id_field, None)
        obj[id_field] = canon_hash(no_id)
    out = root / relpath
    out.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out, obj)
    return {
        "artifact_id": canon_hash(obj),
        "artifact_relpath": relpath,
    }


def make_regime(root: Path, *, accepted_artifact_ids: list[str], prefix: str) -> dict[str, Any]:
    c_ref = write_object(
        root,
        f"artifacts/{prefix}_C.json",
        {
            "checker_kind": "ENUMERATED_ACCEPT_SET",
            "accepted_artifact_ids": list(accepted_artifact_ids),
        },
    )
    k_ref = write_object(root, f"artifacts/{prefix}_K.json", {"kind": "K"})
    e_ref = write_object(root, f"artifacts/{prefix}_E.json", {"kind": "E"})
    w_ref = write_object(root, f"artifacts/{prefix}_W.json", {"kind": "W"})
    t_ref = write_object(root, f"artifacts/{prefix}_T.json", {"kind": "T"})
    return {"C": c_ref, "K": k_ref, "E": e_ref, "W": w_ref, "T": t_ref}


def make_overlap_profile(
    root: Path,
    *,
    refs: list[dict[str, str]],
    old_regime: dict[str, Any],
    new_regime: dict[str, Any],
    relpath: str = "artifacts/overlap.json",
) -> dict[str, str]:
    semantics_ref = write_object(
        root,
        "artifacts/overlap_semantics.json",
        {
            "schema_name": "local_overlap_semantics_profile_v1",
            "schema_version": "v19_0",
            "semantics_profile_id": "sha256:" + ("0" * 64),
            "semantics_kind": "LOCAL_ENUMERATED_ACCEPT_SET",
            "acceptance_checker_kind": "ENUMERATED_ACCEPT_SET",
        },
        id_field="semantics_profile_id",
    )
    payload = {
        "schema_name": "overlap_profile_v1",
        "schema_version": "v19_0",
        "can_version": "v1_7r",
        "overlap_profile_id": "sha256:" + ("0" * 64),
        "overlap_kind": "ENUMERATED_ACCEPT_SET",
        "declared_overlap_language": {
            "accepted_artifact_refs": refs,
        },
        "old_regime_ref": old_regime,
        "new_regime_ref": new_regime,
        "overlap_semantics_profile_ref": semantics_ref,
    }
    return write_object(root, relpath, payload, id_field="overlap_profile_id")


def make_translator_bundle(
    root: Path,
    *,
    ops: list[dict[str, Any]],
    relpath: str = "artifacts/translator.json",
) -> dict[str, str]:
    payload = {
        "schema_name": "translator_bundle_v1",
        "schema_version": "v19_0",
        "translator_bundle_id": "sha256:" + ("0" * 64),
        "translator_ir_kind": "JSON_PATCH_OPS_V1",
        "translator_ir": ops,
        "translator_domain": "ARTIFACT_JSON",
        "termination_profile": {"max_ops": 64, "max_depth": 8},
    }
    return write_object(root, relpath, payload, id_field="translator_bundle_id")


def make_totality_cert(
    root: Path,
    *,
    overlap_ref: dict[str, str],
    translator_ref: dict[str, str],
    refs: list[dict[str, str]],
    relpath: str = "artifacts/totality.json",
) -> dict[str, str]:
    overlap_payload = load_canon_json(root / overlap_ref["artifact_relpath"])
    translator_payload = load_canon_json(root / translator_ref["artifact_relpath"])
    overlap_profile_id = str(overlap_payload["overlap_profile_id"])
    translator_bundle_id = str(translator_payload["translator_bundle_id"])

    cert_budget = budget()
    rows = []
    for ref in refs:
        rows.append(
            {
                "input_artifact_id": ref["artifact_id"],
                "status": "OK",
                "output_artifact_id": ref["artifact_id"],
            }
        )
    payload = {
        "schema_name": "translator_totality_cert_v1",
        "schema_version": "v19_0",
        "cert_id": "sha256:" + ("0" * 64),
        "overlap_profile_id": overlap_profile_id,
        "translator_bundle_id": translator_bundle_id,
        "budget_spec_id": canon_hash(cert_budget),
        "budget_spec": cert_budget,
        "results": rows,
    }
    return write_object(root, relpath, payload, id_field="cert_id")


def make_backrefute_cert(
    root: Path,
    *,
    old_regime: dict[str, Any],
    target_ref: dict[str, str],
    result: str,
    relpath: str,
) -> dict[str, str]:
    witness = write_object(root, f"{relpath}.witness.json", {"witness": "ok"})
    checker = write_object(root, f"{relpath}.checker.json", {"checker": "old"})
    payload = {
        "schema_name": "backrefute_cert_v1",
        "schema_version": "v19_0",
        "cert_id": "sha256:" + ("0" * 64),
        "old_regime_ref": old_regime,
        "target_old_artifact_ref": target_ref,
        "refutation_witness_ref": witness,
        "old_semantics_checker_ref": checker,
        "budget": budget(),
        "result": result,
        "reason_code": "UNIT_TEST",
    }
    return write_object(root, relpath, payload, id_field="cert_id")


def make_morphism(
    root: Path,
    *,
    overlap_ref: dict[str, str],
    translator_ref: dict[str, str],
    totality_ref: dict[str, str] | None,
    old_regime: dict[str, Any],
    new_regime: dict[str, Any],
    backrefute_refs: list[dict[str, str]] | None = None,
    relpath: str = "artifacts/morphism.json",
) -> dict[str, str]:
    payload = {
        "schema_name": "continuity_morphism_v1",
        "schema_version": "v19_0",
        "morphism_id": "sha256:" + ("0" * 64),
        "morphism_type": "M_H",
        "continuity_class": "EXTEND",
        "overlap_profile_ref": overlap_ref,
        "translator_bundle_ref": translator_ref,
        "optional_projection_ref": None,
        "backrefute_policy": {
            "required": True,
            "allowed_outcomes": ["VALID", "INVALID", "BUDGET_EXHAUSTED"],
            "budget": budget(),
            "policy_on_missing_backrefute": "SAFE_HALT",
        },
        "required_proofs": [
            "TRANSLATOR_TOTALITY",
            "CONTINUITY_CHECK",
            "BACKREFUTE_LANE",
            "NO_NEW_ACCEPT_PATH",
            "REPLAY_DETERMINISM",
            "J_DOMINANCE_RENT_PAID",
        ],
        "budgets": {
            "continuity_budget": budget(),
            "translator_budget": budget(),
            "receipt_translation_budget": budget(),
            "totality_budget": budget(),
        },
        "declared_old_regime_ref": old_regime,
        "declared_new_regime_ref": new_regime,
        "translator_totality_cert_ref": totality_ref,
        "continuity_receipt_ref": None,
        "backrefute_cert_refs": backrefute_refs or [],
        "explicit_overlap_exceptions": [],
    }
    return write_object(root, relpath, payload, id_field="morphism_id")


def make_j_profile(root: Path, relpath: str = "artifacts/objective_profile.json") -> dict[str, str]:
    inv_kernel = write_object(root, "artifacts/inv_kernel.json", {"mode": "COUNT"})
    schedule = write_object(root, "artifacts/schedule.json", {"entries": [{"cost_u64": 3}, {"cost_u64": 4}]})
    payload = {
        "schema_name": "objective_J_profile_v1",
        "schema_version": "v19_0",
        "profile_id": "sha256:" + ("0" * 64),
        "enabled_terms": ["UDC_BASE", "INV", "TDL"],
        "weights": {
            "lambda": 1,
            "mu": 0,
            "nu": 1,
            "alpha": 1,
            "beta": 0,
            "gamma": 0,
            "delta": 0,
            "eta": 0,
        },
        "epsilon": 1,
        "amortization_horizons": {"TDL": 1, "CDL": 1, "CoDL": 1, "KDL": 1, "EDL": 1, "IDL": 1},
        "measurement_kernels": {
            "INV": inv_kernel,
        },
        "udc_schedule_ref": schedule,
        "meta_schedule_ref": None,
        "debt_sources": {
            "TDL": [schedule],
        },
    }
    return write_object(root, relpath, payload, id_field="profile_id")
