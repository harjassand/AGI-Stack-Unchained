"""Universal continuity checker for v19 overlap semantics."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...v1_7r.canon import canon_bytes
from .check_backrefute_v1 import check_backrefute, index_backrefute_certs
from .common_v1 import (
    ContinuityV19Error,
    canonical_json_size,
    canon_hash_obj,
    fail,
    make_budget_tracker,
    sorted_by_canon,
    validate_schema,
    verify_declared_id,
)
from .loaders_v1 import ArtifactRef, BudgetBundleV1, RegimeRef, load_artifact_ref, load_budget_bundle, load_regime_ref


@dataclass
class TranslationResult:
    status: str
    output_payload: Any | None
    output_artifact_id: str | None
    reason: str | None


def _split_pointer(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        fail("TRANSLATOR_FAILURE", safe_halt=True)
    tokens: list[str] = []
    for row in pointer.split("/")[1:]:
        tokens.append(row.replace("~1", "/").replace("~0", "~"))
    return tokens


def _token_index(token: str, length: int, *, allow_end: bool = False) -> int:
    if token == "-" and allow_end:
        return length
    if not token.isdigit():
        fail("TRANSLATOR_FAILURE", safe_halt=True)
    idx = int(token)
    if idx < 0:
        fail("TRANSLATOR_FAILURE", safe_halt=True)
    return idx


def _resolve_parent(doc: Any, pointer: str) -> tuple[Any, str]:
    tokens = _split_pointer(pointer)
    if not tokens:
        fail("TRANSLATOR_FAILURE", safe_halt=True)
    parent_tokens = tokens[:-1]
    leaf = tokens[-1]
    node = doc
    for token in parent_tokens:
        if isinstance(node, dict):
            if token not in node:
                fail("TRANSLATOR_FAILURE", safe_halt=True)
            node = node[token]
        elif isinstance(node, list):
            idx = _token_index(token, len(node), allow_end=False)
            if idx >= len(node):
                fail("TRANSLATOR_FAILURE", safe_halt=True)
            node = node[idx]
        else:
            fail("TRANSLATOR_FAILURE", safe_halt=True)
    return node, leaf


def _get_value(doc: Any, pointer: str) -> Any:
    tokens = _split_pointer(pointer)
    node = doc
    for token in tokens:
        if isinstance(node, dict):
            if token not in node:
                fail("TRANSLATOR_FAILURE", safe_halt=True)
            node = node[token]
        elif isinstance(node, list):
            idx = _token_index(token, len(node), allow_end=False)
            if idx >= len(node):
                fail("TRANSLATOR_FAILURE", safe_halt=True)
            node = node[idx]
        else:
            fail("TRANSLATOR_FAILURE", safe_halt=True)
    return copy.deepcopy(node)


def _set_value(doc: Any, pointer: str, value: Any, *, create_only: bool = False, replace_only: bool = False) -> Any:
    if pointer == "":
        if create_only or replace_only:
            return copy.deepcopy(value)
        return copy.deepcopy(value)

    parent, leaf = _resolve_parent(doc, pointer)
    if isinstance(parent, dict):
        exists = leaf in parent
        if create_only and exists:
            fail("TRANSLATOR_FAILURE", safe_halt=True)
        if replace_only and not exists:
            fail("TRANSLATOR_FAILURE", safe_halt=True)
        parent[leaf] = copy.deepcopy(value)
        return doc

    if isinstance(parent, list):
        idx = _token_index(leaf, len(parent), allow_end=True)
        if create_only:
            if idx == len(parent):
                parent.append(copy.deepcopy(value))
            elif idx < len(parent):
                parent.insert(idx, copy.deepcopy(value))
            else:
                fail("TRANSLATOR_FAILURE", safe_halt=True)
            return doc
        if replace_only:
            if idx >= len(parent):
                fail("TRANSLATOR_FAILURE", safe_halt=True)
            parent[idx] = copy.deepcopy(value)
            return doc
        if idx == len(parent):
            parent.append(copy.deepcopy(value))
        elif idx < len(parent):
            parent[idx] = copy.deepcopy(value)
        else:
            fail("TRANSLATOR_FAILURE", safe_halt=True)
        return doc

    fail("TRANSLATOR_FAILURE", safe_halt=True)
    return doc


def _remove_value(doc: Any, pointer: str) -> Any:
    if pointer == "":
        fail("TRANSLATOR_FAILURE", safe_halt=True)
    parent, leaf = _resolve_parent(doc, pointer)
    if isinstance(parent, dict):
        if leaf not in parent:
            fail("TRANSLATOR_FAILURE", safe_halt=True)
        del parent[leaf]
        return doc
    if isinstance(parent, list):
        idx = _token_index(leaf, len(parent), allow_end=False)
        if idx >= len(parent):
            fail("TRANSLATOR_FAILURE", safe_halt=True)
        parent.pop(idx)
        return doc
    fail("TRANSLATOR_FAILURE", safe_halt=True)
    return doc


def _max_pointer_depth(op: dict[str, Any]) -> int:
    keys = ["path", "from_path", "to_path"]
    best = 0
    for key in keys:
        row = op.get(key)
        if isinstance(row, str):
            best = max(best, len(_split_pointer(row)))
    return best


def apply_translator_bundle(
    *,
    payload: Any,
    translator_bundle: dict[str, Any],
    tracker: Any,
) -> TranslationResult:
    if not isinstance(translator_bundle, dict):
        return TranslationResult(status="FAIL", output_payload=None, output_artifact_id=None, reason="SCHEMA_ERROR")
    validate_schema(translator_bundle, "translator_bundle_v1")
    verify_declared_id(translator_bundle, "translator_bundle_id")

    if str(translator_bundle.get("translator_ir_kind")) != "JSON_PATCH_OPS_V1":
        fail("TRANSLATOR_FAILURE", safe_halt=True)

    term = translator_bundle.get("termination_profile")
    if not isinstance(term, dict):
        fail("TRANSLATOR_FAILURE", safe_halt=True)
    max_ops = int(term.get("max_ops", -1))
    max_depth = int(term.get("max_depth", -1))
    if max_ops < 0 or max_depth < 1:
        fail("TRANSLATOR_FAILURE", safe_halt=True)

    ops = translator_bundle.get("translator_ir")
    if not isinstance(ops, list):
        fail("TRANSLATOR_FAILURE", safe_halt=True)
    if len(ops) > max_ops:
        fail("TRANSLATOR_FAILURE", safe_halt=True)

    doc = copy.deepcopy(payload)
    tracker.consume_items(1)
    tracker.consume_bytes_read(canonical_json_size(payload))

    for op in ops:
        tracker.consume_steps(1)
        if not isinstance(op, dict):
            fail("TRANSLATOR_FAILURE", safe_halt=True)
        if _max_pointer_depth(op) > max_depth:
            fail("TRANSLATOR_FAILURE", safe_halt=True)

        kind = str(op.get("op", "")).strip()
        if kind == "ADD":
            doc = _set_value(doc, str(op.get("path")), op.get("value"), create_only=True)
        elif kind == "REMOVE":
            doc = _remove_value(doc, str(op.get("path")))
        elif kind == "REPLACE":
            doc = _set_value(doc, str(op.get("path")), op.get("value"), replace_only=True)
        elif kind == "MOVE":
            value = _get_value(doc, str(op.get("from_path")))
            doc = _remove_value(doc, str(op.get("from_path")))
            doc = _set_value(doc, str(op.get("to_path")), value, create_only=True)
        elif kind == "COPY":
            value = _get_value(doc, str(op.get("from_path")))
            doc = _set_value(doc, str(op.get("to_path")), value, create_only=True)
        elif kind == "TEST":
            observed = _get_value(doc, str(op.get("path")))
            expected = op.get("value")
            if canon_bytes(observed) != canon_bytes(expected):
                fail("TRANSLATOR_FAILURE", safe_halt=True)
        else:
            fail("TRANSLATOR_FAILURE", safe_halt=True)

    artifact_id = canon_hash_obj(doc)
    tracker.consume_bytes_write(canonical_json_size(doc))
    return TranslationResult(status="OK", output_payload=doc, output_artifact_id=artifact_id, reason=None)


def _accept_under_regime_overlap(
    *,
    store_root: Path,
    regime_ref: RegimeRef,
    candidate_artifact_id: str,
    overlap_ids: set[str],
) -> bool:
    # Pinned acceptance checker is read from the constitution slot C.
    checker_artifact = load_artifact_ref(store_root, regime_ref["C"])
    payload = checker_artifact.payload
    if not isinstance(payload, dict):
        fail("SCHEMA_ERROR", safe_halt=True)

    checker_kind = str(payload.get("checker_kind", "ENUMERATED_ACCEPT_SET"))
    if checker_kind != "ENUMERATED_ACCEPT_SET":
        fail("SCHEMA_ERROR", safe_halt=True)

    accepted = payload.get("accepted_artifact_ids")
    if not isinstance(accepted, list):
        fail("SCHEMA_ERROR", safe_halt=True)

    accepted_set: set[str] = set()
    for row in accepted:
        accepted_set.add(str(row))

    # Overlap language in v1 is explicit; only overlap IDs participate in continuity check.
    if candidate_artifact_id not in overlap_ids and candidate_artifact_id not in accepted_set:
        return False
    return candidate_artifact_id in accepted_set


def _collect_overlap_artifact_refs(overlap_payload: dict[str, Any]) -> list[ArtifactRef]:
    language = overlap_payload.get("declared_overlap_language")
    if not isinstance(language, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    refs = language.get("accepted_artifact_refs")
    if not isinstance(refs, list):
        fail("SCHEMA_ERROR", safe_halt=True)
    out: list[ArtifactRef] = []
    for row in refs:
        if not isinstance(row, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        artifact_id = str(row.get("artifact_id", "")).strip()
        artifact_relpath = str(row.get("artifact_relpath", "")).strip()
        if not artifact_id or not artifact_relpath:
            fail("SCHEMA_ERROR", safe_halt=True)
        out.append(ArtifactRef(artifact_id=artifact_id, artifact_relpath=artifact_relpath))
    return out


def _collect_new_overlap_accept_set(
    *,
    store_root: Path,
    regime_ref: RegimeRef,
    overlap_ids: set[str],
    translated_preserved_set: set[str],
) -> set[str]:
    checker_artifact = load_artifact_ref(store_root, regime_ref["C"])
    payload = checker_artifact.payload
    if not isinstance(payload, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    accepted = payload.get("accepted_artifact_ids")
    if not isinstance(accepted, list):
        fail("SCHEMA_ERROR", safe_halt=True)
    accepted_set: set[str] = set()
    for row in accepted:
        if isinstance(row, str):
            if row in overlap_ids or row in translated_preserved_set:
                accepted_set.add(row)
    return accepted_set


def check_continuity(
    sigma_old_ref: ArtifactRef,
    sigma_new_ref: ArtifactRef,
    regime_old_ref: RegimeRef,
    regime_new_ref: RegimeRef,
    morphism_ref: ArtifactRef,
    budgets: BudgetBundleV1,
) -> dict[str, Any]:
    """Universal overlap continuity checker (Team 1 continuity core)."""

    store_root = Path(".").resolve()

    budget_bundle = load_budget_bundle(budgets)
    continuity_tracker = make_budget_tracker(budget_bundle["continuity_budget"])
    translator_tracker = make_budget_tracker(budget_bundle["translator_budget"])

    sigma_old = load_artifact_ref(store_root, sigma_old_ref)
    sigma_new = load_artifact_ref(store_root, sigma_new_ref)
    continuity_tracker.consume_bytes_read(sigma_old.canonical_size + sigma_new.canonical_size)

    normalized_old_regime, _loaded_old = load_regime_ref(store_root, regime_old_ref)
    normalized_new_regime, _loaded_new = load_regime_ref(store_root, regime_new_ref)

    morphism = load_artifact_ref(store_root, morphism_ref)
    continuity_tracker.consume_bytes_read(morphism.canonical_size)
    morphism_payload = morphism.payload
    if not isinstance(morphism_payload, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    validate_schema(morphism_payload, "continuity_morphism_v1")
    verify_declared_id(morphism_payload, "morphism_id")

    if morphism_payload.get("declared_old_regime_ref") != normalized_old_regime:
        fail("ID_MISMATCH", safe_halt=True)
    if morphism_payload.get("declared_new_regime_ref") != normalized_new_regime:
        fail("ID_MISMATCH", safe_halt=True)

    overlap_ref = morphism_payload.get("overlap_profile_ref")
    translator_ref = morphism_payload.get("translator_bundle_ref")
    if not isinstance(overlap_ref, dict) or not isinstance(translator_ref, dict):
        fail("SCHEMA_ERROR", safe_halt=True)

    overlap_artifact = load_artifact_ref(store_root, overlap_ref)
    translator_artifact = load_artifact_ref(store_root, translator_ref)
    continuity_tracker.consume_bytes_read(overlap_artifact.canonical_size + translator_artifact.canonical_size)

    overlap_payload = overlap_artifact.payload
    translator_payload = translator_artifact.payload
    if not isinstance(overlap_payload, dict) or not isinstance(translator_payload, dict):
        fail("SCHEMA_ERROR", safe_halt=True)

    validate_schema(overlap_payload, "overlap_profile_v1")
    verify_declared_id(overlap_payload, "overlap_profile_id")
    validate_schema(translator_payload, "translator_bundle_v1")
    verify_declared_id(translator_payload, "translator_bundle_id")
    if str(overlap_payload.get("can_version", "")) != "v1_7r":
        fail("SCHEMA_ERROR", safe_halt=True)

    if overlap_payload.get("old_regime_ref") != normalized_old_regime:
        fail("ID_MISMATCH", safe_halt=True)
    if overlap_payload.get("new_regime_ref") != normalized_new_regime:
        fail("ID_MISMATCH", safe_halt=True)

    if overlap_payload.get("overlap_kind") != "ENUMERATED_ACCEPT_SET":
        fail("SCHEMA_ERROR", safe_halt=True)

    semantics_ref = overlap_payload.get("overlap_semantics_profile_ref")
    if not isinstance(semantics_ref, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    semantics = load_artifact_ref(store_root, semantics_ref)
    continuity_tracker.consume_bytes_read(semantics.canonical_size)
    if not isinstance(semantics.payload, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    validate_schema(semantics.payload, "local_overlap_semantics_profile_v1")
    verify_declared_id(semantics.payload, "semantics_profile_id")
    if str(semantics.payload.get("semantics_kind", "")) != "LOCAL_ENUMERATED_ACCEPT_SET":
        fail("SCHEMA_ERROR", safe_halt=True)

    overlap_refs = sorted_by_canon(_collect_overlap_artifact_refs(overlap_payload))
    overlap_ids = {row["artifact_id"] for row in overlap_refs}

    backrefute_policy = morphism_payload.get("backrefute_policy")
    if not isinstance(backrefute_policy, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    if overlap_refs:
        if bool(backrefute_policy.get("required", False)) is not True:
            fail("SCHEMA_ERROR", safe_halt=True)
        if str(backrefute_policy.get("policy_on_missing_backrefute", "")) != "SAFE_HALT":
            fail("SCHEMA_ERROR", safe_halt=True)

    required_proofs = morphism_payload.get("required_proofs")
    if not isinstance(required_proofs, list):
        fail("SCHEMA_ERROR", safe_halt=True)
    required_proof_set = {str(row) for row in required_proofs}
    for required in (
        "TRANSLATOR_TOTALITY",
        "CONTINUITY_CHECK",
        "BACKREFUTE_LANE",
        "NO_NEW_ACCEPT_PATH",
        "REPLAY_DETERMINISM",
        "J_DOMINANCE_RENT_PAID",
    ):
        if required not in required_proof_set:
            fail("SCHEMA_ERROR", safe_halt=True)

    totality_ref = morphism_payload.get("translator_totality_cert_ref")
    if overlap_refs and not isinstance(totality_ref, dict):
        fail("MISSING_ARTIFACT", safe_halt=True)
    totality_id = "sha256:" + ("0" * 64)
    if isinstance(totality_ref, dict):
        totality_artifact = load_artifact_ref(store_root, totality_ref)
        if not isinstance(totality_artifact.payload, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        validate_schema(totality_artifact.payload, "translator_totality_cert_v1")
        verify_declared_id(totality_artifact.payload, "cert_id")
        if str(totality_artifact.payload.get("budget_spec_id", "")) != canon_hash_obj(totality_artifact.payload.get("budget_spec", {})):
            fail("ID_MISMATCH", safe_halt=True)
        if str(totality_artifact.payload.get("overlap_profile_id", "")) != str(overlap_payload.get("overlap_profile_id", "")):
            fail("ID_MISMATCH", safe_halt=True)
        if str(totality_artifact.payload.get("translator_bundle_id", "")) != str(translator_payload.get("translator_bundle_id", "")):
            fail("ID_MISMATCH", safe_halt=True)

        totality_results_raw = totality_artifact.payload.get("results")
        if not isinstance(totality_results_raw, list):
            fail("SCHEMA_ERROR", safe_halt=True)
        result_by_input: dict[str, str] = {}
        for row in totality_results_raw:
            if not isinstance(row, dict):
                fail("SCHEMA_ERROR", safe_halt=True)
            item_id = str(row.get("input_artifact_id", "")).strip()
            status = str(row.get("status", "")).strip()
            if not item_id:
                fail("SCHEMA_ERROR", safe_halt=True)
            if status == "OK":
                output_id = str(row.get("output_artifact_id", "")).strip()
                if not output_id.startswith("sha256:"):
                    fail("SCHEMA_ERROR", safe_halt=True)
            result_by_input[item_id] = status
        for overlap_ref_row in overlap_refs:
            status = result_by_input.get(overlap_ref_row["artifact_id"], "")
            if status != "OK":
                fail("CONTINUITY_FAILURE", safe_halt=True)
        totality_id = str(totality_artifact.payload.get("cert_id"))

    backrefute_refs = morphism_payload.get("backrefute_cert_refs")
    if backrefute_refs is None:
        backrefute_refs = []
    if not isinstance(backrefute_refs, list):
        fail("SCHEMA_ERROR", safe_halt=True)
    backrefute_index = index_backrefute_certs(store_root=store_root, cert_refs=backrefute_refs)

    items: list[dict[str, Any]] = []
    translated_preserved_set: set[str] = set()

    for item_ref in overlap_refs:
        continuity_tracker.consume_items(1)
        continuity_tracker.consume_steps(1)
        old_artifact = load_artifact_ref(store_root, item_ref)
        translation_acceptance = "SAFE_HALT"
        backrefute_status = "NOT_PROVIDED"
        final_item_outcome = "UNRESOLVED"
        translated_id: str | None = None

        try:
            translation = apply_translator_bundle(
                payload=old_artifact.payload,
                translator_bundle=translator_payload,
                tracker=translator_tracker,
            )
        except ContinuityV19Error:
            translation = TranslationResult(status="FAIL", output_payload=None, output_artifact_id=None, reason="TRANSLATOR_FAILURE")

        if translation.status == "OK" and translation.output_artifact_id is not None:
            translated_id = translation.output_artifact_id
            accepted = _accept_under_regime_overlap(
                store_root=store_root,
                regime_ref=normalized_new_regime,
                candidate_artifact_id=translated_id,
                overlap_ids=overlap_ids,
            )
            if accepted:
                translated_preserved_set.add(translated_id)
                translation_acceptance = "ACCEPT"
                final_item_outcome = "PRESERVED"
            else:
                translation_acceptance = "REJECT"

        if final_item_outcome != "PRESERVED":
            cert_ref = backrefute_index.get(item_ref["artifact_id"])
            if cert_ref is None:
                backrefute_status = "NOT_PROVIDED"
                final_item_outcome = "UNRESOLVED"
            else:
                try:
                    backrefute_result = check_backrefute(
                        store_root=store_root,
                        cert_ref=cert_ref,
                        old_regime_ref=normalized_old_regime,
                        target_old_artifact_ref=item_ref,
                        budget=morphism_payload.get("backrefute_policy", {}).get("budget", {}),
                    )
                except Exception:
                    backrefute_result = {"result": "INVALID"}
                backrefute_status = str(backrefute_result.get("result", "INVALID"))
                if backrefute_status == "VALID":
                    final_item_outcome = "REFUTED"
                else:
                    final_item_outcome = "UNRESOLVED"

        item_row = {
            "old_artifact_id": item_ref["artifact_id"],
            "translation_acceptance": translation_acceptance,
            "backrefute_status": backrefute_status,
            "final_outcome": final_item_outcome,
        }
        if translated_id is not None:
            item_row["translated_artifact_id"] = translated_id
        items.append(item_row)

    final_outcome = "ACCEPT"
    if any(row["final_outcome"] == "UNRESOLVED" for row in items):
        final_outcome = "SAFE_HALT"

    if final_outcome == "ACCEPT":
        new_overlap_accept = _collect_new_overlap_accept_set(
            store_root=store_root,
            regime_ref=normalized_new_regime,
            overlap_ids=overlap_ids,
            translated_preserved_set=translated_preserved_set,
        )
        raw_exceptions = morphism_payload.get("explicit_overlap_exceptions")
        exceptions: set[str] = set()
        if isinstance(raw_exceptions, list):
            for row in raw_exceptions:
                if isinstance(row, str):
                    exceptions.add(row)
        allowed_set = translated_preserved_set.union(exceptions)
        if new_overlap_accept != allowed_set:
            final_outcome = "SAFE_HALT"

    receipt_without_id = {
        "schema_name": "continuity_receipt_v1",
        "schema_version": "v19_0",
        "sigma_old_id": sigma_old.ref["artifact_id"],
        "sigma_new_id": sigma_new.ref["artifact_id"],
        "regime_old_id": canon_hash_obj(normalized_old_regime),
        "regime_new_id": canon_hash_obj(normalized_new_regime),
        "overlap_profile_id": str(overlap_payload.get("overlap_profile_id")),
        "translator_bundle_id": str(translator_payload.get("translator_bundle_id")),
        "totality_cert_id": totality_id,
        "budgets": {
            "continuity_budget": budget_bundle["continuity_budget"],
            "translator_budget": budget_bundle["translator_budget"],
            "backrefute_budget": morphism_payload.get("backrefute_policy", {}).get("budget", budget_bundle["continuity_budget"]),
        },
        "items": items,
        "final_outcome": final_outcome,
    }
    receipt = dict(receipt_without_id)
    receipt["receipt_id"] = canon_hash_obj(receipt_without_id)
    validate_schema(receipt, "continuity_receipt_v1")
    verify_declared_id(receipt, "receipt_id")
    return receipt


__all__ = ["TranslationResult", "apply_translator_bundle", "check_continuity"]
