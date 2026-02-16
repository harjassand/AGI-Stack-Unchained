"""Treaty checker for v19.0 federation portability."""

from __future__ import annotations

import copy
from typing import Any, Callable

from ..common_v1 import (
    BudgetExhausted,
    BudgetMeter,
    budget_outcome,
    canon_hash_obj,
    ensure_sha256,
    require_budget_spec,
    validate_schema,
    verify_object_id,
)
from .check_ok_overlap_signature_v1 import check_ok_overlap_signature
from .check_refutation_interop_v1 import check_refutation_interop
from .ok_ican_v1 import ican_id


T_AXIS_MORPHISM_TYPE = "M_T"


def _decode_json_pointer(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise KeyError("json-pointer")
    out = []
    for token in pointer[1:].split("/"):
        out.append(token.replace("~1", "/").replace("~0", "~"))
    return out


def _resolve_parent(doc: Any, pointer: str) -> tuple[Any, str | int]:
    tokens = _decode_json_pointer(pointer)
    if not tokens:
        return None, ""
    cur = doc
    for token in tokens[:-1]:
        if isinstance(cur, list):
            cur = cur[int(token)]
        elif isinstance(cur, dict):
            cur = cur[token]
        else:
            raise KeyError("json-pointer")
    leaf = tokens[-1]
    if isinstance(cur, list):
        if leaf == "-":
            return cur, len(cur)
        return cur, int(leaf)
    if isinstance(cur, dict):
        return cur, leaf
    raise KeyError("json-pointer")


def _get_value(doc: Any, pointer: str) -> Any:
    tokens = _decode_json_pointer(pointer)
    cur = doc
    for token in tokens:
        if isinstance(cur, list):
            cur = cur[int(token)]
        elif isinstance(cur, dict):
            cur = cur[token]
        else:
            raise KeyError("json-pointer")
    return cur


def _set_value(doc: Any, pointer: str, value: Any, *, replace: bool) -> Any:
    parent, key = _resolve_parent(doc, pointer)
    if parent is None:
        return copy.deepcopy(value)
    if isinstance(parent, list):
        idx = int(key)
        if replace:
            parent[idx] = copy.deepcopy(value)
        else:
            if idx < 0 or idx > len(parent):
                raise KeyError("json-pointer")
            parent.insert(idx, copy.deepcopy(value))
        return doc
    if isinstance(parent, dict):
        if replace and key not in parent:
            raise KeyError("json-pointer")
        parent[str(key)] = copy.deepcopy(value)
        return doc
    raise KeyError("json-pointer")


def _remove_value(doc: Any, pointer: str) -> Any:
    parent, key = _resolve_parent(doc, pointer)
    if parent is None:
        raise KeyError("json-pointer")
    if isinstance(parent, list):
        del parent[int(key)]
        return doc
    if isinstance(parent, dict):
        del parent[str(key)]
        return doc
    raise KeyError("json-pointer")


def _depth(value: Any) -> int:
    if isinstance(value, dict):
        if not value:
            return 1
        return 1 + max(_depth(item) for item in value.values())
    if isinstance(value, list):
        if not value:
            return 1
        return 1 + max(_depth(item) for item in value)
    return 1


def _validate_translator_bundle_local(translator_bundle: dict[str, Any]) -> None:
    if not isinstance(translator_bundle, dict):
        raise ValueError("SCHEMA_FAIL")
    if str(translator_bundle.get("schema_name", "")).strip() != "translator_bundle_v1":
        raise ValueError("SCHEMA_FAIL")
    if str(translator_bundle.get("schema_version", "")).strip() != "v19_0":
        raise ValueError("SCHEMA_FAIL")
    verify_object_id(translator_bundle, id_field="translator_bundle_id")

    domain = str(translator_bundle.get("translator_domain", "")).strip()
    if domain not in {"OVERLAP_OK_IR", "RECEIPT_JSON"}:
        raise ValueError("SCHEMA_FAIL")

    ir = translator_bundle.get("translator_ir")
    if not isinstance(ir, list):
        raise ValueError("SCHEMA_FAIL")
    for op in ir:
        if not isinstance(op, dict):
            raise ValueError("SCHEMA_FAIL")
        if not isinstance(op.get("op"), str):
            raise ValueError("SCHEMA_FAIL")

    term = translator_bundle.get("termination_profile")
    if not isinstance(term, dict):
        raise ValueError("SCHEMA_FAIL")
    max_ops = term.get("max_ops")
    max_depth = term.get("max_depth")
    if not isinstance(max_ops, int) or max_ops < 0:
        raise ValueError("SCHEMA_FAIL")
    if not isinstance(max_depth, int) or max_depth < 1:
        raise ValueError("SCHEMA_FAIL")


def apply_translator_bundle(
    *,
    translator_bundle: dict[str, Any],
    source_obj: Any,
    meter: BudgetMeter,
) -> tuple[bool, Any | None, str | None]:
    try:
        _validate_translator_bundle_local(translator_bundle)
    except ValueError:
        return False, None, "SCHEMA_FAIL"

    if str(translator_bundle.get("translator_ir_kind", "")).strip() != "JSON_PATCH_OPS_V1":
        return False, None, "UNSUPPORTED_TRANSLATOR_IR"

    ir = translator_bundle.get("translator_ir")
    if not isinstance(ir, list):
        return False, None, "SCHEMA_FAIL"

    term = translator_bundle.get("termination_profile")
    if not isinstance(term, dict):
        return False, None, "SCHEMA_FAIL"
    max_ops = int(term.get("max_ops", 0))
    max_depth = int(term.get("max_depth", 0))
    if max_ops < 0 or max_depth < 1:
        return False, None, "SCHEMA_FAIL"

    if len(ir) > max_ops:
        return False, None, "TRANSLATOR_MAX_OPS_EXCEEDED"

    doc = copy.deepcopy(source_obj)
    op_index = 0
    while op_index < len(ir):
        meter.consume(steps=1, items=1)
        op = ir[op_index]
        if not isinstance(op, dict):
            return False, None, "SCHEMA_FAIL"
        kind = str(op.get("op", "")).strip()
        try:
            if kind == "ADD":
                doc = _set_value(doc, str(op["path"]), op.get("value"), replace=False)
            elif kind == "REMOVE":
                doc = _remove_value(doc, str(op["path"]))
            elif kind == "REPLACE":
                doc = _set_value(doc, str(op["path"]), op.get("value"), replace=True)
            elif kind == "MOVE":
                moved = _get_value(doc, str(op["from_path"]))
                doc = _remove_value(doc, str(op["from_path"]))
                doc = _set_value(doc, str(op["to_path"]), moved, replace=False)
            elif kind == "COPY":
                copied = _get_value(doc, str(op["from_path"]))
                doc = _set_value(doc, str(op["to_path"]), copied, replace=False)
            elif kind == "TEST":
                if _get_value(doc, str(op["path"])) != op.get("value"):
                    return False, None, "TEST_FAILED"
            else:
                return False, None, "SCHEMA_FAIL"
        except (KeyError, ValueError, IndexError):
            return False, None, "POINTER_ERROR"
        op_index += 1

    if _depth(doc) > max_depth:
        return False, None, "MAX_DEPTH_EXCEEDED"

    return True, doc, None


def _build_totality_cert(
    *,
    overlap_profile_id: str,
    translator_bundle_id: str,
    budget_spec: dict[str, Any],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "schema_name": "translator_totality_cert_v1",
        "schema_version": "v19_0",
        "overlap_profile_id": overlap_profile_id,
        "translator_bundle_id": translator_bundle_id,
        "budget_spec_id": canon_hash_obj(budget_spec),
        "budget_spec": dict(budget_spec),
        "results": results,
    }
    out = dict(payload)
    out["cert_id"] = canon_hash_obj(payload)
    if str(out.get("schema_name", "")).strip() != "translator_totality_cert_v1":
        raise ValueError("SCHEMA_FAIL")
    if str(out.get("schema_version", "")).strip() != "v19_0":
        raise ValueError("SCHEMA_FAIL")
    ensure_sha256(out.get("overlap_profile_id"), reason="SCHEMA_FAIL")
    ensure_sha256(out.get("translator_bundle_id"), reason="SCHEMA_FAIL")
    ensure_sha256(out.get("budget_spec_id"), reason="SCHEMA_FAIL")
    if not isinstance(out.get("budget_spec"), dict):
        raise ValueError("SCHEMA_FAIL")
    if not isinstance(out.get("results"), list):
        raise ValueError("SCHEMA_FAIL")
    for row in out["results"]:
        if not isinstance(row, dict):
            raise ValueError("SCHEMA_FAIL")
        ensure_sha256(row.get("input_artifact_id"), reason="SCHEMA_FAIL")
        status = str(row.get("status", "")).strip()
        if status not in {"OK", "FAIL", "BUDGET_EXHAUSTED"}:
            raise ValueError("SCHEMA_FAIL")
        output_id = row.get("output_artifact_id")
        if output_id is not None:
            ensure_sha256(output_id, reason="SCHEMA_FAIL")
        failure_reason = row.get("failure_reason_code")
        if failure_reason is not None and not isinstance(failure_reason, str):
            raise ValueError("SCHEMA_FAIL")
    verify_object_id(out, id_field="cert_id")
    return out


def _empty_totality_cert(
    *,
    overlap_profile_id: str,
    translator_bundle_id: str,
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    return _build_totality_cert(
        overlap_profile_id=overlap_profile_id,
        translator_bundle_id=translator_bundle_id,
        budget_spec=budget_spec,
        results=[],
    )


def _build_receipt(
    *,
    treaty_id: str,
    outcome: str,
    reason_code: str,
    phi_totality_cert: dict[str, Any],
    psi_totality_cert: dict[str, Any],
    refutation_receipts: list[dict[str, Any]],
    translated_ids_by_input_id: dict[str, str],
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_name": "treaty_check_receipt_v1",
        "schema_version": "v19_0",
        "treaty_id": treaty_id,
        "outcome": outcome,
        "reason_code": reason_code,
        "phi_totality_cert": phi_totality_cert,
        "psi_totality_cert": psi_totality_cert,
        "refutation_receipts": refutation_receipts,
        "translated_ids_by_input_id": translated_ids_by_input_id,
        "budget_spec": dict(budget_spec),
    }
    out = dict(payload)
    out["receipt_id"] = canon_hash_obj(payload)
    return out


def _safe_check(checker: Callable[[Any], bool], obj: Any) -> bool:
    try:
        return bool(checker(obj))
    except Exception:  # noqa: BLE001
        return False


def _validate_overlap_subset_decl(
    *,
    treaty: dict[str, Any],
    ok_signature: dict[str, Any],
) -> bool:
    subset = treaty.get("overlap_subset_decl")
    if not isinstance(subset, dict):
        return False
    kinds = subset.get("kinds")
    schema_ids = subset.get("schema_ids")
    if not isinstance(kinds, list) or not isinstance(schema_ids, list):
        return False

    supported = ok_signature.get("supported_kinds")
    if not isinstance(supported, list):
        return False
    supported_kind_set: set[str] = set()
    supported_schema_id_set: set[str] = set()
    for row in supported:
        if not isinstance(row, dict):
            return False
        kind = str(row.get("kind", "")).strip()
        schema_id = ensure_sha256(row.get("schema_id"), reason="SCHEMA_FAIL")
        if not kind:
            return False
        supported_kind_set.add(kind)
        supported_schema_id_set.add(schema_id)

    for kind in kinds:
        if not isinstance(kind, str) or kind not in supported_kind_set:
            return False
    for schema_id in schema_ids:
        if ensure_sha256(schema_id, reason="SCHEMA_FAIL") not in supported_schema_id_set:
            return False
    return True


def check_treaty(
    *,
    treaty: dict[str, Any],
    artifact_store: dict[str, Any],
    overlap_objects_by_id: dict[str, Any],
    witnesses_by_input_id: dict[str, dict[str, Any]] | None,
    source_checker: Callable[[Any], bool] | None,
    target_checker: Callable[[Any], bool] | None,
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    budget = require_budget_spec(budget_spec)
    meter = BudgetMeter(budget)

    validate_schema(treaty, "treaty_v1")
    treaty_id = verify_object_id(treaty, id_field="treaty_id")

    source_ok = source_checker or (lambda _obj: True)
    target_ok = target_checker or (lambda _obj: True)

    try:
        meter.consume(steps=1, items=1)

        ok_signature_id = ensure_sha256(treaty.get("ok_overlap_signature_ref"), reason="SCHEMA_FAIL")
        ok_signature = artifact_store.get(ok_signature_id)
        if not isinstance(ok_signature, dict):
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="SAFE_HALT",
                reason_code="MISSING_OK_SIGNATURE",
                phi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                psi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                refutation_receipts=[],
                translated_ids_by_input_id={},
                budget_spec=budget,
            )

        ok_sig_receipt = check_ok_overlap_signature(signature=ok_signature, budget_spec=budget)
        if ok_sig_receipt.get("outcome") != "ACCEPT":
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="SAFE_HALT",
                reason_code="INVALID_OK_SIGNATURE",
                phi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                psi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                refutation_receipts=[],
                translated_ids_by_input_id={},
                budget_spec=budget,
            )

        if not _validate_overlap_subset_decl(treaty=treaty, ok_signature=ok_signature):
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="SAFE_HALT",
                reason_code="SUBSET_DECL_MISMATCH",
                phi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                psi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                refutation_receipts=[],
                translated_ids_by_input_id={},
                budget_spec=budget,
            )

        dispute_rule = treaty.get("dispute_rule")
        if not isinstance(dispute_rule, dict):
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="SAFE_HALT",
                reason_code="SCHEMA_FAIL",
                phi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                psi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                refutation_receipts=[],
                translated_ids_by_input_id={},
                budget_spec=budget,
            )
        dispute_budget = dispute_rule.get("budgets")
        if not isinstance(dispute_budget, dict):
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="SAFE_HALT",
                reason_code="MISSING_BUDGET",
                phi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                psi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                refutation_receipts=[],
                translated_ids_by_input_id={},
                budget_spec=budget,
            )
        dispute_budget = require_budget_spec(dispute_budget)
        if canon_hash_obj(dispute_budget) != canon_hash_obj(budget):
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="SAFE_HALT",
                reason_code="BUDGET_MISMATCH",
                phi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                psi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                refutation_receipts=[],
                translated_ids_by_input_id={},
                budget_spec=budget,
            )

        ican_profile_id = ensure_sha256(ok_signature.get("ican_profile_id"), reason="SCHEMA_FAIL")

        phi_ref = treaty.get("phi_translator_bundle_ref")
        psi_ref = treaty.get("psi_refutation_translator_bundle_ref")
        if not isinstance(phi_ref, dict) or not isinstance(psi_ref, dict):
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="SAFE_HALT",
                reason_code="SCHEMA_FAIL",
                phi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                psi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id="sha256:" + ("0" * 64),
                    budget_spec=budget,
                ),
                refutation_receipts=[],
                translated_ids_by_input_id={},
                budget_spec=budget,
            )

        phi_bundle_id = ensure_sha256(phi_ref.get("bundle_id"), reason="SCHEMA_FAIL")
        psi_bundle_id = ensure_sha256(psi_ref.get("bundle_id"), reason="SCHEMA_FAIL")
        phi_bundle = artifact_store.get(phi_bundle_id)
        psi_bundle = artifact_store.get(psi_bundle_id)
        if not isinstance(phi_bundle, dict) or not isinstance(psi_bundle, dict):
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="SAFE_HALT",
                reason_code="MISSING_TRANSLATOR_BUNDLE",
                phi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id=phi_bundle_id,
                    budget_spec=budget,
                ),
                psi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id=psi_bundle_id,
                    budget_spec=budget,
                ),
                refutation_receipts=[],
                translated_ids_by_input_id={},
                budget_spec=budget,
            )
        if str(phi_ref.get("translator_domain", "")).strip() != str(phi_bundle.get("translator_domain", "")).strip():
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="SAFE_HALT",
                reason_code="TRANSLATOR_DOMAIN_MISMATCH",
                phi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id=phi_bundle_id,
                    budget_spec=budget,
                ),
                psi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id=psi_bundle_id,
                    budget_spec=budget,
                ),
                refutation_receipts=[],
                translated_ids_by_input_id={},
                budget_spec=budget,
            )
        if str(psi_ref.get("translator_domain", "")).strip() != str(psi_bundle.get("translator_domain", "")).strip():
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="SAFE_HALT",
                reason_code="TRANSLATOR_DOMAIN_MISMATCH",
                phi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id=phi_bundle_id,
                    budget_spec=budget,
                ),
                psi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id=psi_bundle_id,
                    budget_spec=budget,
                ),
                refutation_receipts=[],
                translated_ids_by_input_id={},
                budget_spec=budget,
            )

        overlap_ids_raw = treaty.get("overlap_test_set_ids")
        if not isinstance(overlap_ids_raw, list) or not overlap_ids_raw:
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="SAFE_HALT",
                reason_code="SCHEMA_FAIL",
                phi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id=phi_bundle_id,
                    budget_spec=budget,
                ),
                psi_totality_cert=_empty_totality_cert(
                    overlap_profile_id=ok_signature_id,
                    translator_bundle_id=psi_bundle_id,
                    budget_spec=budget,
                ),
                refutation_receipts=[],
                translated_ids_by_input_id={},
                budget_spec=budget,
            )

        overlap_ids = sorted(ensure_sha256(value, reason="SCHEMA_FAIL") for value in overlap_ids_raw)
        witnesses = witnesses_by_input_id or {}

        phi_results: list[dict[str, Any]] = []
        psi_results: list[dict[str, Any]] = []
        refutation_receipts: list[dict[str, Any]] = []
        translated_ids_by_input_id: dict[str, str] = {}
        translated_objects_by_input_id: dict[str, Any] = {}

        for overlap_id in overlap_ids:
            meter.consume(steps=1, items=1)
            overlap_obj = overlap_objects_by_id.get(overlap_id)
            if overlap_obj is None:
                phi_results.append(
                    {
                        "input_artifact_id": overlap_id,
                        "status": "FAIL",
                        "failure_reason_code": "MISSING_OVERLAP_OBJECT",
                    }
                )
                psi_results.append(
                    {
                        "input_artifact_id": overlap_id,
                        "status": "FAIL",
                        "failure_reason_code": "MISSING_OVERLAP_OBJECT",
                    }
                )
                continue

            if ican_id(overlap_obj, ican_profile_id) != overlap_id:
                phi_results.append(
                    {
                        "input_artifact_id": overlap_id,
                        "status": "FAIL",
                        "failure_reason_code": "OVERLAP_ID_MISMATCH",
                    }
                )
                psi_results.append(
                    {
                        "input_artifact_id": overlap_id,
                        "status": "FAIL",
                        "failure_reason_code": "OVERLAP_ID_MISMATCH",
                    }
                )
                continue

            phi_ok, phi_out, phi_reason = apply_translator_bundle(
                translator_bundle=phi_bundle,
                source_obj=overlap_obj,
                meter=meter,
            )
            if phi_ok:
                translated_id = ican_id(phi_out, ican_profile_id)
                translated_ids_by_input_id[overlap_id] = translated_id
                translated_objects_by_input_id[overlap_id] = phi_out
                phi_results.append(
                    {
                        "input_artifact_id": overlap_id,
                        "status": "OK",
                        "output_artifact_id": translated_id,
                    }
                )
            else:
                phi_results.append(
                    {
                        "input_artifact_id": overlap_id,
                        "status": "FAIL",
                        "failure_reason_code": str(phi_reason or "TRANSLATOR_FAILURE"),
                    }
                )

            psi_ok, psi_out, psi_reason = apply_translator_bundle(
                translator_bundle=psi_bundle,
                source_obj=overlap_obj,
                meter=meter,
            )
            if psi_ok:
                psi_results.append(
                    {
                        "input_artifact_id": overlap_id,
                        "status": "OK",
                        "output_artifact_id": ican_id(psi_out, ican_profile_id),
                    }
                )
            else:
                psi_results.append(
                    {
                        "input_artifact_id": overlap_id,
                        "status": "FAIL",
                        "failure_reason_code": str(psi_reason or "TRANSLATOR_FAILURE"),
                    }
                )

        phi_totality = _build_totality_cert(
            overlap_profile_id=ok_signature_id,
            translator_bundle_id=phi_bundle_id,
            budget_spec=budget,
            results=phi_results,
        )
        psi_totality = _build_totality_cert(
            overlap_profile_id=ok_signature_id,
            translator_bundle_id=psi_bundle_id,
            budget_spec=budget,
            results=psi_results,
        )

        totality_fail = any(row.get("status") != "OK" for row in phi_results + psi_results)
        if totality_fail:
            policy = str(((treaty.get("dispute_rule") or {}).get("budgets") or {}).get("policy", "SAFE_SPLIT"))
            outcome = "SAFE_SPLIT" if policy == "SAFE_SPLIT" else "SAFE_HALT"
            return _build_receipt(
                treaty_id=treaty_id,
                outcome=outcome,
                reason_code="TRANSLATOR_NON_TOTAL",
                phi_totality_cert=phi_totality,
                psi_totality_cert=psi_totality,
                refutation_receipts=[],
                translated_ids_by_input_id=translated_ids_by_input_id,
                budget_spec=budget,
            )

        any_safe_split = False
        any_reject = False
        no_new_accept_path = False
        for overlap_id in overlap_ids:
            overlap_obj = overlap_objects_by_id[overlap_id]
            translated_obj = translated_objects_by_input_id.get(overlap_id)
            source_accepts = _safe_check(source_ok, overlap_obj)
            target_accepts = _safe_check(target_ok, translated_obj)
            if (not source_accepts) and target_accepts:
                no_new_accept_path = True
            witness = witnesses.get(overlap_id)
            ref_receipt = check_refutation_interop(
                treaty=treaty,
                input_overlap_object=overlap_obj,
                translated_object=translated_obj,
                target_accepts_translated=target_accepts,
                witness=witness,
                artifact_store=artifact_store,
                ican_profile_id=ican_profile_id,
                budget_spec=budget,
            )
            refutation_receipts.append(ref_receipt)
            if ref_receipt.get("outcome") == "SAFE_SPLIT":
                any_safe_split = True
            elif ref_receipt.get("outcome") == "REJECT":
                any_reject = True
            elif ref_receipt.get("outcome") == "SAFE_HALT":
                return _build_receipt(
                    treaty_id=treaty_id,
                    outcome="SAFE_HALT",
                    reason_code="REFUTATION_INTEROP_FAIL",
                    phi_totality_cert=phi_totality,
                    psi_totality_cert=psi_totality,
                    refutation_receipts=refutation_receipts,
                    translated_ids_by_input_id=translated_ids_by_input_id,
                    budget_spec=budget,
                )

        if no_new_accept_path:
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="SAFE_SPLIT",
                reason_code="NO_NEW_ACCEPTANCE_PATH",
                phi_totality_cert=phi_totality,
                psi_totality_cert=psi_totality,
                refutation_receipts=refutation_receipts,
                translated_ids_by_input_id=translated_ids_by_input_id,
                budget_spec=budget,
            )

        if any_safe_split:
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="SAFE_SPLIT",
                reason_code="DISPUTE_AMBIGUOUS",
                phi_totality_cert=phi_totality,
                psi_totality_cert=psi_totality,
                refutation_receipts=refutation_receipts,
                translated_ids_by_input_id=translated_ids_by_input_id,
                budget_spec=budget,
            )
        if any_reject:
            return _build_receipt(
                treaty_id=treaty_id,
                outcome="REJECT",
                reason_code="VALID_REFUTATION_PRESENT",
                phi_totality_cert=phi_totality,
                psi_totality_cert=psi_totality,
                refutation_receipts=refutation_receipts,
                translated_ids_by_input_id=translated_ids_by_input_id,
                budget_spec=budget,
            )

        return _build_receipt(
            treaty_id=treaty_id,
            outcome="ACCEPT",
            reason_code="TREATY_VALID",
            phi_totality_cert=phi_totality,
            psi_totality_cert=psi_totality,
            refutation_receipts=refutation_receipts,
            translated_ids_by_input_id=translated_ids_by_input_id,
            budget_spec=budget,
        )
    except BudgetExhausted:
        empty_totality = _empty_totality_cert(
            overlap_profile_id="sha256:" + ("0" * 64),
            translator_bundle_id="sha256:" + ("0" * 64),
            budget_spec=budget,
        )
        return _build_receipt(
            treaty_id=treaty_id,
            outcome=budget_outcome(budget["policy"], allow_safe_split=True),
            reason_code="BUDGET_EXHAUSTED",
            phi_totality_cert=empty_totality,
            psi_totality_cert=empty_totality,
            refutation_receipts=[],
            translated_ids_by_input_id={},
            budget_spec=budget,
        )


__all__ = ["T_AXIS_MORPHISM_TYPE", "apply_translator_bundle", "check_treaty"]
