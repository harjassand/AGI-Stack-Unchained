"""v19 promotion adapter with continuity/J dominance gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v18_0 import omega_promoter_v1 as v18_promoter
from ..v18_0.omega_common_v1 import (
    canon_hash_obj,
    load_canon_dict,
    resolve_execution_mode,
    require_no_absolute_paths,
    validate_schema as validate_v18_schema,
    write_hashed_json,
)
from ..v18_0.omega_promotion_bundle_v1 import extract_touched_paths
from .continuity.check_constitution_upgrade_v1 import check_constitution_upgrade
from .continuity.check_continuity_v1 import check_continuity
from .continuity.check_env_upgrade_v1 import check_env_upgrade
from .continuity.check_kernel_upgrade_v1 import check_kernel_upgrade, enforce_kernel_polarity
from .continuity.check_meta_law_v1 import check_meta_law, enforce_meta_law_for_morphism
from .continuity.common_v1 import canon_hash_obj as canon_hash_obj_v19
from .continuity.common_v1 import (
    ContinuityV19Error,
    fail,
    sorted_by_canon,
    validate_schema,
    verify_declared_id,
    write_canonical,
)
from .continuity.loaders_v1 import load_artifact_ref
from .continuity.objective_J_v1 import compute_J
from .federation.check_treaty_v1 import T_AXIS_MORPHISM_TYPE, check_treaty
from .federation.ok_ican_v1 import DEFAULT_ICAN_PROFILE, ican_id
from .world.check_world_snapshot_v1 import W_AXIS_MORPHISM_TYPE, check_world_snapshot


_GOVERNED_PREFIXES = (
    "CDEL-v2/cdel/",
    "Genesis/schema/",
    "meta-core/",
    "orchestrator/",
)

_MORPHISMS_REQUIRING_C_CONT = {"M_K", "M_E", "M_M", "M_C"}


def _load_axis_bundle_from_bundle(*, bundle_obj: dict[str, Any], bundle_path: Path) -> dict[str, Any] | None:
    axis_ref = bundle_obj.get("axis_upgrade_bundle_ref")
    if isinstance(axis_ref, dict):
        loaded = load_artifact_ref(Path(".").resolve(), axis_ref)
        if not isinstance(loaded.payload, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        return loaded.payload

    sidecar = bundle_path.parent / "axis_upgrade_bundle_v1.json"
    if sidecar.exists() and sidecar.is_file():
        payload = load_canon_dict(sidecar)
        if not isinstance(payload, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        return payload
    return None


def _requires_axis_bundle(bundle_obj: dict[str, Any]) -> bool:
    touched = extract_touched_paths(bundle_obj)
    for row in touched:
        for prefix in _GOVERNED_PREFIXES:
            if str(row).startswith(prefix):
                return True
    return False


def _is_artifact_ref(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return set(value.keys()) == {"artifact_id", "artifact_relpath"}


def _collect_artifact_refs(value: Any, out: list[dict[str, str]]) -> None:
    if _is_artifact_ref(value):
        out.append(value)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_artifact_refs(item, out)
        return
    if isinstance(value, list):
        for item in value:
            _collect_artifact_refs(item, out)


def _rewrite_artifact_refs(value: Any, mapping: dict[tuple[str, str], dict[str, str]]) -> Any:
    if _is_artifact_ref(value):
        key = (str(value["artifact_id"]), str(value["artifact_relpath"]))
        if key not in mapping:
            fail("MISSING_ARTIFACT", safe_halt=True)
        return dict(mapping[key])
    if isinstance(value, dict):
        return {str(k): _rewrite_artifact_refs(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [_rewrite_artifact_refs(v, mapping) for v in value]
    return value


def _materialize_axis_bundle_for_meta_core(
    *,
    axis_bundle: dict[str, Any],
    source_root: Path,
    bundle_dir: Path,
) -> None:
    refs: list[dict[str, str]] = []
    _collect_artifact_refs(axis_bundle, refs)
    refs_sorted = sorted_by_canon(refs)
    mapping: dict[tuple[str, str], dict[str, str]] = {}
    by_id: dict[str, dict[str, str]] = {}

    for idx, ref in enumerate(refs_sorted):
        key = (str(ref["artifact_id"]), str(ref["artifact_relpath"]))
        existing = mapping.get(key)
        if existing is not None:
            continue
        artifact_id = str(ref["artifact_id"])
        by_artifact_id = by_id.get(artifact_id)
        if by_artifact_id is not None:
            mapping[key] = dict(by_artifact_id)
            continue

        loaded = load_artifact_ref(source_root, ref)
        rel = f"omega/continuity/materialized/{idx:04d}_{artifact_id.split(':', 1)[1]}.json"
        write_canonical(bundle_dir / rel, loaded.payload)
        remapped = {"artifact_id": artifact_id, "artifact_relpath": rel}
        mapping[key] = remapped
        by_id[artifact_id] = remapped

    remapped_bundle = _rewrite_artifact_refs(axis_bundle, mapping)
    if not isinstance(remapped_bundle, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    without_id = dict(remapped_bundle)
    without_id.pop("axis_bundle_id", None)
    remapped_bundle["axis_bundle_id"] = canon_hash_obj_v19(without_id)
    validate_schema(remapped_bundle, "axis_upgrade_bundle_v1")
    verify_declared_id(remapped_bundle, "axis_bundle_id")
    write_canonical(bundle_dir / "omega" / "axis_upgrade_bundle_v1.json", remapped_bundle)


def _find_axis_specific_proof_ref(
    *,
    proof_refs: list[dict[str, Any]],
    expected_schema_name: str,
) -> dict[str, Any]:
    store_root = Path(".").resolve()
    for row in sorted_by_canon(proof_refs):
        if not isinstance(row, dict):
            continue
        loaded = load_artifact_ref(store_root, row)
        payload = loaded.payload
        if isinstance(payload, dict) and str(payload.get("schema_name", "")) == expected_schema_name:
            return loaded.ref
    fail("MISSING_ARTIFACT", safe_halt=True)
    return {}


def _schema_name(payload: dict[str, Any]) -> str:
    return str(payload.get("schema_name", "")).strip()


def _load_axis_proof_payloads(*, proof_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for row in sorted_by_canon(proof_refs):
        if not isinstance(row, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        loaded = load_artifact_ref(Path(".").resolve(), row)
        if not isinstance(loaded.payload, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        payloads.append(loaded.payload)
    return payloads


def _single_payload(*, payloads: list[dict[str, Any]], schema_name: str) -> dict[str, Any]:
    rows = [row for row in payloads if _schema_name(row) == schema_name]
    if len(rows) != 1:
        fail("MISSING_ARTIFACT", safe_halt=True)
    return rows[0]


def _multi_payload(*, payloads: list[dict[str, Any]], schema_name: str) -> list[dict[str, Any]]:
    return [row for row in payloads if _schema_name(row) == schema_name]


def _enforce_world_morphism(
    *,
    idx: int,
    proof_refs: list[dict[str, Any]],
    continuity_budget: dict[str, Any],
    promotion_dir: Path,
) -> None:
    payloads = _load_axis_proof_payloads(proof_refs=proof_refs)
    snapshot = _single_payload(payloads=payloads, schema_name="world_snapshot_v1")
    manifest = _single_payload(payloads=payloads, schema_name="world_snapshot_manifest_v1")
    ingestion_receipt = _single_payload(payloads=payloads, schema_name="sealed_ingestion_receipt_v1")
    bindings = _multi_payload(payloads=payloads, schema_name="world_task_binding_v1")
    receipt = check_world_snapshot(
        snapshot=snapshot,
        manifest=manifest,
        ingestion_receipt=ingestion_receipt,
        world_task_bindings=(bindings or None),
        budget_spec=continuity_budget,
    )
    write_canonical(promotion_dir / f"world_snapshot_check_{idx:03d}.json", receipt)
    if str(receipt.get("outcome", "")) != "ACCEPT":
        fail(str(receipt.get("reason_code", "WORLD_SNAPSHOT_INVALID")), safe_halt=True)


def _treaty_acceptance_profile(payloads: list[dict[str, Any]]) -> tuple[bool, bool]:
    rows = _multi_payload(payloads=payloads, schema_name="treaty_acceptance_profile_v1")
    if not rows:
        return True, True
    row = rows[-1]
    source_accepts = bool(row.get("source_accepts", True))
    target_accepts = bool(row.get("target_accepts", True))
    return source_accepts, target_accepts


def _enforce_treaty_morphism(
    *,
    idx: int,
    proof_refs: list[dict[str, Any]],
    continuity_budget: dict[str, Any],
    promotion_dir: Path,
) -> None:
    payloads = _load_axis_proof_payloads(proof_refs=proof_refs)
    treaty = _single_payload(payloads=payloads, schema_name="treaty_v1")
    treaty_id = str(treaty.get("treaty_id", "")).strip()
    overlap_ids = [
        str(row).strip()
        for row in (treaty.get("overlap_test_set_ids") or [])
        if isinstance(row, str) and str(row).strip().startswith("sha256:")
    ]
    artifact_store: dict[str, Any] = {treaty_id: treaty} if treaty_id.startswith("sha256:") else {}
    witnesses_by_input_id: dict[str, dict[str, Any]] = {}
    overlap_objects_by_id: dict[str, Any] = {}

    ok_signature = None
    for payload in payloads:
        schema_name = _schema_name(payload)
        if schema_name == "ok_overlap_signature_v1":
            overlap_signature_id = str(payload.get("overlap_signature_id", "")).strip()
            if overlap_signature_id.startswith("sha256:"):
                artifact_store[overlap_signature_id] = payload
                ok_signature = payload
        elif schema_name == "translator_bundle_v1":
            bundle_id = str(payload.get("translator_bundle_id", "")).strip()
            if bundle_id.startswith("sha256:"):
                artifact_store[bundle_id] = payload
        elif schema_name == "ok_refutation_witness_v1":
            witness_id = str(payload.get("witness_id", "")).strip()
            if witness_id.startswith("sha256:"):
                artifact_store[witness_id] = payload
            subject = payload.get("subject")
            if isinstance(subject, dict):
                input_id = str(subject.get("input_overlap_object_id", "")).strip()
                if input_id.startswith("sha256:"):
                    witnesses_by_input_id[input_id] = payload

    ican_profile_id = DEFAULT_ICAN_PROFILE["profile_id"]
    if isinstance(ok_signature, dict):
        profile_raw = str(ok_signature.get("ican_profile_id", "")).strip()
        if profile_raw.startswith("sha256:"):
            ican_profile_id = profile_raw

    for payload in payloads:
        schema_name = _schema_name(payload)
        if schema_name == "overlap_test_object_v1":
            object_payload = payload.get("object")
            if object_payload is None:
                fail("SCHEMA_ERROR", safe_halt=True)
            object_id = str(payload.get("overlap_object_id", "")).strip()
            if not object_id.startswith("sha256:"):
                object_id = ican_id(object_payload, ican_profile_id)
            if object_id in overlap_ids:
                overlap_objects_by_id[object_id] = object_payload
                artifact_store[object_id] = object_payload
            continue
        if schema_name in {
            "treaty_v1",
            "ok_overlap_signature_v1",
            "translator_bundle_v1",
            "ok_refutation_witness_v1",
            "treaty_acceptance_profile_v1",
        }:
            continue
        try:
            candidate_id = ican_id(payload, ican_profile_id)
        except Exception:
            continue
        if candidate_id in overlap_ids:
            overlap_objects_by_id[candidate_id] = payload
            artifact_store[candidate_id] = payload

    source_accepts, target_accepts = _treaty_acceptance_profile(payloads)
    source_checker = lambda _obj, value=source_accepts: value
    target_checker = lambda _obj, value=target_accepts: value
    treaty_budget = continuity_budget
    dispute_rule = treaty.get("dispute_rule")
    if isinstance(dispute_rule, dict):
        dispute_budget = dispute_rule.get("budgets")
        if isinstance(dispute_budget, dict):
            treaty_budget = dispute_budget
    receipt = check_treaty(
        treaty=treaty,
        artifact_store=artifact_store,
        overlap_objects_by_id=overlap_objects_by_id,
        witnesses_by_input_id=(witnesses_by_input_id or None),
        source_checker=source_checker,
        target_checker=target_checker,
        budget_spec=treaty_budget,
    )
    write_canonical(promotion_dir / f"treaty_check_{idx:03d}.json", receipt)
    outcome = str(receipt.get("outcome", "SAFE_HALT")).strip()
    if outcome == "ACCEPT":
        return
    if outcome == "SAFE_SPLIT":
        reason_code = str(receipt.get("reason_code", "TREATY_SAFE_SPLIT")).strip() or "TREATY_SAFE_SPLIT"
        raise ContinuityV19Error(f"SAFE_SPLIT:{reason_code}")
    fail(str(receipt.get("reason_code", "TREATY_INVALID")), safe_halt=True)


def _write_v18_reject(
    *,
    tick_u64: int,
    dispatch_ctx: dict[str, Any],
    promotion_bundle_hash: str,
    reason: str,
) -> tuple[dict[str, Any], str]:
    out_dir = Path(dispatch_ctx["dispatch_dir"]) / "promotion"
    out_dir.mkdir(parents=True, exist_ok=True)
    execution_mode = resolve_execution_mode()
    payload = {
        "schema_version": "omega_promotion_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "promotion_bundle_hash": promotion_bundle_hash,
        "execution_mode": execution_mode,
        "meta_core_verifier_fingerprint": v18_promoter._meta_fingerprint(),
        "result": {
            "status": "REJECTED",
            "reason_code": reason if reason in {
                "NO_PROMOTION_BUNDLE",
                "SUBVERIFIER_INVALID",
                "META_CORE_REJECT",
                "FORBIDDEN_PATH",
                "TEST_PLAN_RECEIPT_MISSING_OR_FAIL",
                "ALREADY_ACTIVE",
                "TOOLCHAIN_MISMATCH",
                "UNKNOWN",
                "CCAP_RECEIPT_MISSING_OR_MISMATCH",
                "CCAP_RECEIPT_REJECTED",
                "CCAP_APPLY_MISMATCH",
                "CCAP_TOUCHED_PATHS_INVALID",
                "EK_META_VERIFY_MISSING_OR_FAIL",
            } else "UNKNOWN",
        },
        "active_manifest_hash_after": None,
    }
    require_no_absolute_paths(payload)
    _, receipt, digest = write_hashed_json(out_dir, "omega_promotion_receipt_v1.json", payload, id_field="receipt_id")
    validate_v18_schema(receipt, "omega_promotion_receipt_v1")
    return receipt, digest


def _verify_axis_bundle_gate(
    *,
    bundle_obj: dict[str, Any],
    bundle_path: Path,
    promotion_dir: Path,
) -> None:
    axis_bundle = _load_axis_bundle_from_bundle(bundle_obj=bundle_obj, bundle_path=bundle_path)
    needs_axis = _requires_axis_bundle(bundle_obj)
    if axis_bundle is None:
        if needs_axis:
            fail("MISSING_ARTIFACT", safe_halt=True)
        return

    validate_schema(axis_bundle, "axis_upgrade_bundle_v1")
    verify_declared_id(axis_bundle, "axis_bundle_id")

    sigma_old_ref = axis_bundle.get("sigma_old_ref")
    sigma_new_ref = axis_bundle.get("sigma_new_ref")
    regime_old_ref = axis_bundle.get("regime_old_ref")
    regime_new_ref = axis_bundle.get("regime_new_ref")
    objective_profile_ref = axis_bundle.get("objective_J_profile_ref")
    continuity_budget = axis_bundle.get("continuity_budget")

    if not isinstance(sigma_old_ref, dict) or not isinstance(sigma_new_ref, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    if not isinstance(regime_old_ref, dict) or not isinstance(regime_new_ref, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    if not isinstance(objective_profile_ref, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    if not isinstance(continuity_budget, dict):
        fail("MISSING_BUDGET", safe_halt=True)

    continuity_constitution_ref = axis_bundle.get("continuity_constitution_ref")
    continuity_constitution_payload: dict[str, Any] | None = None
    if isinstance(continuity_constitution_ref, dict):
        loaded_constitution = load_artifact_ref(Path(".").resolve(), continuity_constitution_ref)
        if not isinstance(loaded_constitution.payload, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        continuity_constitution_payload = loaded_constitution.payload
        validate_schema(continuity_constitution_payload, "continuity_constitution_v1")
        verify_declared_id(continuity_constitution_payload, "constitution_id")

    morphisms = axis_bundle.get("morphisms")
    if not isinstance(morphisms, list) or not morphisms:
        fail("SCHEMA_ERROR", safe_halt=True)

    kernel_rows: list[dict[str, Any]] = []
    has_m_d = False
    max_epsilon_udc = 0

    for idx, entry in enumerate(morphisms):
        if not isinstance(entry, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        morphism_ref = entry.get("morphism_ref")
        totality_ref = entry.get("totality_cert_ref")
        continuity_ref = entry.get("continuity_receipt_ref")
        if not isinstance(morphism_ref, dict) or not isinstance(totality_ref, dict) or not isinstance(continuity_ref, dict):
            fail("SCHEMA_ERROR", safe_halt=True)

        morphism = load_artifact_ref(Path(".").resolve(), morphism_ref)
        if not isinstance(morphism.payload, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        validate_schema(morphism.payload, "continuity_morphism_v1")
        verify_declared_id(morphism.payload, "morphism_id")
        morphism_type = str(morphism.payload.get("morphism_type", "")).strip()

        if morphism_type in _MORPHISMS_REQUIRING_C_CONT and continuity_constitution_payload is None:
            fail("MISSING_ARTIFACT", safe_halt=True)
        if continuity_constitution_ref is not None:
            if not isinstance(continuity_constitution_ref, dict):
                fail("SCHEMA_ERROR", safe_halt=True)
            enforcement = enforce_meta_law_for_morphism(
                store_root=Path(".").resolve(),
                continuity_constitution_ref=continuity_constitution_ref,
                morphism_ref=morphism_ref,
                budget=continuity_budget,
            )
            write_canonical(promotion_dir / f"meta_law_enforcement_{idx:03d}.json", enforcement)

        proof_refs = entry.get("axis_specific_proof_refs")
        if not isinstance(proof_refs, list):
            fail("SCHEMA_ERROR", safe_halt=True)
        if morphism_type == "M_K":
            kernel_upgrade_ref = _find_axis_specific_proof_ref(
                proof_refs=proof_refs,
                expected_schema_name="kernel_upgrade_v1",
            )
            kernel_result = check_kernel_upgrade(
                store_root=Path(".").resolve(),
                kernel_upgrade_ref=kernel_upgrade_ref,
                budget=continuity_budget,
            )
            kernel_rows.append(kernel_result)
        elif morphism_type == "M_E":
            env_upgrade_ref = _find_axis_specific_proof_ref(
                proof_refs=proof_refs,
                expected_schema_name="env_upgrade_v1",
            )
            _env_result = check_env_upgrade(
                store_root=Path(".").resolve(),
                env_upgrade_ref=env_upgrade_ref,
                budget=continuity_budget,
            )
        elif morphism_type == "M_C":
            constitution_morphism_ref = _find_axis_specific_proof_ref(
                proof_refs=proof_refs,
                expected_schema_name="constitution_morphism_v1",
            )
            _constitution_result = check_constitution_upgrade(
                store_root=Path(".").resolve(),
                constitution_morphism_ref=constitution_morphism_ref,
                budget=continuity_budget,
            )
        elif morphism_type == "M_M":
            meta_law_morphism_ref = _find_axis_specific_proof_ref(
                proof_refs=proof_refs,
                expected_schema_name="meta_law_morphism_v1",
            )
            _meta_result = check_meta_law(
                store_root=Path(".").resolve(),
                meta_law_morphism_ref=meta_law_morphism_ref,
                budget=continuity_budget,
            )
        elif morphism_type == "M_D":
            has_m_d = True
            epsilon_udc_u64 = int(morphism.payload.get("epsilon_udc_u64", 0))
            if epsilon_udc_u64 < 0:
                fail("SCHEMA_ERROR", safe_halt=True)
            max_epsilon_udc = max(max_epsilon_udc, epsilon_udc_u64)
        elif morphism_type == W_AXIS_MORPHISM_TYPE:
            _enforce_world_morphism(
                idx=idx,
                proof_refs=proof_refs,
                continuity_budget=continuity_budget,
                promotion_dir=promotion_dir,
            )
        elif morphism_type == T_AXIS_MORPHISM_TYPE:
            _enforce_treaty_morphism(
                idx=idx,
                proof_refs=proof_refs,
                continuity_budget=continuity_budget,
                promotion_dir=promotion_dir,
            )

        totality = load_artifact_ref(Path(".").resolve(), totality_ref)
        if not isinstance(totality.payload, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        validate_schema(totality.payload, "translator_totality_cert_v1")
        verify_declared_id(totality.payload, "cert_id")
        for row in totality.payload.get("results", []):
            if not isinstance(row, dict):
                fail("SCHEMA_ERROR", safe_halt=True)
            if str(row.get("status", "")) in {"FAIL", "BUDGET_EXHAUSTED"}:
                fail("CONTINUITY_FAILURE", safe_halt=True)

        continuity = load_artifact_ref(Path(".").resolve(), continuity_ref)
        if not isinstance(continuity.payload, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        validate_schema(continuity.payload, "continuity_receipt_v1")
        verify_declared_id(continuity.payload, "receipt_id")

        recomputed = check_continuity(
            sigma_old_ref=sigma_old_ref,
            sigma_new_ref=sigma_new_ref,
            regime_old_ref=regime_old_ref,
            regime_new_ref=regime_new_ref,
            morphism_ref=morphism_ref,
            budgets=morphism.payload.get("budgets", {
                "continuity_budget": continuity_budget,
                "translator_budget": continuity_budget,
                "receipt_translation_budget": continuity_budget,
                "totality_budget": continuity_budget,
            }),
        )
        if canon_hash_obj_v19(recomputed) != canon_hash_obj_v19(continuity.payload):
            fail("NONDETERMINISTIC", safe_halt=True)
        if str(recomputed.get("final_outcome", "")) != "ACCEPT":
            fail("CONTINUITY_FAILURE", safe_halt=True)

        write_canonical(promotion_dir / f"continuity_recomputed_{idx:03d}.json", recomputed)

    if kernel_rows:
        enforce_kernel_polarity(kernel_rows)

    j_old = compute_J(
        regime_ref=regime_old_ref,
        sigma_ref=sigma_old_ref,
        profile_ref=objective_profile_ref,
        budgets=continuity_budget,
    )
    j_new = compute_J(
        regime_ref=regime_new_ref,
        sigma_ref=sigma_new_ref,
        profile_ref=objective_profile_ref,
        budgets=continuity_budget,
    )

    epsilon = int(j_new.get("epsilon", 0))
    old_val = int(j_old.get("weighted_sum", 0))
    new_val = int(j_new.get("weighted_sum", 0))
    if new_val > (old_val - epsilon):
        fail("J_DOMINANCE_FAILURE", safe_halt=True)

    if has_m_d:
        old_udc = int((j_old.get("terms") or {}).get("UDC_BASE", 0))
        new_udc = int((j_new.get("terms") or {}).get("UDC_BASE", 0))
        epsilon_udc = max_epsilon_udc
        if continuity_constitution_payload is not None:
            epsilon_terms = continuity_constitution_payload.get("epsilon_terms")
            if isinstance(epsilon_terms, dict):
                epsilon_udc = max(epsilon_udc, int(epsilon_terms.get("epsilon_udc", 0)))
        if old_udc - new_udc < epsilon_udc:
            fail("J_DOMINANCE_FAILURE", safe_halt=True)

    write_canonical(promotion_dir / "objective_J_old_v1.json", j_old)
    write_canonical(promotion_dir / "objective_J_new_v1.json", j_new)


def run_subverifier(*, tick_u64: int, dispatch_ctx: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    return v18_promoter.run_subverifier(tick_u64=tick_u64, dispatch_ctx=dispatch_ctx)


def run_promotion(
    *,
    tick_u64: int,
    dispatch_ctx: dict[str, Any] | None,
    subverifier_receipt: dict[str, Any] | None,
    allowlists: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    if dispatch_ctx is None:
        return None, None

    subverifier_status = str((subverifier_receipt or {}).get("result", {}).get("status", "")).strip()
    if subverifier_receipt is None or subverifier_status != "VALID":
        return v18_promoter.run_promotion(
            tick_u64=tick_u64,
            dispatch_ctx=dispatch_ctx,
            subverifier_receipt=subverifier_receipt,
            allowlists=allowlists,
        )

    bundle_path, bundle_hash = v18_promoter._find_promotion_bundle(dispatch_ctx)
    if bundle_path is None:
        return v18_promoter.run_promotion(
            tick_u64=tick_u64,
            dispatch_ctx=dispatch_ctx,
            subverifier_receipt=subverifier_receipt,
            allowlists=allowlists,
        )

    bundle_obj = load_canon_dict(bundle_path)
    promotion_dir = bundle_path.parent
    axis_bundle_for_meta = _load_axis_bundle_from_bundle(bundle_obj=bundle_obj, bundle_path=bundle_path)

    try:
        _verify_axis_bundle_gate(
            bundle_obj=bundle_obj,
            bundle_path=bundle_path,
            promotion_dir=promotion_dir,
        )
    except ContinuityV19Error as exc:
        message = str(exc)
        gate_outcome = "SAFE_SPLIT" if message.startswith("SAFE_SPLIT:") else "SAFE_HALT"
        write_canonical(
            promotion_dir / "axis_gate_failure_v1.json",
            {
                "schema_name": "axis_gate_failure_v1",
                "schema_version": "v19_0",
                "outcome": gate_outcome,
                "detail": message,
            },
        )
        return _write_v18_reject(
            tick_u64=tick_u64,
            dispatch_ctx=dispatch_ctx,
            promotion_bundle_hash=bundle_hash or canon_hash_obj(bundle_obj),
            reason="UNKNOWN",
        )
    except Exception:
        return _write_v18_reject(
            tick_u64=tick_u64,
            dispatch_ctx=dispatch_ctx,
            promotion_bundle_hash=bundle_hash or canon_hash_obj(bundle_obj),
            reason="UNKNOWN",
        )
    original_build_meta_bundle = v18_promoter._build_meta_core_promotion_bundle

    def _build_meta_bundle_with_continuity(
        *,
        out_dir: Path,
        campaign_id: str,
        source_bundle_hash: str,
    ) -> Path:
        bundle_dir = original_build_meta_bundle(
            out_dir=out_dir,
            campaign_id=campaign_id,
            source_bundle_hash=source_bundle_hash,
        )
        if isinstance(axis_bundle_for_meta, dict):
            _materialize_axis_bundle_for_meta_core(
                axis_bundle=axis_bundle_for_meta,
                source_root=Path(".").resolve(),
                bundle_dir=bundle_dir,
            )
        return bundle_dir

    v18_promoter._build_meta_core_promotion_bundle = _build_meta_bundle_with_continuity
    try:
        return v18_promoter.run_promotion(
            tick_u64=tick_u64,
            dispatch_ctx=dispatch_ctx,
            subverifier_receipt=subverifier_receipt,
            allowlists=allowlists,
        )
    finally:
        v18_promoter._build_meta_core_promotion_bundle = original_build_meta_bundle


__all__ = ["run_promotion", "run_subverifier"]
