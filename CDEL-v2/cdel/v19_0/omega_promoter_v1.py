"""v19 promotion adapter with continuity/J dominance gates."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from orchestrator.native.runtime_stats_v1 import RUNTIME_STATS_SOURCE_ID

from ..v18_0 import omega_promoter_v1 as v18_promoter
from ..v18_0.ccap_runtime_v1 import normalize_subrun_relpath
from ..v18_0.omega_common_v1 import (
    canon_hash_obj,
    load_canon_dict,
    repo_root,
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
from .nontriviality_cert_v1 import build_nontriviality_cert_v1 as build_shared_nontriviality_cert_v1
from .world.check_world_snapshot_v1 import W_AXIS_MORPHISM_TYPE, check_world_snapshot


_GOVERNED_PREFIXES = (
    "CDEL-v2/cdel/",
    "Genesis/schema/",
    "meta-core/",
    "orchestrator/",
)

_MORPHISMS_REQUIRING_C_CONT = {"M_K", "M_E", "M_M", "M_C"}

_AXIS_EXEMPTIONS_REL = "configs/omega_axis_gate_exemptions_v1.json"
EXPECTED_AXIS_EXEMPTIONS_ID = "sha256:ddf80e01910d5a304332976b2c7b8f9727e0bdd6e74418d8621a97993819d3d3"
_SHA256_ZERO = "sha256:" + ("0" * 64)
_HEAVY_DECLARED_CLASSES = {"FRONTIER_HEAVY", "CANARY_HEAVY"}
_DECLARED_CLASSES = {"FRONTIER_HEAVY", "CANARY_HEAVY", "BASELINE_CORE", "MAINTENANCE"}
_COMMENT_LINE_RE = re.compile(r"^(#|//|/\*|\*|\*/)")
_SH1_CAPABILITY_ID = "RSI_GE_SH1_OPTIMIZER"
_FORCED_HEAVY_ENV_KEY = "OMEGA_SH1_FORCED_HEAVY_B"
_HARD_TASK_METRIC_IDS: tuple[str, ...] = (
    "hard_task_code_correctness_q32",
    "hard_task_performance_q32",
    "hard_task_reasoning_q32",
    "hard_task_suite_score_q32",
)


def _canonical_axis_gate_relpath(path_value: str) -> str:
    raw = str(path_value).strip().replace("\\", "/")
    if not raw:
        fail("SCHEMA_ERROR", safe_halt=True)
    parts: list[str] = []
    for token in raw.split("/"):
        part = str(token).strip()
        if not part or part == ".":
            continue
        if part == "..":
            fail("SCHEMA_ERROR", safe_halt=True)
        parts.append(part)
    if not parts:
        fail("SCHEMA_ERROR", safe_halt=True)
    rel = "/".join(parts)
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts:
        fail("SCHEMA_ERROR", safe_halt=True)
    return rel


def _canonical_axis_gate_relpaths(rows: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        rel = _canonical_axis_gate_relpath(str(row))
        if rel not in seen:
            out.append(rel)
            seen.add(rel)
    return sorted(out)


def _premarathon_v63_enabled() -> bool:
    raw = str(os.environ.get("OMEGA_PREMARATHON_V63", "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


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


def _parse_patch_touched_paths(patch_bytes: bytes) -> list[str]:
    touched: list[str] = []
    seen: set[str] = set()
    for raw in patch_bytes.decode("utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line.startswith("+++ "):
            continue
        if line == "+++ /dev/null":
            continue
        if not line.startswith("+++ b/"):
            continue
        rel = line[len("+++ b/") :]
        rel = rel.split("\t", 1)[0].strip()
        if rel.startswith('"') and rel.endswith('"') and len(rel) >= 2:
            rel = rel[1:-1]
        try:
            normalized = _canonical_axis_gate_relpath(normalize_subrun_relpath(rel))
        except Exception:
            normalized = _canonical_axis_gate_relpath(rel)
        if normalized and normalized not in seen:
            touched.append(normalized)
            seen.add(normalized)
    return sorted(touched)


def _resolve_ccap_subrun_root_for_bundle(*, bundle_obj: dict[str, Any], bundle_path: Path) -> Path:
    """Resolve the subrun root that contains CCAP payloads referenced by `bundle_obj`.

    Promotion can execute with different CWDs (subrun root vs state root) depending on call site.
    Fail closed if we cannot uniquely identify the subrun directory containing both CCAP and patch blobs.
    """
    ccap_rel = normalize_subrun_relpath(str(bundle_obj.get("ccap_relpath", "")).strip())
    patch_rel = normalize_subrun_relpath(str(bundle_obj.get("patch_relpath", "")).strip())

    candidate = bundle_path.parent.parent.resolve()
    if (candidate / ccap_rel).exists() and (candidate / patch_rel).exists():
        return candidate

    dispatch_dir = bundle_path.parent.parent.resolve()
    state_root = dispatch_dir.parent.parent.resolve()
    subruns_root = state_root / "subruns"
    candidates: list[Path] = []
    if subruns_root.exists() and subruns_root.is_dir():
        for subrun in sorted(subruns_root.glob("*"), key=lambda p: p.as_posix()):
            if not subrun.is_dir() or subrun.is_symlink():
                continue
            if (subrun / ccap_rel).exists() and (subrun / patch_rel).exists():
                candidates.append(subrun)
    if len(candidates) != 1:
        fail("MISSING_STATE_INPUT", safe_halt=True)
    return candidates[0].resolve()


def _effective_touched_paths_for_axis_gate(*, bundle_obj: dict[str, Any], bundle_path: Path) -> list[str]:
    if str(bundle_obj.get("schema_version", "")).strip() == "omega_promotion_bundle_ccap_v1":
        subrun_root = _resolve_ccap_subrun_root_for_bundle(bundle_obj=bundle_obj, bundle_path=bundle_path)
        patch_rel = normalize_subrun_relpath(str(bundle_obj.get("patch_relpath", "")).strip())
        patch_path = (subrun_root / patch_rel).resolve()
        if not patch_path.exists() or not patch_path.is_file():
            fail("MISSING_STATE_INPUT", safe_halt=True)
        return _parse_patch_touched_paths(patch_path.read_bytes())
    return _canonical_axis_gate_relpaths(extract_touched_paths(bundle_obj))


_AXIS_EXEMPTIONS_CACHE: tuple[list[str], str] | None = None


def _load_axis_gate_exemptions_config() -> tuple[list[str], str]:
    global _AXIS_EXEMPTIONS_CACHE
    cached = _AXIS_EXEMPTIONS_CACHE
    if cached is not None:
        return cached
    path = (repo_root() / _AXIS_EXEMPTIONS_REL).resolve()
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != "omega_axis_gate_exemptions_v1":
        fail("SCHEMA_ERROR", safe_halt=True)
    config_id = canon_hash_obj(payload)
    if config_id != EXPECTED_AXIS_EXEMPTIONS_ID:
        fail("SCHEMA_ERROR", safe_halt=True)
    rows = payload.get("exempt_relpaths")
    if not isinstance(rows, list) or not rows:
        fail("SCHEMA_ERROR", safe_halt=True)
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        rel = _canonical_axis_gate_relpath(str(row))
        if rel not in seen:
            out.append(rel)
            seen.add(rel)
    _AXIS_EXEMPTIONS_CACHE = (sorted(out), config_id)
    return _AXIS_EXEMPTIONS_CACHE


def _requires_axis_bundle(*, bundle_obj: dict[str, Any], bundle_path: Path) -> tuple[bool, bool, list[str], list[str], list[str], str]:
    touched = _effective_touched_paths_for_axis_gate(bundle_obj=bundle_obj, bundle_path=bundle_path)
    governed: list[str] = []
    for row in touched:
        for prefix in _GOVERNED_PREFIXES:
            if str(row).startswith(prefix):
                governed.append(str(row))
                break
    exempt_relpaths, exemptions_id = _load_axis_gate_exemptions_config()
    exempt_set = set(exempt_relpaths)
    axis_gate_exempted_b = all(row in exempt_set for row in touched)
    needs_axis = bool(governed) and not axis_gate_exempted_b
    return needs_axis, axis_gate_exempted_b, touched, governed, exempt_relpaths, exemptions_id


def _axis_gate_context_for_bundle(
    *,
    bundle_obj: dict[str, Any],
    bundle_path: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    axis_bundle = _load_axis_bundle_from_bundle(bundle_obj=bundle_obj, bundle_path=bundle_path)
    needs_axis, axis_exempted_b, touched, governed, exempt_relpaths, exemptions_id = _requires_axis_bundle(
        bundle_obj=bundle_obj,
        bundle_path=bundle_path,
    )
    axis_gate_axis_id: str | None = None
    axis_gate_bundle_sha256: str | None = None
    if isinstance(axis_bundle, dict):
        axis_gate_axis_id_raw = axis_bundle.get("axis_bundle_id")
        if isinstance(axis_gate_axis_id_raw, str) and axis_gate_axis_id_raw.strip():
            axis_gate_axis_id = str(axis_gate_axis_id_raw).strip()
        axis_gate_bundle_sha256 = canon_hash_obj(axis_bundle)
    axis_gate_reason_code = "EXEMPTED" if axis_exempted_b else ("REQUIRED" if needs_axis else "NONE")
    axis_gate_context = {
        "axis_gate_required_b": bool(needs_axis),
        "axis_gate_exempted_b": bool(axis_exempted_b),
        "axis_gate_reason_code": str(axis_gate_reason_code),
        "axis_gate_axis_id": axis_gate_axis_id,
        "axis_gate_bundle_present_b": bool(axis_bundle is not None),
        "axis_gate_bundle_sha256": axis_gate_bundle_sha256,
        "axis_gate_checked_relpaths_v1": list(touched),
    }
    axis_gate_decision_payload = {
        "schema_name": "axis_gate_decision_v1",
        "schema_version": "v19_0",
        "bundle_schema_version": str(bundle_obj.get("schema_version", "")).strip(),
        "effective_touched_paths": list(touched),
        "governed_touched_paths": list(governed),
        "exempt_relpaths": list(exempt_relpaths),
        "exemptions_config_id": str(exemptions_id),
        "needs_axis_bundle_b": bool(needs_axis),
        **axis_gate_context,
    }
    return axis_gate_context, axis_bundle, axis_gate_decision_payload


def _axis_gate_reason_code_for_failure(*, message: str, gate_outcome: str, fallback: str) -> str:
    text = str(message).strip().upper()
    if text.startswith("SAFE_HALT:MISSING_ARTIFACT"):
        return "MISSING_AXIS_BUNDLE"
    if str(gate_outcome).strip() == "SAFE_SPLIT":
        return "SAFE_SPLIT"
    if text.startswith("SAFE_HALT:"):
        return "SAFE_HALT"
    fallback_norm = str(fallback).strip().upper()
    if fallback_norm and fallback_norm != "NONE":
        return fallback_norm
    return "SAFE_HALT"


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
        "utility_proof_hash": None,
        "declared_class": None,
        "effect_class": "EFFECT_REJECTED",
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
            "route": "NONE",
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
) -> dict[str, Any]:
    axis_gate_context, axis_bundle, axis_gate_decision_payload = _axis_gate_context_for_bundle(
        bundle_obj=bundle_obj,
        bundle_path=bundle_path,
    )
    write_canonical(
        promotion_dir / "axis_gate_decision_v1.json",
        axis_gate_decision_payload,
    )
    # Axis validation is required only when governed touched paths are not exempt.
    # If the bundle carries an optional axis payload while `needs_axis` is false,
    # treat it as non-blocking and skip the expensive/strict checks.
    if bool(axis_gate_context.get("axis_gate_exempted_b", False)):
        axis_gate_context = dict(axis_gate_context)
        axis_gate_context["axis_gate_required_b"] = False
        axis_gate_context["axis_gate_reason_code"] = "EXEMPTED"
        return axis_gate_context
    if not bool(axis_gate_context.get("axis_gate_required_b", False)):
        return axis_gate_context
    if axis_bundle is None:
        fail("MISSING_ARTIFACT", safe_halt=True)

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
    return axis_gate_context


def _is_sha256(value: Any) -> bool:
    text = str(value).strip()
    return text.startswith("sha256:") and len(text) == 71 and all(ch in "0123456789abcdef" for ch in text.split(":", 1)[1])


def _config_dir_for_dispatch(dispatch_ctx: dict[str, Any]) -> Path | None:
    state_root_raw = dispatch_ctx.get("state_root")
    if not isinstance(state_root_raw, (str, Path)):
        return None
    state_root = Path(state_root_raw).resolve()
    config_dir = state_root.parent / "config"
    if config_dir.exists() and config_dir.is_dir():
        return config_dir
    return None


def _load_long_run_profile_for_dispatch(dispatch_ctx: dict[str, Any]) -> dict[str, Any] | None:
    config_dir = _config_dir_for_dispatch(dispatch_ctx)
    if config_dir is None:
        return None
    candidates = [config_dir / "long_run_profile_v1.json"]
    # Accept profile filename variants (for example long_run_profile_v1_debug_hard_task.json)
    # while still validating content against long_run_profile_v1 schema.
    candidates.extend(sorted(config_dir.glob("**/long_run_profile_v1*.json"), key=lambda p: p.as_posix()))
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = load_canon_dict(path)
            validate_schema(payload, "long_run_profile_v1")
        except Exception:  # noqa: BLE001
            continue
        return payload
    return None


def _load_utility_policy_for_dispatch(dispatch_ctx: dict[str, Any]) -> dict[str, Any] | None:
    profile = _load_long_run_profile_for_dispatch(dispatch_ctx)
    if not isinstance(profile, dict):
        return None
    rel_raw = str(profile.get("utility_policy_rel", "")).strip()
    declared_id = str(profile.get("utility_policy_id", "")).strip()
    if not rel_raw or not declared_id:
        return None
    rel_path = Path(rel_raw)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        return None
    config_dir = _config_dir_for_dispatch(dispatch_ctx)
    if config_dir is None:
        return None
    path = (config_dir / rel_path).resolve()
    if not path.exists() or not path.is_file():
        return None
    payload = load_canon_dict(path)
    validate_schema(payload, "utility_policy_v1")
    policy_id = str(payload.get("policy_id", "")).strip()
    payload_no_id = dict(payload)
    payload_no_id.pop("policy_id", None)
    if policy_id != canon_hash_obj_v19(payload_no_id):
        fail("NONDETERMINISTIC", safe_halt=True)
    if policy_id != declared_id:
        fail("PIN_HASH_MISMATCH", safe_halt=True)
    return payload


def _capability_id_from_dispatch(dispatch_ctx: dict[str, Any]) -> str:
    cap = dispatch_ctx.get("campaign_entry")
    if not isinstance(cap, dict):
        return ""
    return str(cap.get("capability_id", "")).strip()


def _dispatch_forced_heavy_b(dispatch_ctx: dict[str, Any]) -> bool:
    overrides = dispatch_ctx.get("invocation_env_overrides")
    if not isinstance(overrides, dict):
        return False
    raw = str(overrides.get(_FORCED_HEAVY_ENV_KEY, "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _declared_class_for_capability(dispatch_ctx: dict[str, Any], utility_policy: dict[str, Any] | None) -> str:
    capability_id = _capability_id_from_dispatch(dispatch_ctx)
    if capability_id == _SH1_CAPABILITY_ID and (_premarathon_v63_enabled() or _dispatch_forced_heavy_b(dispatch_ctx)):
        return "FRONTIER_HEAVY"
    if isinstance(utility_policy, dict):
        mapping = utility_policy.get("declared_class_by_capability")
        if isinstance(mapping, dict):
            mapped = str(mapping.get(capability_id, "")).strip().upper()
            if mapped in _DECLARED_CLASSES:
                return mapped
    return "UNCLASSIFIED"


def _baseline_ref_hash(meta_core_root: Path, active_binding: dict[str, Any] | None) -> str:
    if isinstance(active_binding, dict):
        promotion_bundle_hash = str(active_binding.get("promotion_bundle_hash", "")).strip()
        if _is_sha256(promotion_bundle_hash):
            return promotion_bundle_hash
    try:
        active_hex = str(v18_promoter._meta_core_active_bundle_hex(meta_core_root)).strip()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        active_hex = ""
    if len(active_hex) == 64 and all(ch in "0123456789abcdef" for ch in active_hex):
        return f"sha256:{active_hex}"
    return _SHA256_ZERO


def _load_latest_runtime_stats(dispatch_ctx: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    state_root_raw = dispatch_ctx.get("state_root")
    if not isinstance(state_root_raw, (str, Path)):
        return None, None
    ledger_dir = Path(state_root_raw).resolve() / "ledger" / "native"
    if not ledger_dir.exists() or not ledger_dir.is_dir():
        return None, None
    rows = sorted(ledger_dir.glob("sha256_*.omega_native_runtime_stats_v1.json"), key=lambda p: p.as_posix())
    if not rows:
        return None, None
    path = rows[-1]
    payload = load_canon_dict(path)
    validate_v18_schema(payload, "omega_native_runtime_stats_v1")
    digest = "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]
    if canon_hash_obj(payload) != digest:
        fail("NONDETERMINISTIC", safe_halt=True)
    return payload, digest


def _bundle_binary_hash(bundle_obj: dict[str, Any]) -> str | None:
    native_module = bundle_obj.get("native_module")
    if not isinstance(native_module, dict):
        return None
    value = str(native_module.get("binary_sha256", "")).strip()
    if _is_sha256(value):
        return value
    return None


def _binary_artifact_delta_present(*, bundle_obj: dict[str, Any], active_binding: dict[str, Any] | None) -> bool:
    candidate_binary = _bundle_binary_hash(bundle_obj)
    if candidate_binary is None:
        return False
    if not isinstance(active_binding, dict):
        return True
    baseline_native = active_binding.get("native_module")
    if not isinstance(baseline_native, dict):
        return True
    baseline_binary = str(baseline_native.get("binary_sha256", "")).strip()
    if not _is_sha256(baseline_binary):
        return True
    return baseline_binary != candidate_binary


def _nontrivial_delta_from_patch_bytes(patch_bytes: bytes) -> int:
    count = 0
    for raw_line in patch_bytes.decode("utf-8", errors="replace").splitlines():
        if raw_line.startswith("+++") or raw_line.startswith("---") or raw_line.startswith("@@"):
            continue
        if not raw_line:
            continue
        if raw_line[0] not in {"+", "-"}:
            continue
        body = raw_line[1:].strip()
        if not body:
            continue
        if _COMMENT_LINE_RE.match(body):
            continue
        count += 1
    return int(count)


def _patch_bytes_for_bundle(*, bundle_obj: dict[str, Any], bundle_path: Path) -> bytes | None:
    if str(bundle_obj.get("schema_version", "")).strip() != "omega_promotion_bundle_ccap_v1":
        return None
    patch_rel = normalize_subrun_relpath(str(bundle_obj.get("patch_relpath", "")).strip())
    if not patch_rel:
        return None
    subrun_root = _resolve_ccap_subrun_root_for_bundle(bundle_obj=bundle_obj, bundle_path=bundle_path)
    patch_path = (subrun_root / patch_rel).resolve()
    if not patch_path.exists() or not patch_path.is_file():
        return None
    return patch_path.read_bytes()


def _nontrivial_delta_for_bundle(*, bundle_obj: dict[str, Any], bundle_path: Path) -> int:
    patch_bytes = _patch_bytes_for_bundle(bundle_obj=bundle_obj, bundle_path=bundle_path)
    if patch_bytes is None:
        return 0
    return _nontrivial_delta_from_patch_bytes(patch_bytes)


def _rewrite_subverifier_receipt(
    *,
    dispatch_ctx: dict[str, Any],
    receipt: dict[str, Any],
    status: str,
    reason_code: str | None,
    nontriviality_cert_v1: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    out_dir = Path(dispatch_ctx["dispatch_dir"]) / "verifier"
    payload = dict(receipt)
    result = dict(payload.get("result") or {})
    result["status"] = status
    result["reason_code"] = reason_code
    payload["result"] = result
    payload["nontriviality_cert_v1"] = nontriviality_cert_v1 if isinstance(nontriviality_cert_v1, dict) else None
    _, new_receipt, digest = write_hashed_json(out_dir, "omega_subverifier_receipt_v1.json", payload, id_field="receipt_id")
    validate_v18_schema(new_receipt, "omega_subverifier_receipt_v1")
    return new_receipt, digest


def _compute_effect_class(*, declared_class: str, correctness_ok_b: bool, utility_ok_b: bool) -> str:
    if not correctness_ok_b:
        return "EFFECT_REJECTED"
    if declared_class in _HEAVY_DECLARED_CLASSES:
        return "EFFECT_HEAVY_OK" if utility_ok_b else "EFFECT_HEAVY_NO_UTILITY"
    if declared_class == "BASELINE_CORE":
        return "EFFECT_BASELINE_CORE_OK"
    if declared_class == "MAINTENANCE":
        return "EFFECT_MAINTENANCE_OK"
    return "EFFECT_REJECTED"


def _candidate_bundle_present(
    *,
    dispatch_ctx: dict[str, Any],
    promotion_bundle_hash: str,
) -> tuple[bool, Path | None]:
    if not _is_sha256(promotion_bundle_hash) or promotion_bundle_hash == _SHA256_ZERO:
        return False, None
    path, found_hash = v18_promoter._find_promotion_bundle(dispatch_ctx)  # type: ignore[attr-defined]
    if path is None or found_hash is None:
        return False, None
    if found_hash != promotion_bundle_hash:
        return False, None
    return path.exists() and path.is_file(), path


def _heavy_policy_for_capability(
    utility_policy: dict[str, Any] | None,
    capability_id: str,
    *,
    dispatch_ctx: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    sh1_capability_b = str(capability_id).strip() == _SH1_CAPABILITY_ID
    forced_sh1_heavy_b = bool(sh1_capability_b and isinstance(dispatch_ctx, dict) and _dispatch_forced_heavy_b(dispatch_ctx))
    if (_premarathon_v63_enabled() and sh1_capability_b) or forced_sh1_heavy_b:
        return {
            "probe_suite_id": "utility_probe_suite_default_v1",
            "stress_probe_suite_id": "utility_stress_probe_suite_default_v1",
            "primary_signal": "NONTRIVIAL_DELTA",
            "primary_threshold_u64": 1,
            "stress_signal": "REQUIRE_PATCH_DELTA",
            "stress_threshold_u64": 1,
        }
    if not isinstance(utility_policy, dict):
        return None
    rows = utility_policy.get("heavy_policies")
    if not isinstance(rows, dict):
        return None
    row = rows.get(str(capability_id))
    if isinstance(row, dict):
        return row
    return None


def _baseline_work_units_for_capability(
    *,
    dispatch_ctx: dict[str, Any],
    capability_id: str,
    baseline_ref_hash: str,
) -> int | None:
    if not _is_sha256(baseline_ref_hash) or baseline_ref_hash == _SHA256_ZERO:
        return None
    state_root_raw = dispatch_ctx.get("state_root")
    if not isinstance(state_root_raw, (str, Path)):
        return None
    state_root = Path(state_root_raw).resolve()
    rows = sorted(
        state_root.glob("dispatch/*/promotion/sha256_*.utility_proof_receipt_v1.json"),
        key=lambda p: p.as_posix(),
    )
    matched_tick = -1
    matched_work_units: int | None = None
    for path in rows:
        payload = load_canon_dict(path)
        try:
            validate_schema(payload, "utility_proof_receipt_v1")
        except Exception:
            continue
        if canon_hash_obj(payload) != ("sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]):
            continue
        if str(payload.get("capability_id", "")).strip() != str(capability_id):
            continue
        if str(payload.get("candidate_bundle_hash", "")).strip() != str(baseline_ref_hash):
            continue
        metrics = payload.get("utility_metrics")
        if not isinstance(metrics, dict):
            continue
        tick = int(payload.get("tick_u64", -1))
        work_units = int(metrics.get("runtime_total_work_units_u64", 0))
        if work_units < 0:
            continue
        if tick >= matched_tick:
            matched_tick = tick
            matched_work_units = work_units
    return matched_work_units


def _metric_q32(metrics: dict[str, Any], metric_id: str) -> int:
    raw = metrics.get(metric_id)
    if not isinstance(raw, dict):
        return 0
    if set(raw.keys()) != {"q"}:
        return 0
    return int(raw.get("q", 0))


def _selected_precheck_hard_task_prediction(dispatch_ctx: dict[str, Any]) -> dict[str, int]:
    out = {
        "predicted_hard_task_delta_q32": 0,
        "predicted_hard_task_baseline_score_q32": 0,
        "predicted_hard_task_patched_score_q32": 0,
    }
    subrun_root_raw = dispatch_ctx.get("subrun_root_abs")
    if not isinstance(subrun_root_raw, (str, Path)):
        return out
    precheck_dir = Path(subrun_root_raw).resolve() / "precheck"
    if not precheck_dir.exists() or not precheck_dir.is_dir():
        return out
    rows = sorted(precheck_dir.glob("sha256_*.candidate_precheck_receipt_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        return out
    payload = load_canon_dict(rows[-1])
    try:
        validate_schema(payload, "candidate_precheck_receipt_v1")
    except Exception:
        return out
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return out
    selected_rows = [row for row in candidates if isinstance(row, dict) and bool(row.get("selected_for_ccap_b", False))]
    if not selected_rows:
        return out
    selected_rows.sort(key=lambda row: int(max(0, int(row.get("candidate_idx_u32", 0)))))
    selected = selected_rows[0]
    for key in sorted(out.keys()):
        try:
            out[key] = int(selected.get(key, 0))
        except Exception:
            out[key] = 0
    forced_heavy_ctx = payload.get("forced_heavy_context_v1")
    final_rows = (forced_heavy_ctx or {}).get("final_candidate_rows_v1") if isinstance(forced_heavy_ctx, dict) else None
    if isinstance(final_rows, list):
        selected_ctx: dict[str, Any] | None = None
        selected_idx = int(max(0, int(selected.get("candidate_idx_u32", 0))))
        for row in final_rows:
            if not isinstance(row, dict):
                continue
            row_idx = int(max(0, int(row.get("candidate_idx_u32", -1))))
            if row_idx == selected_idx and str(row.get("precheck_decision_code", "")).strip() == "SELECTED_FOR_CCAP":
                selected_ctx = row
                break
        if selected_ctx is None:
            for row in final_rows:
                if isinstance(row, dict) and str(row.get("precheck_decision_code", "")).strip() == "SELECTED_FOR_CCAP":
                    selected_ctx = row
                    break
        if selected_ctx is not None:
            for key in sorted(out.keys()):
                try:
                    value = int(selected_ctx.get(key, 0))
                except Exception:
                    value = 0
                if out[key] == 0 and value != 0:
                    out[key] = int(value)
    return out


def _hard_task_observation_deltas(dispatch_ctx: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "observation_hash": None,
        "previous_observation_hash": None,
        "baseline_init_b": False,
        "prev_score_q32": 0,
        "gain_count_u64": 0,
        "delta_by_metric": {metric_id: 0 for metric_id in _HARD_TASK_METRIC_IDS},
    }
    state_root_raw = dispatch_ctx.get("state_root")
    if not isinstance(state_root_raw, (str, Path)):
        return out
    state_root = Path(state_root_raw).resolve()
    obs_dir = state_root / "observations"
    if not obs_dir.exists() or not obs_dir.is_dir():
        return out

    rows: list[tuple[int, str, dict[str, Any], str]] = []
    for path in sorted(obs_dir.glob("sha256_*.omega_observation_report_v1.json"), key=lambda p: p.as_posix()):
        payload = load_canon_dict(path)
        if str(payload.get("schema_version", "")).strip() != "omega_observation_report_v1":
            continue
        digest = "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]
        if canon_hash_obj(payload) != digest:
            continue
        tick_u64 = int(payload.get("tick_u64", -1))
        if tick_u64 < 0:
            continue
        rows.append((tick_u64, path.as_posix(), payload, digest))
    if not rows:
        return out

    rows.sort(key=lambda row: (int(row[0]), str(row[1])))
    _tick_now, _path_now, now_payload, now_hash = rows[-1]
    prev_payload: dict[str, Any] | None = None
    prev_hash: str | None = None
    if len(rows) >= 2:
        _tick_prev, _path_prev, prev_payload, prev_hash = rows[-2]

    now_metrics = now_payload.get("metrics")
    prev_metrics = (prev_payload or {}).get("metrics")
    if not isinstance(now_metrics, dict):
        return out
    baseline_raw = now_metrics.get("hard_task_baseline_init_u64", 1)
    try:
        baseline_init_u64 = int((baseline_raw or {}).get("q", 0) if isinstance(baseline_raw, dict) else baseline_raw)
    except Exception:
        baseline_init_u64 = 1
    now_prev_score_q32 = int(_metric_q32(now_metrics, "hard_task_prev_score_q32"))
    now_suite_delta_q32 = int(_metric_q32(now_metrics, "hard_task_delta_q32"))
    if not isinstance(prev_metrics, dict):
        out["observation_hash"] = str(now_hash)
        out["previous_observation_hash"] = str(prev_hash) if isinstance(prev_hash, str) and prev_hash else None
        out["baseline_init_b"] = bool(baseline_init_u64 > 0)
        out["prev_score_q32"] = int(now_prev_score_q32)
        deltas = {metric_id: 0 for metric_id in _HARD_TASK_METRIC_IDS}
        deltas["hard_task_suite_score_q32"] = int(now_suite_delta_q32)
        out["gain_count_u64"] = int(1 if int(now_suite_delta_q32) > 0 else 0)
        out["delta_by_metric"] = deltas
        return out

    deltas: dict[str, int] = {}
    gain_count = 0
    previous_hard_task_score_q32 = int(_metric_q32(prev_metrics, "hard_task_score_q32"))
    if previous_hard_task_score_q32 == 0:
        previous_hard_task_score_q32 = int(_metric_q32(prev_metrics, "hard_task_suite_score_q32"))
    for metric_id in _HARD_TASK_METRIC_IDS:
        delta_q32 = int(_metric_q32(now_metrics, metric_id)) - int(_metric_q32(prev_metrics, metric_id))
        deltas[metric_id] = int(delta_q32)
        if int(delta_q32) > 0:
            gain_count += 1

    out["observation_hash"] = str(now_hash)
    out["previous_observation_hash"] = str(prev_hash) if isinstance(prev_hash, str) and prev_hash else None
    out["baseline_init_b"] = bool(baseline_init_u64 > 0)
    out["prev_score_q32"] = int(now_prev_score_q32 if int(now_prev_score_q32) > 0 else previous_hard_task_score_q32)
    out["gain_count_u64"] = int(gain_count)
    out["delta_by_metric"] = dict(deltas)
    return out


def _signal_from_policy(
    *,
    signal_mode: str,
    threshold_u64: int,
    binary_delta_b: bool,
    nontrivial_delta_u64: int,
    runtime_total_work_units_u64: int,
    baseline_work_units_u64: int | None,
    bundle_obj: dict[str, Any],
    policy_artifact_relpath: str | None,
    promotion_dir: Path,
) -> bool:
    mode = str(signal_mode).strip().upper()
    if mode == "BINARY_ARTIFACT_DELTA":
        return bool(binary_delta_b) and int(threshold_u64) <= 1
    if mode == "NONTRIVIAL_DELTA":
        return int(nontrivial_delta_u64) >= int(max(0, threshold_u64))
    if mode == "CAPABILITY_GAIN":
        capability_gain = 1 if (binary_delta_b or nontrivial_delta_u64 > 0) else 0
        return capability_gain >= int(max(0, threshold_u64))
    if mode == "WORK_UNITS_REDUCTION":
        baseline = baseline_work_units_u64
        if baseline is None or baseline <= 0:
            return False
        candidate = int(max(0, runtime_total_work_units_u64))
        required_pct = int(max(0, threshold_u64))
        if required_pct <= 0:
            return candidate <= baseline
        # Percentage threshold is integer percent, deterministic and wall-clock free.
        required_delta = int((int(baseline) * int(required_pct) + 99) // 100)
        target = max(0, int(baseline) - int(required_delta))
        return candidate <= target
    if mode == "REQUIRE_HEALTHCHECK_HASH":
        native_module = bundle_obj.get("native_module")
        if not isinstance(native_module, dict):
            return False
        value = str(native_module.get("healthcheck_receipt_hash", "")).strip()
        return _is_sha256(value)
    if mode == "REQUIRE_BINARY_ARTIFACT":
        return bool(binary_delta_b) and int(threshold_u64) <= 1
    if mode == "REQUIRE_PATCH_DELTA":
        return int(nontrivial_delta_u64) >= int(max(0, threshold_u64))
    if mode == "REQUIRE_POLICY_ARTIFACT":
        if not policy_artifact_relpath:
            return False
        rel = Path(policy_artifact_relpath)
        if rel.is_absolute() or ".." in rel.parts:
            return False
        candidate = (promotion_dir / rel).resolve()
        return candidate.exists() and candidate.is_file()
    return False


def _write_utility_proof_receipt(
    *,
    tick_u64: int,
    dispatch_ctx: dict[str, Any],
    capability_id: str,
    declared_class: str,
    candidate_bundle_hash: str,
    baseline_ref_hash: str,
    correctness_ok_b: bool,
    utility_ok_b: bool,
    signal_a_ok_b: bool,
    signal_b_ok_b: bool,
    reason_code: str,
    effect_class: str,
    probe_suite_id: str,
    stress_probe_suite_id: str,
    runtime_stats_source_id: str,
    runtime_stats_hash: str | None,
    candidate_bundle_present_b: bool,
    probe_executed_b: bool,
    utility_metrics: dict[str, Any],
    utility_thresholds: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    out_dir = Path(dispatch_ctx["dispatch_dir"]) / "promotion"
    out_dir.mkdir(parents=True, exist_ok=True)
    primary_probe_input_hash = canon_hash_obj_v19(
        {
            "probe_suite_id": probe_suite_id,
            "baseline_ref_hash": baseline_ref_hash,
            "candidate_bundle_hash": candidate_bundle_hash,
            "utility_metrics": utility_metrics,
        }
    )
    primary_probe_output_hash = canon_hash_obj_v19(
        {
            "signal_a_ok_b": bool(signal_a_ok_b),
            "reason_code": reason_code,
        }
    )
    stress_probe_input_hash = canon_hash_obj_v19(
        {
            "stress_probe_suite_id": stress_probe_suite_id,
            "baseline_ref_hash": baseline_ref_hash,
            "candidate_bundle_hash": candidate_bundle_hash,
            "utility_thresholds": utility_thresholds,
        }
    )
    stress_probe_output_hash = canon_hash_obj_v19(
        {
            "signal_b_ok_b": bool(signal_b_ok_b),
            "reason_code": reason_code,
        }
    )
    payload = {
        "schema_name": "utility_proof_receipt_v1",
        "schema_version": "v19_0",
        "receipt_id": _SHA256_ZERO,
        "tick_u64": int(tick_u64),
        "capability_id": str(capability_id),
        "candidate_bundle_hash": candidate_bundle_hash,
        "baseline_ref_hash": baseline_ref_hash,
        "probe_suite_id": str(probe_suite_id),
        "stress_probe_suite_id": str(stress_probe_suite_id),
        "runtime_stats_source_id": str(runtime_stats_source_id),
        "runtime_stats_hash": runtime_stats_hash,
        "candidate_bundle_present_b": bool(candidate_bundle_present_b),
        "probe_executed_b": bool(probe_executed_b),
        "correctness_ok_b": bool(correctness_ok_b),
        "utility_ok_b": bool(utility_ok_b),
        "signal_a_ok_b": bool(signal_a_ok_b),
        "signal_b_ok_b": bool(signal_b_ok_b),
        "utility_metrics": dict(utility_metrics),
        "utility_thresholds": dict(utility_thresholds),
        "reason_code": str(reason_code),
        "declared_class": str(declared_class),
        "effect_class": str(effect_class),
        "primary_probe": {
            "input_hash": primary_probe_input_hash,
            "output_hash": primary_probe_output_hash,
        },
        "stress_probe": {
            "input_hash": stress_probe_input_hash,
            "output_hash": stress_probe_output_hash,
        },
    }
    validate_schema(payload, "utility_proof_receipt_v1")
    _, receipt, digest = write_hashed_json(out_dir, "utility_proof_receipt_v1.json", payload, id_field="receipt_id")
    validate_schema(receipt, "utility_proof_receipt_v1")
    return receipt, digest


def _write_promotion_receipt_v19(
    *,
    tick_u64: int,
    dispatch_ctx: dict[str, Any],
    promotion_bundle_hash: str,
    status: str,
    reason: str | None,
    route: str,
    active_manifest_hash_after: str | None,
    utility_proof_hash: str | None,
    declared_class: str,
    effect_class: str,
    replay_binding_v1: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    out_dir = Path(dispatch_ctx["dispatch_dir"]) / "promotion"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "omega_promotion_receipt_v1",
        "receipt_id": _SHA256_ZERO,
        "tick_u64": int(tick_u64),
        "promotion_bundle_hash": promotion_bundle_hash if _is_sha256(promotion_bundle_hash) else _SHA256_ZERO,
        "execution_mode": resolve_execution_mode(),
        "meta_core_verifier_fingerprint": v18_promoter._meta_fingerprint(),
        "native_module": None,
        "native_runtime_contract_hash": None,
        "native_healthcheck_vectors_hash": None,
        "utility_proof_hash": utility_proof_hash if isinstance(utility_proof_hash, str) and _is_sha256(utility_proof_hash) else None,
        "declared_class": declared_class if declared_class in _DECLARED_CLASSES else "UNCLASSIFIED",
        "effect_class": effect_class,
        "result": {
            "status": status,
            "reason_code": reason,
            "route": route,
        },
        "active_manifest_hash_after": active_manifest_hash_after if _is_sha256(active_manifest_hash_after) else None,
    }
    if isinstance(replay_binding_v1, dict):
        payload["replay_binding_v1"] = dict(replay_binding_v1)
    require_no_absolute_paths(payload)
    _, receipt, digest = write_hashed_json(out_dir, "omega_promotion_receipt_v1.json", payload, id_field="receipt_id")
    validate_v18_schema(receipt, "omega_promotion_receipt_v1")
    return receipt, digest


def _augment_promotion_receipt_with_effect(
    *,
    dispatch_ctx: dict[str, Any],
    promotion_receipt: dict[str, Any],
    utility_proof_hash: str | None,
    declared_class: str,
    effect_class: str,
    replay_binding_v1: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    out_dir = Path(dispatch_ctx["dispatch_dir"]) / "promotion"
    payload = dict(promotion_receipt)
    payload["utility_proof_hash"] = utility_proof_hash if isinstance(utility_proof_hash, str) and _is_sha256(utility_proof_hash) else None
    payload["declared_class"] = declared_class if declared_class in _DECLARED_CLASSES else "UNCLASSIFIED"
    payload["effect_class"] = effect_class
    if isinstance(replay_binding_v1, dict):
        payload["replay_binding_v1"] = dict(replay_binding_v1)
    result = dict(payload.get("result") or {})
    route = str(result.get("route", "")).strip().upper()
    if route not in {"ACTIVE", "SHADOW", "NONE"}:
        route = "ACTIVE" if str(result.get("status", "")).strip() == "PROMOTED" else "NONE"
    result["route"] = route
    payload["result"] = result
    require_no_absolute_paths(payload)
    _, receipt, digest = write_hashed_json(out_dir, "omega_promotion_receipt_v1.json", payload, id_field="receipt_id")
    validate_v18_schema(receipt, "omega_promotion_receipt_v1")
    return receipt, digest


def run_subverifier(*, tick_u64: int, dispatch_ctx: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    receipt, digest = v18_promoter.run_subverifier(tick_u64=tick_u64, dispatch_ctx=dispatch_ctx)
    if dispatch_ctx is None or receipt is None:
        return receipt, digest
    status = str((receipt.get("result") or {}).get("status", "")).strip()
    if status != "VALID":
        return receipt, digest

    utility_policy = _load_utility_policy_for_dispatch(dispatch_ctx)
    declared_class = _declared_class_for_capability(dispatch_ctx, utility_policy)
    if declared_class not in _HEAVY_DECLARED_CLASSES:
        return receipt, digest

    bundle_path, _bundle_hash = v18_promoter._find_promotion_bundle(dispatch_ctx)  # type: ignore[attr-defined]
    if bundle_path is None:
        return receipt, digest
    bundle_obj = load_canon_dict(bundle_path)
    patch_bytes = _patch_bytes_for_bundle(bundle_obj=bundle_obj, bundle_path=bundle_path)
    # Always emit a certificate shape, even when patch material is missing,
    # so INSUFFICIENT_NONTRIVIAL_DELTA has deterministic measured evidence.
    nontriviality_cert_v1 = build_shared_nontriviality_cert_v1(
        repo_root=repo_root(),
        patch_bytes=(patch_bytes if patch_bytes is not None else b""),
        archetype_id=None,
    )
    capability_id = _capability_id_from_dispatch(dispatch_ctx)
    if capability_id == _SH1_CAPABILITY_ID:
        cert = dict(nontriviality_cert_v1 or {})
        if not bool(cert.get("wiring_class_ok_b", False)):
            return _rewrite_subverifier_receipt(
                dispatch_ctx=dispatch_ctx,
                receipt=receipt,
                status="INVALID",
                reason_code="VERIFY_ERROR:INSUFFICIENT_NONTRIVIAL_DELTA",
                nontriviality_cert_v1=cert if cert else None,
            )
        return _rewrite_subverifier_receipt(
            dispatch_ctx=dispatch_ctx,
            receipt=receipt,
            status="VALID",
            reason_code=(receipt.get("result") or {}).get("reason_code"),
            nontriviality_cert_v1=cert,
        )

    active_binding = v18_promoter._read_active_binding(v18_promoter._meta_core_root())  # type: ignore[attr-defined]
    binary_delta_b = _binary_artifact_delta_present(bundle_obj=bundle_obj, active_binding=active_binding)
    nontrivial_delta_u64 = _nontrivial_delta_for_bundle(bundle_obj=bundle_obj, bundle_path=bundle_path)
    if not (binary_delta_b or nontrivial_delta_u64 >= 1):
        return _rewrite_subverifier_receipt(
            dispatch_ctx=dispatch_ctx,
            receipt=receipt,
            status="INVALID",
            reason_code="VERIFY_ERROR:INSUFFICIENT_NONTRIVIAL_DELTA",
            nontriviality_cert_v1=nontriviality_cert_v1,
        )
    return receipt, digest


def run_promotion(
    *,
    tick_u64: int,
    dispatch_ctx: dict[str, Any] | None,
    subverifier_receipt: dict[str, Any] | None,
    allowlists: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    if dispatch_ctx is None:
        return None, None

    utility_policy = _load_utility_policy_for_dispatch(dispatch_ctx)
    declared_class = _declared_class_for_capability(dispatch_ctx, utility_policy)
    capability_id = _capability_id_from_dispatch(dispatch_ctx)
    replay_binding_v1 = v18_promoter._replay_binding_v1_for_receipt(  # type: ignore[attr-defined]
        dispatch_ctx=dispatch_ctx,
        subverifier_receipt=subverifier_receipt,
    )

    subverifier_status = str((subverifier_receipt or {}).get("result", {}).get("status", "")).strip()
    if subverifier_receipt is None or subverifier_status != "VALID":
        receipt, digest = v18_promoter.run_promotion(
            tick_u64=tick_u64,
            dispatch_ctx=dispatch_ctx,
            subverifier_receipt=subverifier_receipt,
            allowlists=allowlists,
        )
        if receipt is None or digest is None:
            return receipt, digest
        return _augment_promotion_receipt_with_effect(
            dispatch_ctx=dispatch_ctx,
            promotion_receipt=receipt,
            utility_proof_hash=None,
            declared_class=declared_class,
            effect_class="EFFECT_REJECTED",
            replay_binding_v1=replay_binding_v1,
        )

    bundle_path, bundle_hash = v18_promoter._find_promotion_bundle(dispatch_ctx)
    if bundle_path is None:
        receipt, digest = v18_promoter.run_promotion(
            tick_u64=tick_u64,
            dispatch_ctx=dispatch_ctx,
            subverifier_receipt=subverifier_receipt,
            allowlists=allowlists,
        )
        if receipt is None or digest is None:
            return receipt, digest
        effect_class = _compute_effect_class(
            declared_class=declared_class,
            correctness_ok_b=True,
            utility_ok_b=False,
        )
        return _augment_promotion_receipt_with_effect(
            dispatch_ctx=dispatch_ctx,
            promotion_receipt=receipt,
            utility_proof_hash=None,
            declared_class=declared_class,
            effect_class=effect_class,
            replay_binding_v1=replay_binding_v1,
        )

    bundle_obj = load_canon_dict(bundle_path)
    promotion_bundle_hash = bundle_hash or canon_hash_obj(bundle_obj)
    promotion_dir = bundle_path.parent
    axis_gate_context: dict[str, Any] = {
        "axis_gate_required_b": False,
        "axis_gate_exempted_b": False,
        "axis_gate_reason_code": "NONE",
        "axis_gate_axis_id": None,
        "axis_gate_bundle_present_b": False,
        "axis_gate_bundle_sha256": None,
        "axis_gate_checked_relpaths_v1": [],
    }
    axis_bundle_for_meta: dict[str, Any] | None = None

    try:
        axis_gate_context, axis_bundle_for_meta, _ = _axis_gate_context_for_bundle(
            bundle_obj=bundle_obj,
            bundle_path=bundle_path,
        )
        _verify_axis_bundle_gate(
            bundle_obj=bundle_obj,
            bundle_path=bundle_path,
            promotion_dir=promotion_dir,
        )
    except ContinuityV19Error as exc:
        message = str(exc)
        gate_outcome = "SAFE_SPLIT" if message.startswith("SAFE_SPLIT:") else "SAFE_HALT"
        axis_failure_context = dict(axis_gate_context)
        axis_failure_context["axis_gate_reason_code"] = _axis_gate_reason_code_for_failure(
            message=message,
            gate_outcome=gate_outcome,
            fallback=str(axis_gate_context.get("axis_gate_reason_code", "NONE")),
        )
        write_canonical(
            promotion_dir / "axis_gate_failure_v1.json",
            {
                "schema_name": "axis_gate_failure_v1",
                "schema_version": "v19_0",
                "outcome": gate_outcome,
                "detail": message,
                **axis_failure_context,
            },
        )
        receipt, _digest = _write_v18_reject(
            tick_u64=tick_u64,
            dispatch_ctx=dispatch_ctx,
            promotion_bundle_hash=promotion_bundle_hash,
            reason="UNKNOWN",
        )
        return _augment_promotion_receipt_with_effect(
            dispatch_ctx=dispatch_ctx,
            promotion_receipt=receipt,
            utility_proof_hash=None,
            declared_class=declared_class,
            effect_class="EFFECT_REJECTED",
            replay_binding_v1=replay_binding_v1,
        )
    except Exception:
        axis_failure_context = dict(axis_gate_context)
        axis_failure_context["axis_gate_reason_code"] = "SAFE_HALT"
        write_canonical(
            promotion_dir / "axis_gate_failure_v1.json",
            {
                "schema_name": "axis_gate_failure_v1",
                "schema_version": "v19_0",
                "outcome": "SAFE_HALT",
                "detail": "SAFE_HALT:UNKNOWN_EXCEPTION",
                **axis_failure_context,
            },
        )
        receipt, _digest = _write_v18_reject(
            tick_u64=tick_u64,
            dispatch_ctx=dispatch_ctx,
            promotion_bundle_hash=promotion_bundle_hash,
            reason="UNKNOWN",
        )
        return _augment_promotion_receipt_with_effect(
            dispatch_ctx=dispatch_ctx,
            promotion_receipt=receipt,
            utility_proof_hash=None,
            declared_class=declared_class,
            effect_class="EFFECT_REJECTED",
            replay_binding_v1=replay_binding_v1,
        )

    meta_core_root = v18_promoter._meta_core_root()  # type: ignore[attr-defined]
    active_binding = v18_promoter._read_active_binding(meta_core_root)  # type: ignore[attr-defined]
    baseline_ref_hash = _baseline_ref_hash(meta_core_root, active_binding)
    runtime_stats_payload, runtime_stats_hash = _load_latest_runtime_stats(dispatch_ctx)
    runtime_stats_source_id = str((utility_policy or {}).get("runtime_stats_source_id", RUNTIME_STATS_SOURCE_ID)).strip() or RUNTIME_STATS_SOURCE_ID
    observed_runtime_source_id = str((runtime_stats_payload or {}).get("runtime_stats_source_id", runtime_stats_source_id)).strip() or runtime_stats_source_id
    runtime_source_match_b = runtime_stats_source_id == observed_runtime_source_id

    binary_delta_b = _binary_artifact_delta_present(bundle_obj=bundle_obj, active_binding=active_binding)
    nontrivial_delta_u64 = _nontrivial_delta_for_bundle(bundle_obj=bundle_obj, bundle_path=bundle_path)
    candidate_bundle_present_b, _candidate_bundle_path = _candidate_bundle_present(
        dispatch_ctx=dispatch_ctx,
        promotion_bundle_hash=promotion_bundle_hash,
    )
    runtime_total_work_units_u64 = int((runtime_stats_payload or {}).get("total_work_units_u64", 0))
    baseline_work_units_u64 = _baseline_work_units_for_capability(
        dispatch_ctx=dispatch_ctx,
        capability_id=capability_id,
        baseline_ref_hash=baseline_ref_hash,
    )

    heavy_policy = _heavy_policy_for_capability(
        utility_policy,
        capability_id,
        dispatch_ctx=dispatch_ctx,
    )
    probe_suite_id = str((heavy_policy or {}).get("probe_suite_id", "utility_probe_suite_default_v1"))
    stress_probe_suite_id = str((heavy_policy or {}).get("stress_probe_suite_id", "utility_stress_probe_suite_default_v1"))
    primary_signal = str((heavy_policy or {}).get("primary_signal", "NONTRIVIAL_DELTA"))
    primary_threshold_u64 = int((heavy_policy or {}).get("primary_threshold_u64", 1))
    stress_signal = str((heavy_policy or {}).get("stress_signal", "REQUIRE_PATCH_DELTA"))
    stress_threshold_u64 = int((heavy_policy or {}).get("stress_threshold_u64", 1))
    policy_artifact_relpath = str((heavy_policy or {}).get("policy_artifact_relpath", "")).strip() or None
    require_hard_task_gain_b_raw = (heavy_policy or {}).get("require_hard_task_gain_b")
    require_hard_task_gain_b = (
        bool(require_hard_task_gain_b_raw) if isinstance(require_hard_task_gain_b_raw, bool) else True
    )
    hard_task_required_gain_count_u64 = max(1, int((heavy_policy or {}).get("hard_task_min_gain_count_u64", 1)))
    hard_task_observation = _hard_task_observation_deltas(dispatch_ctx)
    hard_task_delta_by_metric_raw = hard_task_observation.get("delta_by_metric")
    hard_task_delta_by_metric = (
        dict(hard_task_delta_by_metric_raw) if isinstance(hard_task_delta_by_metric_raw, dict) else {}
    )
    hard_task_code_delta_q32 = int(hard_task_delta_by_metric.get("hard_task_code_correctness_q32", 0))
    hard_task_performance_delta_q32 = int(hard_task_delta_by_metric.get("hard_task_performance_q32", 0))
    hard_task_reasoning_delta_q32 = int(hard_task_delta_by_metric.get("hard_task_reasoning_q32", 0))
    hard_task_suite_delta_q32 = int(hard_task_delta_by_metric.get("hard_task_suite_score_q32", 0))
    hard_task_prediction = _selected_precheck_hard_task_prediction(dispatch_ctx)
    predicted_hard_task_delta_q32 = int(hard_task_prediction.get("predicted_hard_task_delta_q32", 0))
    predicted_hard_task_baseline_score_q32 = int(
        hard_task_prediction.get("predicted_hard_task_baseline_score_q32", 0)
    )
    predicted_hard_task_patched_score_q32 = int(
        hard_task_prediction.get("predicted_hard_task_patched_score_q32", 0)
    )
    hard_task_baseline_init_b = bool(hard_task_observation.get("baseline_init_b", False))
    hard_task_prev_score_q32 = int(hard_task_observation.get("prev_score_q32", 0))
    effective_hard_task_delta_q32 = 0
    if not hard_task_baseline_init_b:
        effective_hard_task_delta_q32 = int(max(hard_task_suite_delta_q32, predicted_hard_task_delta_q32))
    hard_task_gain_count_u64 = max(0, int(hard_task_observation.get("gain_count_u64", 0)))
    hard_task_any_gain_b = (not hard_task_baseline_init_b) and (
        int(hard_task_gain_count_u64) >= int(hard_task_required_gain_count_u64)
    )
    if (not hard_task_baseline_init_b) and int(predicted_hard_task_delta_q32) > 0:
        hard_task_any_gain_b = True

    signal_a_ok_b = True
    signal_b_ok_b = True
    utility_ok_b = True
    utility_reason_code = "UTILITY_OK"
    hard_task_ok_b = True

    if declared_class in _HEAVY_DECLARED_CLASSES:
        if not runtime_source_match_b:
            signal_a_ok_b = False
            signal_b_ok_b = False
            utility_ok_b = False
            utility_reason_code = "RUNTIME_STATS_SOURCE_MISMATCH"
        elif not isinstance(heavy_policy, dict):
            signal_a_ok_b = False
            signal_b_ok_b = False
            utility_ok_b = False
            utility_reason_code = "POLICY_MISSING"
        else:
            signal_a_ok_b = _signal_from_policy(
                signal_mode=primary_signal,
                threshold_u64=primary_threshold_u64,
                binary_delta_b=binary_delta_b,
                nontrivial_delta_u64=nontrivial_delta_u64,
                runtime_total_work_units_u64=runtime_total_work_units_u64,
                baseline_work_units_u64=baseline_work_units_u64,
                bundle_obj=bundle_obj,
                policy_artifact_relpath=policy_artifact_relpath,
                promotion_dir=promotion_dir,
            )
            signal_b_ok_b = _signal_from_policy(
                signal_mode=stress_signal,
                threshold_u64=stress_threshold_u64,
                binary_delta_b=binary_delta_b,
                nontrivial_delta_u64=nontrivial_delta_u64,
                runtime_total_work_units_u64=runtime_total_work_units_u64,
                baseline_work_units_u64=baseline_work_units_u64,
                bundle_obj=bundle_obj,
                policy_artifact_relpath=policy_artifact_relpath,
                promotion_dir=promotion_dir,
            )
            utility_ok_b = bool(signal_a_ok_b and signal_b_ok_b)
            utility_reason_code = "UTILITY_OK" if utility_ok_b else "NO_UTILITY_GAIN"
            if str(primary_signal).strip().upper() == "WORK_UNITS_REDUCTION" and baseline_work_units_u64 is None:
                utility_reason_code = "PROBE_MISSING"
            if require_hard_task_gain_b:
                hard_task_ok_b = bool(hard_task_any_gain_b)
                utility_ok_b = bool(utility_ok_b and hard_task_ok_b)
                if not utility_ok_b and utility_reason_code == "UTILITY_OK":
                    utility_reason_code = "NO_UTILITY_GAIN"

    utility_metrics = {
        "binary_artifact_delta_present_b": bool(binary_delta_b),
        "non_ws_non_comment_delta_u64": int(nontrivial_delta_u64),
        "runtime_stats_source_match_b": bool(runtime_source_match_b),
        "runtime_total_work_units_u64": int(runtime_total_work_units_u64),
        "baseline_work_units_u64": (int(baseline_work_units_u64) if baseline_work_units_u64 is not None else None),
        "hard_task_observation_hash": (
            str(hard_task_observation.get("observation_hash"))
            if isinstance(hard_task_observation.get("observation_hash"), str)
            else None
        ),
        "hard_task_previous_observation_hash": (
            str(hard_task_observation.get("previous_observation_hash"))
            if isinstance(hard_task_observation.get("previous_observation_hash"), str)
            else None
        ),
        "hard_task_code_correctness_delta_q32": int(hard_task_code_delta_q32),
        "hard_task_performance_delta_q32": int(hard_task_performance_delta_q32),
        "hard_task_reasoning_delta_q32": int(hard_task_reasoning_delta_q32),
        "hard_task_suite_score_delta_q32": int(hard_task_suite_delta_q32),
        "hard_task_delta_q32": int(effective_hard_task_delta_q32),
        "predicted_hard_task_delta_q32": int(predicted_hard_task_delta_q32),
        "predicted_hard_task_baseline_score_q32": int(predicted_hard_task_baseline_score_q32),
        "predicted_hard_task_patched_score_q32": int(predicted_hard_task_patched_score_q32),
        "j_delta_q32_i64": int(effective_hard_task_delta_q32),
        "hard_task_prev_score_q32": int(hard_task_prev_score_q32),
        "hard_task_baseline_init_b": bool(hard_task_baseline_init_b),
        "hard_task_gain_count_u64": int(hard_task_gain_count_u64),
        "hard_task_any_gain_b": bool(hard_task_any_gain_b),
        "hard_task_gate_ok_b": bool(hard_task_ok_b),
    }
    utility_thresholds = {
        "primary_signal": str(primary_signal),
        "primary_threshold_u64": int(primary_threshold_u64),
        "stress_signal": str(stress_signal),
        "stress_threshold_u64": int(stress_threshold_u64),
        "require_hard_task_gain_b": bool(require_hard_task_gain_b),
        "hard_task_min_gain_count_u64": int(hard_task_required_gain_count_u64),
    }

    effect_class = _compute_effect_class(
        declared_class=declared_class,
        correctness_ok_b=True,
        utility_ok_b=utility_ok_b,
    )
    _utility_receipt, utility_proof_hash = _write_utility_proof_receipt(
        tick_u64=tick_u64,
        dispatch_ctx=dispatch_ctx,
        capability_id=capability_id,
        declared_class=declared_class if declared_class in _DECLARED_CLASSES else "UNCLASSIFIED",
        candidate_bundle_hash=promotion_bundle_hash if _is_sha256(promotion_bundle_hash) else _SHA256_ZERO,
        baseline_ref_hash=baseline_ref_hash,
        correctness_ok_b=True,
        utility_ok_b=utility_ok_b,
        signal_a_ok_b=signal_a_ok_b,
        signal_b_ok_b=signal_b_ok_b,
        reason_code=utility_reason_code,
        effect_class=effect_class,
        probe_suite_id=probe_suite_id,
        stress_probe_suite_id=stress_probe_suite_id,
        runtime_stats_source_id=runtime_stats_source_id,
        runtime_stats_hash=runtime_stats_hash,
        candidate_bundle_present_b=bool(candidate_bundle_present_b),
        probe_executed_b=True,
        utility_metrics=utility_metrics,
        utility_thresholds=utility_thresholds,
    )

    if declared_class in _HEAVY_DECLARED_CLASSES and not utility_ok_b:
        return _write_promotion_receipt_v19(
            tick_u64=tick_u64,
            dispatch_ctx=dispatch_ctx,
            promotion_bundle_hash=promotion_bundle_hash,
            status="SKIPPED",
            reason="NO_UTILITY_GAIN_SHADOW",
            route="SHADOW",
            active_manifest_hash_after=None,
            utility_proof_hash=utility_proof_hash,
            declared_class=declared_class,
            effect_class="EFFECT_HEAVY_NO_UTILITY",
            replay_binding_v1=replay_binding_v1,
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
        receipt, digest = v18_promoter.run_promotion(
            tick_u64=tick_u64,
            dispatch_ctx=dispatch_ctx,
            subverifier_receipt=subverifier_receipt,
            allowlists=allowlists,
        )
        if receipt is None or digest is None:
            return receipt, digest
        promotion_status = str((receipt.get("result") or {}).get("status", "")).strip()
        if declared_class in _HEAVY_DECLARED_CLASSES:
            # Heavy utility success is counted as EFFECT_HEAVY_OK even when CCAP
            # integration rejects promotion; rejection reasons remain explicit.
            final_effect_class = "EFFECT_HEAVY_OK" if bool(utility_ok_b) else "EFFECT_REJECTED"
        elif promotion_status == "REJECTED":
            final_effect_class = "EFFECT_REJECTED"
        elif declared_class == "BASELINE_CORE":
            final_effect_class = "EFFECT_BASELINE_CORE_OK"
        elif declared_class == "MAINTENANCE":
            final_effect_class = "EFFECT_MAINTENANCE_OK"
        else:
            final_effect_class = "EFFECT_REJECTED"
        return _augment_promotion_receipt_with_effect(
            dispatch_ctx=dispatch_ctx,
            promotion_receipt=receipt,
            utility_proof_hash=utility_proof_hash,
            declared_class=declared_class,
            effect_class=final_effect_class,
            replay_binding_v1=replay_binding_v1,
        )
    finally:
        v18_promoter._build_meta_core_promotion_bundle = original_build_meta_bundle


__all__ = ["run_promotion", "run_subverifier"]
