"""Verifier for RSI demon v7 recursive ontology attempts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from ..v1_8r.metabolism_v1.eval import _validate_patch_def
from .autonomy import load_translation_inputs
from .constants import meta_identities, require_constants
from .efficiency import efficiency_gate
from .opt_ontology import (
    active_set_ids_from_patches,
    build_active_concepts_from_patches,
    compute_concept_id,
    compute_patch_id,
    evaluate_expr,
    feature_map_from_report,
    normalize_capacity,
    safety_check_concept,
)


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _latest_report(dir_path: Path, prefix: str) -> dict[str, Any]:
    if not dir_path.exists():
        _fail("MISSING_ARTIFACT")
    best_epoch = None
    best_path = None
    for report_path in dir_path.glob(f"{prefix}_epoch_*.json"):
        tail = report_path.stem.split("_epoch_")[-1]
        if not tail.isdigit():
            continue
        idx = int(tail)
        if best_epoch is None or idx > best_epoch:
            best_epoch = idx
            best_path = report_path
    if best_path is None:
        _fail("MISSING_ARTIFACT")
    return load_canon_json(best_path)


def _verify_campaign_pack(state_dir: Path) -> tuple[dict[str, Any], Path]:
    pinned_path = state_dir / "current" / "campaign_pack" / "campaign_pack_used.json"
    if not pinned_path.exists():
        _fail("MISSING_ARTIFACT")
    pinned = load_canon_json(pinned_path)
    if pinned.get("schema") != "rsi_real_demon_campaign_pack_v7":
        _fail("SCHEMA_INVALID")
    if "schema_version" in pinned and int(pinned.get("schema_version", 0)) != 7:
        _fail("SCHEMA_INVALID")

    source_path = _repo_root() / "campaigns" / "rsi_real_recursive_ontology_v2_1_source" / "rsi_real_demon_campaign_pack_v7.json"
    target_path = _repo_root() / "campaigns" / "rsi_real_recursive_ontology_v2_1_target" / "rsi_real_demon_campaign_pack_v7.json"
    candidate_paths = [path for path in (source_path, target_path) if path.exists()]
    pinned_hash = sha256_prefixed(canon_bytes(pinned))
    for path in candidate_paths:
        candidate = load_canon_json(path)
        if sha256_prefixed(canon_bytes(candidate)) == pinned_hash:
            return pinned, path
    _fail("CANON_HASH_MISMATCH")
    return pinned, pinned_path


def _load_active_concept_patches(state_dir: Path) -> list[dict[str, Any]]:
    patches: list[dict[str, Any]] = []
    active_dir = state_dir / "autonomy" / "opt_ontology_v1" / "active_concepts"
    if not active_dir.exists():
        return patches
    for path in sorted(active_dir.glob("*.json")):
        patches.append(load_canon_json(path))
    return patches


def _validate_manifest(manifest: dict[str, Any]) -> None:
    required = {
        "schema",
        "run_id",
        "attempt_id",
        "insertion_index",
        "candidate_rank",
        "generated",
        "manifest_head_hash",
    }
    if set(manifest.keys()) != required:
        _fail("SCHEMA_INVALID")
    if manifest.get("schema") != "autoconcept_manifest_v1":
        _fail("SCHEMA_INVALID")
    generated = manifest.get("generated")
    if not isinstance(generated, list) or len(generated) != 1:
        _fail("SCHEMA_INVALID")
    head = dict(manifest)
    head.pop("manifest_head_hash", None)
    if manifest.get("manifest_head_hash") != sha256_prefixed(canon_bytes(head)):
        _fail("CANON_HASH_MISMATCH")


def _load_concept_patch_from_manifest(state_dir: Path) -> dict[str, Any]:
    manifest_path = state_dir / "autonomy" / "opt_ontology_v1" / "autoconcept_manifest_v1.json"
    if not manifest_path.exists():
        _fail("MISSING_ARTIFACT")
    manifest = load_canon_json(manifest_path)
    _validate_manifest(manifest)
    generated = manifest.get("generated")[0]
    relpath = generated.get("concept_patch_relpath")
    if not isinstance(relpath, str):
        _fail("SCHEMA_INVALID")
    patch_path = state_dir / relpath
    if not patch_path.exists():
        _fail("MISSING_ARTIFACT")
    patch = load_canon_json(patch_path)
    if generated.get("concept_id") != patch.get("concept", {}).get("concept_id"):
        _fail("CANON_HASH_MISMATCH")
    if generated.get("patch_id") != patch.get("patch_id"):
        _fail("CANON_HASH_MISMATCH")
    return patch


def _load_concept_patch_from_pinned(state_dir: Path, opt_concepts_dir: str) -> dict[str, Any]:
    root = state_dir / opt_concepts_dir
    if not root.exists():
        _fail("MISSING_ARTIFACT")
    patches = list(sorted(root.glob("*.json")))
    if len(patches) != 1:
        _fail("SCHEMA_INVALID")
    return load_canon_json(patches[0])


def _validate_concept_patch(patch: dict[str, Any], constants: dict[str, Any]) -> dict[str, Any]:
    if set(patch.keys()) != {"schema", "patch_id", "concept"}:
        _fail("SCHEMA_INVALID")
    if patch.get("schema") != "opt_concept_patch_v1":
        _fail("SCHEMA_INVALID")
    concept = patch.get("concept") if isinstance(patch.get("concept"), dict) else None
    if not isinstance(concept, dict):
        _fail("SCHEMA_INVALID")
    if set(concept.keys()) != {
        "schema",
        "dsl_version",
        "concept_id",
        "created_in_run_id",
        "name",
        "description",
        "output_kind",
        "expr",
    }:
        _fail("SCHEMA_INVALID")
    if concept.get("schema") != "opt_concept_v1":
        _fail("SCHEMA_INVALID")
    if int(concept.get("dsl_version", 0)) != int(constants.get("OPT_DSL_VERSION", 1) or 1):
        _fail("SCHEMA_INVALID")
    if concept.get("output_kind") != "ctx_hash_cache_v1_capacity_policy":
        _fail("SCHEMA_INVALID")
    expected_concept_id = compute_concept_id(concept)
    if concept.get("concept_id") != expected_concept_id:
        _fail("CANON_HASH_MISMATCH")
    expected_patch_id = compute_patch_id(concept)
    if patch.get("patch_id") != expected_patch_id:
        _fail("CANON_HASH_MISMATCH")
    return concept


def _load_single_patch_def(state_dir: Path) -> dict[str, Any]:
    proposals_dir = state_dir / "autonomy" / "metabolism_v1" / "proposals"
    if not proposals_dir.exists():
        _fail("MISSING_ARTIFACT")
    patch_paths = list(sorted(proposals_dir.glob("*.json")))
    if len(patch_paths) != 1:
        _fail("SCHEMA_INVALID")
    return load_canon_json(patch_paths[0])


def _validate_report(report: dict[str, Any]) -> None:
    required = {
        "schema",
        "schema_version",
        "epoch",
        "workvec_base",
        "workvec_patch",
        "work_cost_base",
        "work_cost_patch",
        "rho_met",
        "rho_met_min",
        "efficiency_vector_dominance",
        "efficiency_scalar_gate",
        "efficiency_gate_passed",
    }
    if set(report.keys()) != required:
        _fail("SCHEMA_INVALID")
    if report.get("schema") != "meta_patch_eval_report_v2" or int(report.get("schema_version", 0)) != 2:
        _fail("SCHEMA_INVALID")


def _domain_gate_reason(domain_id: str) -> str:
    if domain_id == "formal_logic_v1":
        return "SOURCE_EFFICIENCY_GATE_FAIL"
    if domain_id == "science_model_v1":
        return "TRANSFER_EFFICIENCY_GATE_FAIL"
    return "SCHEMA_INVALID"


def _expected_rho_min(domain_id: str, constants: dict[str, Any]) -> dict[str, Any]:
    if domain_id == "formal_logic_v1":
        return constants.get("RHO_SOURCE_MIN", {})
    if domain_id == "science_model_v1":
        return constants.get("RHO_TRANSFER_MIN", {})
    return {}


def verify(state_dir: Path) -> tuple[dict[str, Any], int]:
    constants = require_constants()
    meta = meta_identities()
    campaign_pack, pack_path = _verify_campaign_pack(state_dir)

    domain_id = str(campaign_pack.get("domain_id", ""))

    rho_min = campaign_pack.get("efficiency", {}).get("rho_min") if isinstance(campaign_pack.get("efficiency"), dict) else None
    if not isinstance(rho_min, dict):
        _fail("SCHEMA_INVALID")
    expected_rho = _expected_rho_min(domain_id, constants)
    if expected_rho and rho_min != expected_rho:
        _fail("SCHEMA_INVALID")

    proposals = campaign_pack.get("proposals") if isinstance(campaign_pack.get("proposals"), dict) else None
    if not isinstance(proposals, dict):
        _fail("SCHEMA_INVALID")
    opt_concepts_dir = proposals.get("opt_concepts_dir")
    if not isinstance(opt_concepts_dir, str):
        _fail("SCHEMA_INVALID")

    autonomy_cfg = campaign_pack.get("autonomy") if isinstance(campaign_pack.get("autonomy"), dict) else None
    if not isinstance(autonomy_cfg, dict):
        _fail("SCHEMA_INVALID")
    opt_cfg = autonomy_cfg.get("opt_ontology") if isinstance(autonomy_cfg.get("opt_ontology"), dict) else None
    if not isinstance(opt_cfg, dict):
        _fail("SCHEMA_INVALID")
    opt_enabled = bool(opt_cfg.get("enabled"))

    if opt_enabled:
        if opt_concepts_dir != "__AUTOCONCEPT_RUNDIR_V1__":
            _fail("SCHEMA_INVALID")
        patch = _load_concept_patch_from_manifest(state_dir)
    else:
        if opt_concepts_dir == "__AUTOCONCEPT_RUNDIR_V1__":
            _fail("SCHEMA_INVALID")
        manifest_path = state_dir / "autonomy" / "opt_ontology_v1" / "autoconcept_manifest_v1.json"
        if manifest_path.exists():
            _fail("SCHEMA_INVALID")
        patch = _load_concept_patch_from_pinned(state_dir, opt_concepts_dir)

    concept = _validate_concept_patch(patch, constants)

    active_patches = _load_active_concept_patches(state_dir)
    active_ids = active_set_ids_from_patches(active_patches)
    active_concepts = build_active_concepts_from_patches(active_patches)

    safety_check_concept(
        concept,
        constants=constants,
        active_concepts=active_concepts,
        active_set_ids=active_ids,
    )

    patch_def = _load_single_patch_def(state_dir)
    try:
        _validate_patch_def(patch_def, constants, meta)
    except CanonError as exc:
        msg = str(exc)
        if "x-meta" in msg:
            _fail("META_DRIFT")
        if "patch_kind" in msg:
            _fail("INVALID_PATCH_KIND")
        _fail("SCHEMA_INVALID")

    translation_path = campaign_pack.get("translation_inputs_path")
    if not isinstance(translation_path, str):
        _fail("SCHEMA_INVALID")
    pack_root = pack_path.parent
    translation_inputs = load_translation_inputs(pack_root / translation_path)

    report = _latest_report(state_dir / "current" / "metabolism_v1" / "reports", "meta_patch_eval_report_v2")
    _validate_report(report)

    features = feature_map_from_report(report, translation_inputs=translation_inputs)
    cap_raw = evaluate_expr(concept.get("expr"), features=features, active_concepts=active_concepts)
    cap_norm = normalize_capacity(cap_raw, constants)
    applied_capacity = int(patch_def.get("params", {}).get("capacity", 0))
    if applied_capacity != int(cap_norm):
        _fail("NONDETERMINISM")

    workvec_base = report.get("workvec_base")
    workvec_patch = report.get("workvec_patch")
    if not isinstance(workvec_base, dict) or not isinstance(workvec_patch, dict):
        _fail("SCHEMA_INVALID")

    weights = constants.get("WORK_COST_WEIGHTS_V1", {}) if isinstance(constants.get("WORK_COST_WEIGHTS_V1"), dict) else {}
    gate = efficiency_gate(
        workvec_base,
        workvec_patch,
        weights=weights,
        rho_min_num=int(rho_min.get("num", 0) or 0),
        rho_min_den=int(rho_min.get("den", 1) or 1),
    )

    if int(report.get("work_cost_base", -1)) != int(gate.get("work_cost_base", -2)):
        _fail("NONDETERMINISM")
    if int(report.get("work_cost_patch", -1)) != int(gate.get("work_cost_patch", -2)):
        _fail("NONDETERMINISM")
    if report.get("rho_met") != gate.get("rho_met"):
        _fail("NONDETERMINISM")
    if bool(report.get("efficiency_gate_passed")) != bool(gate.get("efficiency_gate_passed")):
        _fail("NONDETERMINISM")

    if not gate.get("efficiency_gate_passed"):
        _fail(_domain_gate_reason(domain_id))

    receipt = {
        "schema": "rsi_demon_receipt_v7",
        "verdict": "VALID",
        "reasons": [],
        "concept_id": concept.get("concept_id"),
        "patch_id": patch.get("patch_id"),
        "cap_norm": int(cap_norm),
        "rho_met": gate.get("rho_met"),
        "work_cost_base": int(gate.get("work_cost_base")),
        "work_cost_patch": int(gate.get("work_cost_patch")),
    }
    epochs = int(campaign_pack.get("epochs", 0) or 0)
    return receipt, epochs


def _write_receipt(state_dir: Path, receipt: dict[str, Any], *, epochs: int) -> None:
    out_path = state_dir / "epochs" / f"epoch_{epochs}" / "diagnostics" / "rsi_demon_receipt_v7.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(canon_bytes(receipt) + b"\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify RSI demon v7 attempt")
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        receipt, epochs = verify(Path(args.state_dir))
        _write_receipt(Path(args.state_dir), receipt, epochs=epochs or 1)
    except Exception as exc:  # noqa: BLE001
        reason = str(exc) if str(exc) else "unknown"
        receipt = {
            "schema": "rsi_demon_receipt_v7",
            "verdict": "INVALID",
            "reasons": [reason],
            "concept_id": "",
            "patch_id": "",
            "cap_norm": 0,
            "rho_met": {"num": 0, "den": 1},
            "work_cost_base": 0,
            "work_cost_patch": 0,
        }
        try:
            _write_receipt(Path(args.state_dir), receipt, epochs=6)
        except Exception:
            pass
        print(f"INVALID: {reason}")
        return

    print("VALID")


if __name__ == "__main__":
    main()
