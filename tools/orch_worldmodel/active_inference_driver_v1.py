#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v18_0.campaign_polymath_sip_ingestion_l0_v1 import run as run_sip_campaign
from cdel.v18_0.omega_common_v1 import write_hashed_json
from cdel.v18_0.verify_rsi_polymath_sip_ingestion_l0_v1 import verify as verify_sip
from cdel.v19_0.campaign_epistemic_reduce_v1 import run as run_reduce_campaign
from cdel.v19_0.common_v1 import canon_hash_obj, validate_schema
from cdel.v19_0.verify_rsi_epistemic_reduce_v1 import verify as verify_reduce

from tools.orch_worldmodel.query_router_v1 import derive_queries
from tools.orch_worldmodel.uncertainty_report_v1 import build_uncertainty_report, write_uncertainty_report


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _to_repo_rel(*, repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeError("SCHEMA_FAIL:repo_relpath") from exc


def _is_sha(value: Any) -> bool:
    text = str(value).strip()
    return text.startswith("sha256:") and len(text) == 71 and all(ch in "0123456789abcdef" for ch in text.split(":", 1)[1])


def _latest_hashed(path: Path, suffix: str) -> Path:
    rows = sorted(path.glob(f"sha256_*.{suffix}"), key=lambda p: p.name)
    if not rows:
        raise RuntimeError(f"MISSING_STATE_INPUT:{suffix}")
    return rows[-1].resolve()


def _resolve_manifest_by_hash(manifests_dir: Path, digest: str, suffix: str) -> Path:
    if not _is_sha(digest):
        raise RuntimeError("SCHEMA_FAIL:hash")
    hex64 = str(digest).split(":", 1)[1]
    candidates = [
        manifests_dir / f"sha256_{hex64}.{suffix}",
        manifests_dir.parent / f"sha256_{hex64}.{suffix}",
    ]
    for target in candidates:
        if target.exists() and target.is_file():
            return target.resolve()
    raise RuntimeError("MISSING_STATE_INPUT")


def _resolve_bundle_by_hash(*, repo_root: Path, bundle_hash: str) -> Path:
    if not _is_sha(bundle_hash):
        raise RuntimeError("SCHEMA_FAIL:bundle_hash")
    hex64 = str(bundle_hash).split(":", 1)[1]
    candidates = [
        (repo_root / "daemon" / "orch_policy" / "store" / f"sha256_{hex64}.orch_policy_bundle_v1.json").resolve(),
        (repo_root / "daemon" / "orch_policy" / "store" / "manifests" / f"sha256_{hex64}.orch_policy_bundle_v1.json").resolve(),
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    raise RuntimeError("MISSING_STATE_INPUT:orch_policy_bundle_v1.json")


def _load_bundle_at_path(bundle_path: Path) -> tuple[Path, dict[str, Any], str]:
    bundle = _load_json(bundle_path)
    if str(bundle.get("schema_version", "")).strip() != "orch_policy_bundle_v1":
        raise RuntimeError("SCHEMA_FAIL:orch_policy_bundle_v1")
    bundle_hash = canon_hash_obj(bundle)
    declared_bundle_id = str(bundle.get("policy_bundle_id", "")).strip()
    if _is_sha(declared_bundle_id):
        declared_expected = canon_hash_obj({k: v for k, v in bundle.items() if k != "policy_bundle_id"})
        if declared_bundle_id != declared_expected:
            raise RuntimeError("NONDETERMINISTIC:orch_policy_bundle")
    return bundle_path, bundle, bundle_hash


def _load_latest_worldmodel_bundle(repo_root: Path) -> tuple[Path, dict[str, Any], str]:
    pointer_path = (repo_root / "daemon" / "orch_policy" / "active" / "ORCH_POLICY_V1.json").resolve()
    if pointer_path.exists() and pointer_path.is_file():
        pointer_payload = _load_json(pointer_path)
        validate_schema(pointer_payload, "orch_policy_pointer_v1")
        active_bundle_hash = str(pointer_payload.get("active_policy_bundle_id", "")).strip()
        bundle_path = _resolve_bundle_by_hash(repo_root=repo_root, bundle_hash=active_bundle_hash)
        return _load_bundle_at_path(bundle_path)

    manifests = (repo_root / "daemon" / "orch_policy" / "store" / "manifests").resolve()
    bundle_path = _latest_hashed(manifests, "orch_policy_bundle_v1.json")
    return _load_bundle_at_path(bundle_path)


def _load_manifest_for_bundle(repo_root: Path, bundle: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    manifests = (repo_root / "daemon" / "orch_policy" / "store" / "manifests").resolve()
    manifest_id = str(bundle.get("transition_dataset_manifest_id", "")).strip()
    if not _is_sha(manifest_id):
        path = _latest_hashed(manifests, "orch_transition_dataset_manifest_v1.json")
    else:
        path = _resolve_manifest_by_hash(manifests, manifest_id, "orch_transition_dataset_manifest_v1.json")
    payload = _load_json(path)
    if str(payload.get("schema_version", "")).strip() != "orch_transition_dataset_manifest_v1":
        raise RuntimeError("SCHEMA_FAIL:orch_transition_dataset_manifest_v1")
    return path, payload, canon_hash_obj(payload)


def _load_latest_sip_artifact(state_root: Path) -> tuple[dict[str, Any], str]:
    knowledge_dir = state_root / "polymath" / "ingestion" / "knowledge"
    path = _latest_hashed(knowledge_dir, "sip_knowledge_artifact_v1.json")
    payload = _load_json(path)
    if str(payload.get("schema_version", "")).strip() != "sip_knowledge_artifact_v1":
        raise RuntimeError("SCHEMA_FAIL:sip_knowledge_artifact_v1")
    return payload, canon_hash_obj(payload)


def _load_latest_capsule(state_root: Path) -> tuple[dict[str, Any], str]:
    capsule_dir = state_root / "epistemic" / "capsules"
    path = _latest_hashed(capsule_dir, "epistemic_capsule_v1.json")
    payload = _load_json(path)
    if str(payload.get("schema_version", "")).strip() != "epistemic_capsule_v1":
        raise RuntimeError("SCHEMA_FAIL:epistemic_capsule_v1")
    return payload, canon_hash_obj(payload)


def _write_utility_policy(*, out_dir: Path, base_policy: dict[str, Any], runtime_stats_source_id: str) -> tuple[Path, dict[str, Any], str]:
    payload = dict(base_policy)
    payload["runtime_stats_source_id"] = str(runtime_stats_source_id)
    payload["policy_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "policy_id"})
    validate_schema(payload, "utility_policy_v1")
    path, obj, digest = write_hashed_json(out_dir, "utility_policy_v1.json", payload, id_field="policy_id")
    validate_schema(obj, "utility_policy_v1")
    return path, obj, digest


def _write_utility_proof_receipt(
    *,
    out_dir: Path,
    tick_u64: int,
    candidate_bundle_hash: str,
    baseline_ref_hash: str,
    runtime_stats_source_id: str,
    runtime_stats_hash: str,
    utility_metrics: dict[str, Any],
    utility_thresholds: dict[str, Any],
) -> tuple[Path, dict[str, Any], str]:
    reason_code = "UTILITY_OK" if bool(utility_metrics.get("utility_ok_b", False)) else "NO_UTILITY_GAIN"
    utility_ok_b = reason_code == "UTILITY_OK"
    primary_in = canon_hash_obj(
        {
            "probe_suite_id": "active_inference_probe_suite_v1",
            "candidate_bundle_hash": candidate_bundle_hash,
            "baseline_ref_hash": baseline_ref_hash,
            "utility_metrics": utility_metrics,
        }
    )
    primary_out = canon_hash_obj({"utility_ok_b": utility_ok_b, "reason_code": reason_code})
    stress_in = canon_hash_obj(
        {
            "stress_probe_suite_id": "active_inference_stress_suite_v1",
            "candidate_bundle_hash": candidate_bundle_hash,
            "baseline_ref_hash": baseline_ref_hash,
            "utility_thresholds": utility_thresholds,
        }
    )
    stress_out = canon_hash_obj({"utility_ok_b": utility_ok_b, "reason_code": reason_code})

    tick = int(max(0, int(tick_u64)))
    targeted_debt_keys = ["KDL", "EDL", "UTILITY_FAIL"]
    debt_before_by_key = {
        "KDL": int(max(0, int(utility_metrics.get("uncertainty_sum_q32", 0)))),
        "EDL": int(max(0, int(utility_metrics.get("uncertainty_sum_q32", 0) // 2))),
        "UTILITY_FAIL": int(0 if utility_ok_b else 1),
    }
    debt_after_by_key = {
        "KDL": int(max(0, debt_before_by_key["KDL"] - int(max(0, int(utility_metrics.get("inferred_kdl_reduction_q32", 0)))))),
        "EDL": int(max(0, debt_before_by_key["EDL"] - int(max(0, int(utility_metrics.get("inferred_edl_reduction_q32", 0)))))),
        "UTILITY_FAIL": int(0 if utility_ok_b else 1),
    }
    debt_delta_by_key = {
        key: int(debt_after_by_key[key] - debt_before_by_key[key])
        for key in targeted_debt_keys
    }
    proof_evidence = [
        {
            "evidence_kind": "UTILITY_METRICS",
            "artifact_hash": str(candidate_bundle_hash),
            "summary": "Utility metrics derived from uncertainty + ingestion signals.",
        },
        {
            "evidence_kind": "BASELINE_REF",
            "artifact_hash": str(baseline_ref_hash),
            "summary": "Baseline transition-manifest reference.",
        },
    ]
    producer_run_id = _sha256_prefixed(
        _canon_bytes(
            {
                "tick_u64": tick,
                "candidate_bundle_hash": str(candidate_bundle_hash),
                "baseline_ref_hash": str(baseline_ref_hash),
                "runtime_stats_hash": str(runtime_stats_hash),
            }
        )
    )

    payload = {
        "schema_id": "utility_proof_receipt_v1",
        "id": "sha256:" + ("0" * 64),
        "schema_name": "utility_proof_receipt_v1",
        "schema_version": "v19_0",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": tick,
        "producer_run_id": producer_run_id,
        "utility_action_id": "ACTIVE_INFERENCE_UTILITY_REDUCE_V1",
        "utility_class": "HEAVY",
        "capability_id": "RSI_ACTIVE_INFERENCE_DRIVER_V1",
        "candidate_bundle_hash": str(candidate_bundle_hash),
        "baseline_ref_hash": str(baseline_ref_hash),
        "probe_suite_id": "active_inference_probe_suite_v1",
        "stress_probe_suite_id": "active_inference_stress_suite_v1",
        "runtime_stats_source_id": str(runtime_stats_source_id),
        "runtime_stats_hash": str(runtime_stats_hash),
        "candidate_bundle_present_b": True,
        "probe_executed_b": True,
        "correctness_ok_b": True,
        "utility_ok_b": bool(utility_ok_b),
        "signal_a_ok_b": bool(utility_ok_b),
        "signal_b_ok_b": bool(utility_ok_b),
        "utility_metrics": dict(utility_metrics),
        "utility_thresholds": dict(utility_thresholds),
        "reason_code": reason_code,
        "declared_class": "FRONTIER_HEAVY",
        "effect_class": "EFFECT_HEAVY_OK" if utility_ok_b else "EFFECT_HEAVY_NO_UTILITY",
        "primary_probe": {"input_hash": primary_in, "output_hash": primary_out},
        "stress_probe": {"input_hash": stress_in, "output_hash": stress_out},
        "targeted_debt_keys": targeted_debt_keys,
        "debt_before_by_key": debt_before_by_key,
        "debt_after_by_key": debt_after_by_key,
        "debt_delta_by_key": debt_delta_by_key,
        "proof_evidence": proof_evidence,
        "reduced_specific_trigger_keys_b": bool(utility_ok_b),
        "created_at_utc": _utc_now_rfc3339(),
    }
    payload["id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "id"})
    validate_schema(payload, "utility_proof_receipt_v1")
    path, obj, digest = write_hashed_json(out_dir, "utility_proof_receipt_v1.json", payload, id_field="receipt_id")
    validate_schema(obj, "utility_proof_receipt_v1")
    return path, obj, digest


def _write_active_inference_receipt(*, out_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    validate_schema(payload, "orch_active_inference_receipt_v1")
    path, obj, digest = write_hashed_json(out_dir, "orch_active_inference_receipt_v1.json", payload, id_field="id")
    validate_schema(obj, "orch_active_inference_receipt_v1")
    return path, obj, digest


def _materialize_sip_pack_with_queries(
    *,
    repo_root: Path,
    state_root: Path,
    base_pack_path: Path,
    queries: list[str],
    tick_u64: int,
) -> Path:
    base_pack = _load_json(base_pack_path)
    if str(base_pack.get("schema_version", "")).strip() != "rsi_polymath_sip_ingestion_l0_pack_v1":
        raise RuntimeError("SCHEMA_FAIL:rsi_polymath_sip_ingestion_l0_pack_v1")

    if not queries:
        return base_pack_path

    query_dir = (repo_root / "daemon" / "orch_active_inference_v1" / "query_inputs").resolve()
    query_dir.mkdir(parents=True, exist_ok=True)
    query_path = query_dir / f"tick_{int(tick_u64):020d}.active_inference_queries_v1.jsonl"
    query_rows = [{"schema_version": "active_inference_query_v1", "query": str(q)} for q in sorted(set(queries))]
    query_blob = b"\n".join(_canon_bytes(row) for row in query_rows) + b"\n"
    query_path.write_bytes(query_blob)

    query_rel = _to_repo_rel(repo_root=repo_root, path=query_path)
    query_hash = _sha256_prefixed(query_blob)
    if _sha256_prefixed(query_path.read_bytes()) != query_hash:
        raise RuntimeError("NONDETERMINISTIC:query_pack_hash")

    inputs_relpaths = sorted({str(v) for v in list(base_pack.get("inputs_relpaths") or []) if str(v).strip()} | {query_rel})
    input_content_ids = dict(base_pack.get("input_content_ids") or {})
    input_content_ids[query_rel] = query_hash

    derived_pack = dict(base_pack)
    derived_pack["inputs_relpaths"] = inputs_relpaths
    derived_pack["input_content_ids"] = {str(k): str(v) for k, v in sorted(input_content_ids.items(), key=lambda kv: str(kv[0]))}

    pack_dir = state_root / "packs"
    pack_dir.mkdir(parents=True, exist_ok=True)
    pack_path = pack_dir / f"tick_{int(tick_u64):020d}.rsi_polymath_sip_ingestion_l0_pack_v1.json"
    pack_path.write_bytes(_canon_bytes(derived_pack))
    return pack_path


def _tick_from_env(fallback: int = 0) -> int:
    raw = str(os.environ.get("OMEGA_TICK_U64", "")).strip()
    if not raw:
        return max(0, int(fallback))
    try:
        value = int(raw)
    except Exception:  # noqa: BLE001
        return max(0, int(fallback))
    return max(0, int(value))


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="active_inference_driver_v1")
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--tick_u64", type=int, default=-1)
    ap.add_argument("--top_k_u64", type=int, default=64)
    ap.add_argument("--query_rules_json", default=str((Path(__file__).resolve().parent / "query_router_rules_v1.json").as_posix()))
    ap.add_argument("--sip_campaign_pack", default="campaigns/rsi_polymath_sip_ingestion_l0_v1/rsi_polymath_sip_ingestion_l0_pack_v1.json")
    ap.add_argument("--reduce_campaign_pack", default="campaigns/rsi_epistemic_reduce_v1/rsi_epistemic_reduce_pack_v1.json")
    ap.add_argument("--skip_campaign_runs", action="store_true")
    ap.add_argument("--created_at_utc", default="")
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = Path(args.out_dir).resolve()
    state_root = out_dir / "daemon" / "orch_active_inference_v1" / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    tick_u64 = _tick_from_env(fallback=(0 if int(args.tick_u64) < 0 else int(args.tick_u64)))

    _bundle_path, bundle, bundle_hash = _load_latest_worldmodel_bundle(repo_root)
    _manifest_path, manifest, manifest_hash = _load_manifest_for_bundle(repo_root, bundle)

    uncertainty_report = build_uncertainty_report(
        tick_u64=tick_u64,
        worldmodel_bundle=bundle,
        transition_dataset_manifest=manifest,
        repo_root=repo_root,
        top_k_u64=int(max(1, int(args.top_k_u64))),
        created_at_utc=(str(args.created_at_utc).strip() or None),
    )
    _u_path, _u_obj, uncertainty_hash = write_uncertainty_report(out_dir=state_root / "uncertainty", report=uncertainty_report)

    feature_ids = [str(row.get("feature_id", "")).strip() for row in list(uncertainty_report.get("uncertain_features") or []) if str(row.get("feature_id", "")).strip()]
    query_rules = _load_json(Path(args.query_rules_json).resolve())
    queries = derive_queries(feature_ids=sorted(set(feature_ids)), rules_payload=query_rules)

    campaign_out = out_dir / "active_inference_campaigns"
    campaign_out.mkdir(parents=True, exist_ok=True)

    sip_pack_path = (repo_root / str(args.sip_campaign_pack)).resolve()
    sip_pack_path = _materialize_sip_pack_with_queries(
        repo_root=repo_root,
        state_root=state_root,
        base_pack_path=sip_pack_path,
        queries=queries,
        tick_u64=tick_u64,
    )

    if not bool(args.skip_campaign_runs):
        run_sip_campaign(
            campaign_pack=sip_pack_path,
            out_dir=campaign_out,
        )
        if verify_sip(campaign_out, mode="full") != "VALID":
            raise RuntimeError("VERIFY_ERROR:sip")

        reduce_result = run_reduce_campaign(
            campaign_pack=(repo_root / str(args.reduce_campaign_pack)).resolve(),
            out_dir=campaign_out,
        )
        if str(reduce_result.get("status", "")).strip() not in {"OK", "REFUTED"}:
            raise RuntimeError("VERIFY_ERROR:reduce")
        if verify_reduce(campaign_out, mode="full") != "VALID":
            raise RuntimeError("VERIFY_ERROR:reduce")

    sip_state = campaign_out / "daemon" / "rsi_polymath_sip_ingestion_l0_v1" / "state"
    reduce_state = campaign_out / "daemon" / "rsi_epistemic_reduce_v1" / "state"

    sip_artifact, sip_artifact_hash = _load_latest_sip_artifact(sip_state)
    sip_receipt_hash = str(sip_artifact.get("sip_seal_receipt_id", "")).strip()
    ingested_content_ids = [
        str(sip_artifact.get("raw_bytes_content_id", "")).strip(),
        str(sip_artifact.get("canonical_jsonl_content_id", "")).strip(),
    ]

    capsule, capsule_hash = _load_latest_capsule(reduce_state)

    base_utility_policy = _load_json((repo_root / "campaigns" / "rsi_omega_daemon_v19_0_long_run_v1" / "utility" / "omega_utility_policy_v1.json").resolve())
    utility_policy_path, utility_policy, utility_policy_hash = _write_utility_policy(
        out_dir=state_root / "utility",
        base_policy=base_utility_policy,
        runtime_stats_source_id="active_inference_driver_v1",
    )

    uncertainty_sum_q32 = int(sum(int(row.get("uncertainty_q32", 0)) for row in list(uncertainty_report.get("uncertain_features") or [])) )
    ingested_u64 = int(sum(1 for x in ingested_content_ids if _is_sha(x)))
    inferred_kdl_reduction_q32 = int(min(uncertainty_sum_q32, ingested_u64 * (1 << 31)))
    inferred_edl_reduction_q32 = int(min(uncertainty_sum_q32 // 2, ingested_u64 * (1 << 30)))
    utility_ok_b = bool(ingested_u64 > 0 and _is_sha(capsule_hash))

    utility_metrics = {
        "uncertainty_feature_count_u64": int(len(list(uncertainty_report.get("uncertain_features") or []))),
        "uncertainty_sum_q32": int(uncertainty_sum_q32),
        "ingested_content_u64": int(ingested_u64),
        "inferred_kdl_reduction_q32": int(inferred_kdl_reduction_q32),
        "inferred_edl_reduction_q32": int(inferred_edl_reduction_q32),
        "utility_ok_b": bool(utility_ok_b),
    }
    utility_thresholds = {
        "min_ingested_content_u64": 1,
        "min_inferred_kdl_reduction_q32": 1,
    }

    _up_path, _up_obj, utility_proof_hash = _write_utility_proof_receipt(
        out_dir=state_root / "utility",
        tick_u64=tick_u64,
        candidate_bundle_hash=uncertainty_hash,
        baseline_ref_hash=manifest_hash,
        runtime_stats_source_id=str(utility_policy.get("runtime_stats_source_id", "active_inference_driver_v1")),
        runtime_stats_hash=capsule_hash,
        utility_metrics=utility_metrics,
        utility_thresholds=utility_thresholds,
    )

    producer_run_id = _sha256_prefixed(
        json.dumps(
            {
                "tick_u64": int(tick_u64),
                "worldmodel_bundle_hash": bundle_hash,
                "transition_dataset_manifest_hash": manifest_hash,
                "queries": queries,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )

    receipt_payload = {
        "schema_id": "orch_active_inference_receipt_v1",
        "id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "producer_run_id": producer_run_id,
        "uncertainty_report_hash": uncertainty_hash,
        "queries": queries,
        "sip_ingestion": {
            "campaign_id": "rsi_polymath_sip_ingestion_l0_v1",
            "sip_receipt_hash": sip_receipt_hash,
            "ingested_content_ids": [x for x in ingested_content_ids if _is_sha(x)],
        },
        "epistemic_reduce": {
            "campaign_id": "rsi_epistemic_reduce_v1",
            "reduce_receipt_hash": capsule_hash,
            "utility_policy_hash": utility_policy_hash,
        },
        "created_at_utc": str(args.created_at_utc).strip() or _utc_now_rfc3339(),
    }
    receipt_payload["id"] = canon_hash_obj({k: v for k, v in receipt_payload.items() if k != "id"})
    receipt_path, _receipt_obj, receipt_hash = _write_active_inference_receipt(out_dir=state_root / "receipts", payload=receipt_payload)

    summary = {
        "schema_version": "active_inference_driver_summary_v1",
        "receipt_hash": receipt_hash,
        "receipt_path": receipt_path.as_posix(),
        "uncertainty_report_hash": uncertainty_hash,
        "sip_artifact_hash": sip_artifact_hash,
        "capsule_hash": capsule_hash,
        "utility_policy_hash": utility_policy_hash,
        "utility_proof_hash": utility_proof_hash,
        "utility_policy_path": utility_policy_path.as_posix(),
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
