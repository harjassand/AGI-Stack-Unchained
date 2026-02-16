"""RE2 authoritative verifier for Vision Stage 3 (QXRL, v1).

Stage 3 verification recomputes deterministic QXRL dataset construction from
vision provenance, validates committed segments/root, and enforces perception
UFC/CAC thresholds from deterministic scorecard metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path
from typing import Any

from ..omega_common_v1 import OmegaV18Error, fail, repo_root, require_no_absolute_paths, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, require_safe_relpath_v1, verify_artifact_ref_v1
from .eudrs_u_common_v1 import EUDRS_U_EVIDENCE_DIR_REL, load_active_root_tuple_pointer
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from .eudrs_u_q32ops_v1 import add_sat, mul_q32
from .qxrl_common_v1 import compute_eval_id_config_hash
from .qxrl_eval_v1 import compute_qxrl_eval_scorecard_v1
from .qxrl_forward_qre_v1 import parse_qxrl_model_manifest_v1
from .qxrl_train_replay_v1 import load_and_verify_weights_manifest_v1
from .vision_common_v1 import (
    REASON_VISION3_CAC_FAIL,
    REASON_VISION3_DATASET_BUILD_MISMATCH,
    REASON_VISION3_SCORECARD_MISMATCH,
    REASON_VISION3_UFC_INVALID,
)
from .vision_to_qxrl_tokens_v1 import (
    build_qxrl_examples_from_rows_v1,
    build_qxrl_segments_v1,
    compute_build_root_hash32_hex_v1,
    compute_dataset_root_hash32_hex_from_segments_v1,
    load_and_parse_vision_qxrl_dataset_config_v1,
    load_listing_descriptor_rows_v1,
    parse_vision_qxrl_dataset_config_v1,
)

# Reuse Stage2 provenance checker to enforce Stage2 trust chain in Stage3.
from . import verify_vision_stage2_v1 as _stage2  # noqa: E402


def _load_json_obj(path: Path, *, schema_id: str, reason: str) -> dict[str, Any]:
    raw = path.read_bytes()
    obj = gcj1_loads_and_verify_canonical(raw)
    if not isinstance(obj, dict):
        fail(reason)
    require_no_absolute_paths(obj)
    if str(obj.get("schema_id", "")).strip() != schema_id:
        fail(reason)
    try:
        validate_schema(obj, schema_id)
    except Exception:  # noqa: BLE001
        fail(reason)
    return dict(obj)


def _q32(value: Any, *, reason: str) -> int:
    if not isinstance(value, dict) or set(value.keys()) != {"q"}:
        fail(reason)
    q = value.get("q")
    if not isinstance(q, int):
        fail(reason)
    return int(q)


def _scorecard_ufc_q32(*, scorecard_obj: dict[str, Any], suite_obj: dict[str, Any]) -> int:
    metrics = scorecard_obj.get("metrics")
    if not isinstance(metrics, dict):
        fail(REASON_VISION3_SCORECARD_MISMATCH)
    masked_acc_q32 = _q32(metrics.get("masked_acc_at_1_q32"), reason=REASON_VISION3_SCORECARD_MISMATCH)
    recall_q32 = _q32(metrics.get("recall_at_k_q32"), reason=REASON_VISION3_SCORECARD_MISMATCH)

    metric_mix = suite_obj.get("metric_mix")
    if not isinstance(metric_mix, dict):
        fail(REASON_VISION3_UFC_INVALID)
    w_mask = _q32(metric_mix.get("masked_acc_at_1_weight_q32"), reason=REASON_VISION3_UFC_INVALID)
    w_recall = _q32(metric_mix.get("recall_at_k_weight_q32"), reason=REASON_VISION3_UFC_INVALID)

    part0 = int(mul_q32(int(w_mask), int(masked_acc_q32)))
    part1 = int(mul_q32(int(w_recall), int(recall_q32)))
    return int(add_sat(int(part0), int(part1)))


def _resolve_state_roots(state_dir: Path) -> tuple[Path, Path]:
    state_root = Path(state_dir).resolve()
    if not state_root.exists() or not state_root.is_dir():
        fail("MISSING_STATE_INPUT")
    staged = state_root / "eudrs_u" / "staged_registry_tree"
    if staged.exists() and staged.is_dir():
        return state_root, staged.resolve()
    return state_root, state_root


def _find_single_json_by_schema_id(*, directory: Path, schema_id: str) -> tuple[Path, dict[str, Any]] | None:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(Path(directory).glob("*.json"), key=lambda p: p.as_posix()):
        try:
            obj = gcj1_loads_and_verify_canonical(path.read_bytes())
        except Exception:  # noqa: BLE001
            continue
        if isinstance(obj, dict) and str(obj.get("schema_id", "")).strip() == str(schema_id):
            matches.append((path.resolve(), dict(obj)))
    if not matches:
        return None
    if len(matches) != 1:
        fail(REASON_VISION3_SCORECARD_MISMATCH)
    return matches[0]


def _resolve_candidate_qxrl_context_from_staged(
    *,
    state_root: Path,
    staged_root: Path,
    candidate_scorecard_obj: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    evidence_dir = state_root / EUDRS_U_EVIDENCE_DIR_REL
    summary_match = _find_single_json_by_schema_id(directory=evidence_dir, schema_id="eudrs_u_promotion_summary_v1")
    if summary_match is None:
        fail(REASON_VISION3_SCORECARD_MISMATCH)
    _summary_path, summary_obj = summary_match
    proposed_ref = require_artifact_ref_v1(summary_obj.get("proposed_root_tuple_ref"), reason=REASON_VISION3_SCORECARD_MISMATCH)
    root_path = verify_artifact_ref_v1(
        artifact_ref=proposed_ref,
        base_dir=state_root,
        expected_relpath_prefix="eudrs_u/staged_registry_tree/polymath/registry/eudrs_u/roots/",
    )
    root_obj = gcj1_loads_and_verify_canonical(root_path.read_bytes())
    if not isinstance(root_obj, dict):
        fail(REASON_VISION3_SCORECARD_MISMATCH)
    require_no_absolute_paths(root_obj)

    sroot_ref = require_artifact_ref_v1(root_obj.get("sroot"), reason=REASON_VISION3_SCORECARD_MISMATCH)
    sroot_path = verify_artifact_ref_v1(
        artifact_ref=sroot_ref,
        base_dir=staged_root,
        expected_relpath_prefix="polymath/registry/eudrs_u/",
    )
    system_obj = gcj1_loads_and_verify_canonical(sroot_path.read_bytes())
    if not isinstance(system_obj, dict):
        fail(REASON_VISION3_SCORECARD_MISMATCH)
    require_no_absolute_paths(system_obj)

    qxrl_bind = system_obj.get("qxrl")
    if not isinstance(qxrl_bind, dict):
        fail(REASON_VISION3_SCORECARD_MISMATCH)
    model_ref = require_artifact_ref_v1(qxrl_bind.get("model_manifest_ref"), reason=REASON_VISION3_SCORECARD_MISMATCH)
    eval_ref = require_artifact_ref_v1(qxrl_bind.get("eval_manifest_ref"), reason=REASON_VISION3_SCORECARD_MISMATCH)
    dataset_ref = require_artifact_ref_v1(qxrl_bind.get("dataset_manifest_ref"), reason=REASON_VISION3_SCORECARD_MISMATCH)
    candidate_wroot_ref = require_artifact_ref_v1(root_obj.get("wroot"), reason=REASON_VISION3_SCORECARD_MISMATCH)

    eval_path = verify_artifact_ref_v1(
        artifact_ref=eval_ref,
        base_dir=staged_root,
        expected_relpath_prefix="polymath/registry/eudrs_u/",
    )
    eval_obj = gcj1_loads_and_verify_canonical(eval_path.read_bytes())
    if not isinstance(eval_obj, dict):
        fail(REASON_VISION3_SCORECARD_MISMATCH)
    score_ref = require_artifact_ref_v1(eval_obj.get("scorecard_ref"), reason=REASON_VISION3_SCORECARD_MISMATCH)
    if str(score_ref.get("artifact_id", "")).strip() != str(candidate_scorecard_obj.get("scorecard_id", "")).strip():
        fail(REASON_VISION3_SCORECARD_MISMATCH)

    return dict(model_ref), dict(eval_ref), dict(dataset_ref), dict(candidate_wroot_ref)


def _load_active_wroot_ref() -> dict[str, str]:
    base = repo_root().resolve()
    ptr = load_active_root_tuple_pointer(root=base)
    if ptr is None:
        fail(REASON_VISION3_SCORECARD_MISMATCH)
    active_ref = require_artifact_ref_v1(ptr.get("active_root_tuple"), reason=REASON_VISION3_SCORECARD_MISMATCH)
    root_path = verify_artifact_ref_v1(
        artifact_ref=active_ref,
        base_dir=base,
        expected_relpath_prefix="polymath/registry/eudrs_u/roots/",
    )
    root_obj = gcj1_loads_and_verify_canonical(root_path.read_bytes())
    if not isinstance(root_obj, dict):
        fail(REASON_VISION3_SCORECARD_MISMATCH)
    return dict(require_artifact_ref_v1(root_obj.get("wroot"), reason=REASON_VISION3_SCORECARD_MISMATCH))


def _hybrid_registry_loader(*, staged_root: Path, repo_base: Path):
    def _loader(ref: dict[str, Any]) -> bytes:
        aref = require_artifact_ref_v1(ref, reason=REASON_VISION3_SCORECARD_MISMATCH)
        try:
            p = verify_artifact_ref_v1(
                artifact_ref=aref,
                base_dir=staged_root,
                expected_relpath_prefix="polymath/registry/eudrs_u/",
            )
            return p.read_bytes()
        except OmegaV18Error:
            p = verify_artifact_ref_v1(
                artifact_ref=aref,
                base_dir=repo_base,
                expected_relpath_prefix="polymath/registry/eudrs_u/",
            )
            return p.read_bytes()

    return _loader


def _eval_scorecard_with_weights(
    *,
    model_ref: dict[str, str],
    dataset_ref: dict[str, str],
    eval_obj: dict[str, Any],
    weights_ref: dict[str, str],
    registry_loader,
    examples_override: list[Any] | None = None,
) -> dict[str, Any]:
    model_obj = gcj1_loads_and_verify_canonical(registry_loader(dict(model_ref)))
    dataset_obj = gcj1_loads_and_verify_canonical(registry_loader(dict(dataset_ref)))
    weights_obj = gcj1_loads_and_verify_canonical(registry_loader(dict(weights_ref)))
    if not isinstance(model_obj, dict) or not isinstance(dataset_obj, dict) or not isinstance(weights_obj, dict):
        fail(REASON_VISION3_SCORECARD_MISMATCH)

    model = parse_qxrl_model_manifest_v1(dict(model_obj))

    # Lazy import to avoid circulars in module init path.
    from .qxrl_dataset_v1 import load_and_verify_qxrl_dataset_v1

    examples, dataset_root_hash32 = load_and_verify_qxrl_dataset_v1(
        dataset_manifest_obj=dict(dataset_obj),
        registry_loader=registry_loader,
    )
    examples_use = list(examples_override) if examples_override is not None else list(examples)
    if not examples_use:
        fail(REASON_VISION3_SCORECARD_MISMATCH)
    weights = load_and_verify_weights_manifest_v1(
        weights_manifest_obj=dict(weights_obj),
        registry_loader=registry_loader,
    )

    score_obj, _score_bytes, _score_id, _h_eval_tail = compute_qxrl_eval_scorecard_v1(
        eval_manifest_obj=dict(eval_obj),
        model=model,
        model_manifest_id=str(model_ref.get("artifact_id", "")),
        dataset_manifest_obj=dict(dataset_obj),
        dataset_root_hash32=bytes(dataset_root_hash32),
        examples=list(examples_use),
        weights_manifest_id=str(weights_ref.get("artifact_id", "")),
        weights_manifest=weights,
        registry_loader=registry_loader,
        enforce_floors=False,
    )
    return dict(score_obj)


def _deterministic_holdout_examples(examples: list[Any]) -> list[Any]:
    holdout: list[Any] = []
    for ex in list(examples):
        ex_id = int(getattr(ex, "example_id_u64"))
        h = hashlib.sha256()
        h.update(b"QXRL_STAGE3_HOLDOUT_V1")
        h.update(struct.pack("<Q", ex_id & 0xFFFFFFFFFFFFFFFF))
        if (h.digest()[0] & 1) == 1:
            holdout.append(ex)
    if holdout:
        return holdout
    return list(examples[:1])


def _recompute_baseline_and_robust_delta(
    *,
    state_root: Path,
    staged_root: Path,
    suite_obj: dict[str, Any],
    candidate_scorecard_obj: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    model_ref, eval_ref, dataset_ref, candidate_wroot_ref = _resolve_candidate_qxrl_context_from_staged(
        state_root=state_root,
        staged_root=staged_root,
        candidate_scorecard_obj=candidate_scorecard_obj,
    )
    baseline_wroot_ref = _load_active_wroot_ref()
    loader = _hybrid_registry_loader(staged_root=staged_root, repo_base=repo_root().resolve())

    eval_obj = gcj1_loads_and_verify_canonical(loader(dict(eval_ref)))
    if not isinstance(eval_obj, dict):
        fail(REASON_VISION3_SCORECARD_MISMATCH)

    baseline_scorecard_obj = _eval_scorecard_with_weights(
        model_ref=dict(model_ref),
        dataset_ref=dict(dataset_ref),
        eval_obj=dict(eval_obj),
        weights_ref=dict(baseline_wroot_ref),
        registry_loader=loader,
        examples_override=None,
    )

    # Robust split: deterministic holdout by hashed example ids.
    dataset_obj = gcj1_loads_and_verify_canonical(loader(dict(dataset_ref)))
    if not isinstance(dataset_obj, dict):
        fail(REASON_VISION3_SCORECARD_MISMATCH)
    from .qxrl_dataset_v1 import load_and_verify_qxrl_dataset_v1

    examples_all, _dataset_root_hash32 = load_and_verify_qxrl_dataset_v1(
        dataset_manifest_obj=dict(dataset_obj),
        registry_loader=loader,
    )
    holdout_examples = _deterministic_holdout_examples(list(examples_all))

    eval_holdout_obj = dict(eval_obj)
    eval_holdout_obj["eval_start_index_u64"] = 0
    eval_holdout_obj["eval_example_count_u32"] = int(len(holdout_examples))
    eval_holdout_obj["eval_id"] = compute_eval_id_config_hash(dict(eval_holdout_obj))

    candidate_holdout = _eval_scorecard_with_weights(
        model_ref=dict(model_ref),
        dataset_ref=dict(dataset_ref),
        eval_obj=dict(eval_holdout_obj),
        weights_ref=dict(candidate_wroot_ref),
        registry_loader=loader,
        examples_override=list(holdout_examples),
    )
    baseline_holdout = _eval_scorecard_with_weights(
        model_ref=dict(model_ref),
        dataset_ref=dict(dataset_ref),
        eval_obj=dict(eval_holdout_obj),
        weights_ref=dict(baseline_wroot_ref),
        registry_loader=loader,
        examples_override=list(holdout_examples),
    )

    u_cand_rob = _scorecard_ufc_q32(scorecard_obj=candidate_holdout, suite_obj=suite_obj)
    u_base_rob = _scorecard_ufc_q32(scorecard_obj=baseline_holdout, suite_obj=suite_obj)
    delta_rob_q32 = int(add_sat(int(u_cand_rob), int(-u_base_rob)))
    return dict(baseline_scorecard_obj), int(delta_rob_q32)


def verify(
    state_dir: Path,
    *,
    item_listing_path: Path,
    dataset_config_path: Path,
    qxrl_dataset_manifest_path: Path,
    perception_eval_suite_path: Path,
    candidate_scorecard_path: Path,
    baseline_scorecard_path: Path | None,
) -> dict[str, Any]:
    state_root, staged_root = _resolve_state_roots(Path(state_dir))

    listing_obj = _load_json_obj(item_listing_path.resolve(), schema_id="vision_item_listing_v1", reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    cfg_obj = _load_json_obj(dataset_config_path.resolve(), schema_id="vision_qxrl_dataset_config_v1", reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    cfg = parse_vision_qxrl_dataset_config_v1(cfg_obj)

    listing_id = sha256_prefixed(item_listing_path.read_bytes())
    if str(cfg.item_listing_ref.get("artifact_id", "")).strip() != str(listing_id).strip():
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    dataset_manifest_obj = _load_json_obj(qxrl_dataset_manifest_path.resolve(), schema_id="qxrl_dataset_manifest_v1", reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    suite_obj = _load_json_obj(perception_eval_suite_path.resolve(), schema_id="qxrl_perception_eval_suite_v1", reason=REASON_VISION3_UFC_INVALID)
    candidate_scorecard_obj = _load_json_obj(candidate_scorecard_path.resolve(), schema_id="qxrl_eval_scorecard_v1", reason=REASON_VISION3_SCORECARD_MISMATCH)

    rows = load_listing_descriptor_rows_v1(
        base_dir=staged_root,
        item_listing_obj=dict(listing_obj),
        max_items_u64=int(cfg.caps.max_items_u64),
        provenance_check_fn=_stage2._verify_descriptor_provenance_v1,
    )
    examples = build_qxrl_examples_from_rows_v1(base_dir=staged_root, rows=rows, cfg=cfg)
    segments = build_qxrl_segments_v1(examples=examples, cfg=cfg)

    seg_rows = dataset_manifest_obj.get("segments")
    if not isinstance(seg_rows, list):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    seg_rows_sorted = sorted(list(seg_rows), key=lambda r: int(r.get("segment_index_u32", -1)) if isinstance(r, dict) else -1)
    if len(seg_rows_sorted) != len(segments):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    segment_ids: list[str] = []
    for exp, row in zip(segments, seg_rows_sorted, strict=True):
        if not isinstance(row, dict):
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
        if int(row.get("segment_index_u32", -1)) != int(exp.segment_index_u32):
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
        if int(row.get("record_count_u32", -1)) != int(exp.record_count_u32):
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
        if int(row.get("first_example_id_u64", -1)) != int(exp.first_example_id_u64):
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
        if int(row.get("last_example_id_u64", -1)) != int(exp.last_example_id_u64):
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

        seg_ref = require_artifact_ref_v1(row.get("segment_ref"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
        if str(seg_ref.get("artifact_id", "")).strip() != str(exp.segment_id).strip():
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
        seg_path = verify_artifact_ref_v1(
            artifact_ref=seg_ref,
            base_dir=staged_root,
            expected_relpath_prefix="polymath/registry/eudrs_u/datasets/segments/",
        )
        if seg_path.read_bytes() != exp.segment_bytes:
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
        segment_ids.append(str(exp.segment_id))

    dataset_root_hex = str(dataset_manifest_obj.get("dataset_root_hash32_hex", "")).strip()
    if dataset_root_hex != compute_dataset_root_hash32_hex_from_segments_v1(segments):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    # Bind build-root (used by build-manifest producers) deterministically.
    _build_root_hex = compute_build_root_hash32_hex_v1(config_id=sha256_prefixed(dataset_config_path.read_bytes()), item_listing_id=listing_id, segment_ids=segment_ids)

    if baseline_scorecard_path is not None:
        baseline_scorecard_obj = _load_json_obj(baseline_scorecard_path.resolve(), schema_id="qxrl_eval_scorecard_v1", reason=REASON_VISION3_SCORECARD_MISMATCH)
        delta_rob_q32: int | None = None
    else:
        baseline_scorecard_obj, delta_rob_q32 = _recompute_baseline_and_robust_delta(
            state_root=state_root,
            staged_root=staged_root,
            suite_obj=suite_obj,
            candidate_scorecard_obj=candidate_scorecard_obj,
        )

    ufc_candidate_q32 = _scorecard_ufc_q32(scorecard_obj=candidate_scorecard_obj, suite_obj=suite_obj)
    ufc_baseline_q32 = _scorecard_ufc_q32(scorecard_obj=baseline_scorecard_obj, suite_obj=suite_obj)

    delta_q32 = int(add_sat(int(ufc_candidate_q32), int(-ufc_baseline_q32)))
    if delta_rob_q32 is None:
        delta_rob_q32 = int(delta_q32)

    thresholds = suite_obj.get("thresholds")
    if not isinstance(thresholds, dict):
        fail(REASON_VISION3_UFC_INVALID)
    ufc_min_q32 = _q32(thresholds.get("ufc_min_q32"), reason=REASON_VISION3_UFC_INVALID)
    cac_delta_min_q32 = _q32(thresholds.get("cac_delta_min_q32"), reason=REASON_VISION3_CAC_FAIL)
    cac_delta_rob_min_q32 = _q32(thresholds.get("cac_delta_rob_min_q32"), reason=REASON_VISION3_CAC_FAIL)

    if int(ufc_candidate_q32) < int(ufc_min_q32):
        fail(REASON_VISION3_UFC_INVALID)
    if int(delta_q32) < int(cac_delta_min_q32):
        fail(REASON_VISION3_CAC_FAIL)
    if int(delta_rob_q32) < int(cac_delta_rob_min_q32):
        fail(REASON_VISION3_CAC_FAIL)

    return {
        "schema_id": "vision_stage3_verify_receipt_v1",
        "verdict": "VALID",
        "computed": {
            "ufc_q32": {"q": int(ufc_candidate_q32)},
            "delta_q32": {"q": int(delta_q32)},
            "delta_rob_q32": {"q": int(delta_rob_q32)},
            "candidate_scorecard_id": str(candidate_scorecard_obj.get("scorecard_id", "")),
            "baseline_scorecard_id": str(baseline_scorecard_obj.get("scorecard_id", "")),
            "build_root_hash32_hex": str(_build_root_hex),
        },
    }


def _write_receipt(*, state_dir: Path, receipt_obj: dict[str, Any]) -> None:
    evidence_dir = Path(state_dir).resolve() / EUDRS_U_EVIDENCE_DIR_REL
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "vision_stage3_verify_receipt_v1.json").write_bytes(gcj1_canon_bytes(receipt_obj))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="verify_vision_stage3_v1")
    parser.add_argument("--state_dir", required=True)
    parser.add_argument("--item_listing_relpath", required=True)
    parser.add_argument("--dataset_config_relpath", required=True)
    parser.add_argument("--qxrl_dataset_manifest_relpath", required=True)
    parser.add_argument("--perception_eval_suite_relpath", required=True)
    parser.add_argument("--candidate_scorecard_relpath", required=True)
    parser.add_argument("--baseline_scorecard_relpath", required=False)
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir).resolve()
    _, staged_root = _resolve_state_roots(state_dir)

    def _resolve(rel: str) -> Path:
        s = require_safe_relpath_v1(str(rel), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
        p = (staged_root / s).resolve()
        try:
            _ = p.relative_to(staged_root)
        except Exception:
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
        if not p.exists() or not p.is_file():
            fail("MISSING_STATE_INPUT")
        return p

    baseline_path = None
    if args.baseline_scorecard_relpath:
        baseline_path = _resolve(str(args.baseline_scorecard_relpath))

    try:
        receipt = verify(
            state_dir=state_dir,
            item_listing_path=_resolve(str(args.item_listing_relpath)),
            dataset_config_path=_resolve(str(args.dataset_config_relpath)),
            qxrl_dataset_manifest_path=_resolve(str(args.qxrl_dataset_manifest_relpath)),
            perception_eval_suite_path=_resolve(str(args.perception_eval_suite_relpath)),
            candidate_scorecard_path=_resolve(str(args.candidate_scorecard_relpath)),
            baseline_scorecard_path=baseline_path,
        )
        _write_receipt(state_dir=state_dir, receipt_obj=receipt)
        print("VALID")
    except OmegaV18Error as exc:
        reason = str(exc)
        if reason.startswith("INVALID:"):
            reason = reason.split(":", 1)[1]
        receipt = {"schema_id": "vision_stage3_verify_receipt_v1", "verdict": "INVALID", "reason_code": str(reason)}
        try:
            _write_receipt(state_dir=state_dir, receipt_obj=receipt)
        except Exception:  # noqa: BLE001
            pass
        print("INVALID:" + str(reason))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
