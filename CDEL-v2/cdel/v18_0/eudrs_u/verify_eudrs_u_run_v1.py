"""Fail-closed subverifier for EUDRS-U campaign runs (v1).

In v1 this verifier treats the promotion summary as the entrypoint and validates
all referenced content-addressed artifacts and the staged registry tree.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..omega_common_v1 import OmegaV18Error, fail, require_no_absolute_paths
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, require_safe_relpath_v1, verify_artifact_ref_v1
from .eudrs_u_common_v1 import EUDRS_U_EVIDENCE_DIR_REL
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical
from .verify_eudrs_u_promotion_v1 import _load_single_summary, _resolve_state_dir, verify as _verify_promotion
from .verify_qxrl_v1 import verify_qxrl_v1


def _find_single_json_by_schema_id(*, directory: Path, schema_id: str) -> tuple[Path, dict[str, Any]] | None:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(directory.glob("*.json"), key=lambda p: p.as_posix()):
        try:
            obj = gcj1_loads_and_verify_canonical(path.read_bytes())
        except Exception:  # noqa: BLE001
            continue
        if isinstance(obj, dict) and str(obj.get("schema_id", "")).strip() == str(schema_id):
            matches.append((path, dict(obj)))
    if not matches:
        return None
    if len(matches) != 1:
        fail("SCHEMA_FAIL")
    return matches[0]


def _write_evidence_receipt(*, state_root: Path, filename: str, payload: dict[str, Any]) -> None:
    out_dir = state_root / EUDRS_U_EVIDENCE_DIR_REL
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / filename).write_bytes(gcj1_canon_bytes(payload))


def _find_json_path_by_id_and_type(*, root: Path, artifact_id: str, artifact_type: str) -> Path:
    if not isinstance(artifact_id, str) or not artifact_id.startswith("sha256:") or len(artifact_id) != len("sha256:") + 64:
        fail("SCHEMA_FAIL")
    hex64 = artifact_id.split(":", 1)[1]
    filename = f"sha256_{hex64}.{artifact_type}.json"
    matches = sorted([p for p in Path(root).resolve().rglob(filename) if p.is_file()], key=lambda p: p.as_posix())
    if len(matches) != 1:
        fail("MISSING_STATE_INPUT")
    return matches[0]


def verify(state_dir: Path, *, mode: str = "full") -> str:
    # Phase 1: promotion summary + staged registry tree integrity checks.
    verdict = _verify_promotion(state_dir, mode=mode)
    if verdict != "VALID":
        fail("SCHEMA_FAIL")

    # Phase 4: QXRL replay verification (WRoot update + eval scorecard binding).
    state_root = _resolve_state_dir(state_dir)
    evidence_dir = state_root / EUDRS_U_EVIDENCE_DIR_REL
    _summary_path, summary = _load_single_summary(evidence_dir)
    require_no_absolute_paths(summary)

    staged_registry_tree_rel = require_safe_relpath_v1(summary.get("staged_registry_tree_relpath"))
    staged_registry_tree_abs = (state_root / staged_registry_tree_rel).resolve()
    if not staged_registry_tree_abs.exists() or not staged_registry_tree_abs.is_dir():
        fail("MISSING_STATE_INPUT")

    proposed_root_tuple_ref = require_artifact_ref_v1(summary.get("proposed_root_tuple_ref"))
    root_tuple_path = verify_artifact_ref_v1(
        artifact_ref=proposed_root_tuple_ref,
        base_dir=state_root,
        expected_relpath_prefix=f"{staged_registry_tree_rel}/polymath/registry/eudrs_u/roots/",
    )
    root_tuple_obj = gcj1_loads_and_verify_canonical(root_tuple_path.read_bytes())
    if not isinstance(root_tuple_obj, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(root_tuple_obj)

    sroot_ref = require_artifact_ref_v1(root_tuple_obj.get("sroot"))
    sroot_path = verify_artifact_ref_v1(artifact_ref=sroot_ref, base_dir=staged_registry_tree_abs, expected_relpath_prefix="polymath/registry/eudrs_u/")
    system_manifest_obj = gcj1_loads_and_verify_canonical(sroot_path.read_bytes())
    if not isinstance(system_manifest_obj, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(system_manifest_obj)

    det_ref = require_artifact_ref_v1(root_tuple_obj.get("determinism_cert"))
    det_path = verify_artifact_ref_v1(artifact_ref=det_ref, base_dir=staged_registry_tree_abs, expected_relpath_prefix="polymath/registry/eudrs_u/")
    determinism_cert_obj = gcj1_loads_and_verify_canonical(det_path.read_bytes())
    if not isinstance(determinism_cert_obj, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(determinism_cert_obj)

    def _registry_loader(ref: dict[str, str]) -> bytes:
        aref = require_artifact_ref_v1(ref)
        path = verify_artifact_ref_v1(artifact_ref=aref, base_dir=staged_registry_tree_abs, expected_relpath_prefix="polymath/registry/eudrs_u/")
        return path.read_bytes()

    ok, reason = verify_qxrl_v1(
        root_tuple_obj=dict(root_tuple_obj),
        system_manifest_obj=dict(system_manifest_obj),
        determinism_cert_obj=dict(determinism_cert_obj),
        registry_loader=_registry_loader,
        mode=str(mode),
    )
    if not ok:
        fail(str(reason))

    # Stage 3 (vision->QXRL) gate: run when build-manifest + eval-suite evidence exists.
    stage3_build = _find_single_json_by_schema_id(directory=evidence_dir, schema_id="vision_qxrl_dataset_build_manifest_v1")
    stage3_suite = _find_single_json_by_schema_id(directory=evidence_dir, schema_id="qxrl_perception_eval_suite_v1")
    if stage3_build is not None and stage3_suite is not None:
        from .verify_vision_stage3_v1 import verify as verify_stage3

        _build_path, build_obj = stage3_build
        suite_path, _suite_obj = stage3_suite

        config_ref = require_artifact_ref_v1(build_obj.get("config_ref"))
        listing_ref = require_artifact_ref_v1(build_obj.get("item_listing_ref"))
        dataset_ref = require_artifact_ref_v1(build_obj.get("produced_qxrl_dataset_manifest_ref"))

        config_path = verify_artifact_ref_v1(artifact_ref=config_ref, base_dir=state_root)
        listing_path = verify_artifact_ref_v1(artifact_ref=listing_ref, base_dir=state_root)
        dataset_path = verify_artifact_ref_v1(artifact_ref=dataset_ref, base_dir=state_root)

        qxrl_bind = system_manifest_obj.get("qxrl")
        if not isinstance(qxrl_bind, dict):
            fail("SCHEMA_FAIL")
        eval_ref = require_artifact_ref_v1(qxrl_bind.get("eval_manifest_ref"))
        eval_path = verify_artifact_ref_v1(
            artifact_ref=eval_ref,
            base_dir=staged_registry_tree_abs,
            expected_relpath_prefix="polymath/registry/eudrs_u/",
        )
        eval_obj = gcj1_loads_and_verify_canonical(eval_path.read_bytes())
        if not isinstance(eval_obj, dict):
            fail("SCHEMA_FAIL")
        scorecard_ref = require_artifact_ref_v1(eval_obj.get("scorecard_ref"))
        scorecard_path = verify_artifact_ref_v1(
            artifact_ref=scorecard_ref,
            base_dir=staged_registry_tree_abs,
            expected_relpath_prefix="polymath/registry/eudrs_u/",
        )

        receipt = verify_stage3(
            state_dir=state_root,
            item_listing_path=listing_path,
            dataset_config_path=config_path,
            qxrl_dataset_manifest_path=dataset_path,
            perception_eval_suite_path=suite_path,
            candidate_scorecard_path=scorecard_path,
            baseline_scorecard_path=None,
        )
        _write_evidence_receipt(state_root=state_root, filename="vision_stage3_verify_receipt_v1.json", payload=receipt)

    # Stage 4 (vision world model + DMPL) gate: run when suite evidence exists.
    stage4_suite = _find_single_json_by_schema_id(directory=evidence_dir, schema_id="vision_world_model_eval_suite_v1")
    if stage4_suite is not None:
        from .verify_vision_stage4_v1 import verify as verify_stage4

        suite_path, _suite_obj = stage4_suite
        transition_listing = _find_single_json_by_schema_id(directory=evidence_dir, schema_id="vision_transition_listing_v1")
        transition_listing_path = transition_listing[0] if transition_listing is not None else None

        stage1_run_manifest_paths: list[Path] = []
        stage1_list_path = evidence_dir / "vision_stage4_run_manifest_relpaths_v1.txt"
        if stage1_list_path.exists() and stage1_list_path.is_file():
            lines = [ln.strip() for ln in stage1_list_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            for ln in lines:
                rel = require_safe_relpath_v1(ln, reason="SCHEMA_FAIL")
                p = (state_root / rel).resolve()
                try:
                    _ = p.relative_to(state_root.resolve())
                except Exception:
                    fail("SCHEMA_FAIL")
                if not p.exists() or not p.is_file():
                    fail("MISSING_STATE_INPUT")
                stage1_run_manifest_paths.append(p)

        qxwmr_bind = system_manifest_obj.get("qxwmr")
        qxrl_bind = system_manifest_obj.get("qxrl")
        if not isinstance(qxwmr_bind, dict) or not isinstance(qxrl_bind, dict):
            fail("SCHEMA_FAIL")

        qxrl_model_ref = require_artifact_ref_v1(qxrl_bind.get("model_manifest_ref"))
        qxrl_model_path = verify_artifact_ref_v1(
            artifact_ref=qxrl_model_ref,
            base_dir=staged_registry_tree_abs,
            expected_relpath_prefix="polymath/registry/eudrs_u/",
        )
        wroot_path = verify_artifact_ref_v1(
            artifact_ref=require_artifact_ref_v1(root_tuple_obj.get("wroot")),
            base_dir=staged_registry_tree_abs,
            expected_relpath_prefix="polymath/registry/eudrs_u/",
        )
        wm_path = verify_artifact_ref_v1(
            artifact_ref=require_artifact_ref_v1(qxwmr_bind.get("world_model_manifest_ref")),
            base_dir=staged_registry_tree_abs,
            expected_relpath_prefix="polymath/registry/eudrs_u/",
        )
        wm_eval_path = verify_artifact_ref_v1(
            artifact_ref=require_artifact_ref_v1(qxwmr_bind.get("eval_manifest_ref")),
            base_dir=staged_registry_tree_abs,
            expected_relpath_prefix="polymath/registry/eudrs_u/",
        )

        dmpl_evidence = summary.get("dmpl_evidence")
        if not isinstance(dmpl_evidence, dict):
            fail("SCHEMA_FAIL")
        train_evidence = dmpl_evidence.get("train_evidence")
        if not isinstance(train_evidence, dict):
            fail("SCHEMA_FAIL")
        train_run_ref = require_artifact_ref_v1(train_evidence.get("dmpl_train_run_ref"))
        train_trace_ref = require_artifact_ref_v1(train_evidence.get("dmpl_train_trace_ref"))
        train_receipt_ref = require_artifact_ref_v1(train_evidence.get("dmpl_train_receipt_ref"))
        train_run_path = verify_artifact_ref_v1(artifact_ref=train_run_ref, base_dir=state_root)
        train_trace_path = verify_artifact_ref_v1(artifact_ref=train_trace_ref, base_dir=state_root)
        train_receipt_path = verify_artifact_ref_v1(artifact_ref=train_receipt_ref, base_dir=state_root)

        train_run_obj = gcj1_loads_and_verify_canonical(train_run_path.read_bytes())
        if not isinstance(train_run_obj, dict):
            fail("SCHEMA_FAIL")
        dataset_pack_id = str(train_run_obj.get("dataset_pack_id", "")).strip()
        dataset_pack_path = _find_json_path_by_id_and_type(root=state_root, artifact_id=dataset_pack_id, artifact_type="dmpl_dataset_pack_v1")

        receipt = verify_stage4(
            state_dir=state_root,
            qxrl_model_manifest_path=qxrl_model_path,
            wroot_path=wroot_path,
            dmpl_dataset_pack_path=dataset_pack_path,
            dmpl_train_run_path=train_run_path,
            dmpl_train_trace_path=train_trace_path,
            dmpl_train_receipt_path=train_receipt_path,
            qxwmr_world_model_manifest_path=wm_path,
            qxwmr_eval_manifest_path=wm_eval_path,
            vision_wm_eval_suite_path=suite_path,
            stage1_run_manifest_paths=stage1_run_manifest_paths,
            vision_transition_listing_path=transition_listing_path,
        )
        _write_evidence_receipt(state_root=state_root, filename="vision_stage4_verify_receipt_v1.json", payload=receipt)
    return "VALID"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="verify_eudrs_u_run_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args(argv)

    try:
        print(verify(Path(args.state_dir), mode=str(args.mode)))
    except OmegaV18Error as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
