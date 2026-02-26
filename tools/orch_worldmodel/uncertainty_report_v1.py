#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v18_0.omega_common_v1 import write_hashed_json
from cdel.v19_0.common_v1 import canon_hash_obj, validate_schema


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL:jsonl_row")
        out.append(row)
    return out


def _resolve_rel(path_value: str, repo_root: Path) -> Path:
    raw = str(path_value).strip()
    if not raw:
        raise RuntimeError("SCHEMA_FAIL:relpath")
    p = Path(raw)
    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (repo_root / p).resolve()
    if not resolved.exists() or not resolved.is_file():
        raise RuntimeError("MISSING_STATE_INPUT")
    return resolved


def _policy_scores(policy_table: dict[str, Any]) -> dict[tuple[str, str], int]:
    scores: dict[tuple[str, str], int] = {}
    if isinstance(policy_table.get("context_rows"), list):
        for ctx_row in list(policy_table.get("context_rows") or []):
            if not isinstance(ctx_row, dict):
                continue
            context_key = str(ctx_row.get("context_key", "")).strip()
            ranked = ctx_row.get("ranked_actions")
            if not context_key or not isinstance(ranked, list):
                continue
            for action in ranked:
                if not isinstance(action, dict):
                    continue
                cap = str(action.get("capability_id", "")).strip()
                if not cap:
                    continue
                scores[(context_key, cap)] = int(action.get("score_q32", 0))
        return scores

    if isinstance(policy_table.get("rows"), list):
        for ctx_row in list(policy_table.get("rows") or []):
            if not isinstance(ctx_row, dict):
                continue
            context_key = str(ctx_row.get("context_key", "")).strip()
            ranked = ctx_row.get("ranked_capabilities")
            if not context_key or not isinstance(ranked, list):
                continue
            for action in ranked:
                if not isinstance(action, dict):
                    continue
                cap = str(action.get("capability_id", "")).strip()
                if not cap:
                    continue
                scores[(context_key, cap)] = int(action.get("score_q32", 0))
    return scores


def _find_policy_table(bundle: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    rel = str(bundle.get("policy_table_relpath", "")).strip()
    if rel:
        policy_path = _resolve_rel(rel, repo_root)
        payload = _load_json(policy_path)
        if str(payload.get("schema_version", "")).strip() != "orch_policy_table_v1":
            raise RuntimeError("SCHEMA_FAIL:policy_table")
        return payload
    table = bundle.get("policy_table")
    if not isinstance(table, dict):
        raise RuntimeError("SCHEMA_FAIL:policy_table_missing")
    if str(table.get("schema_version", "")).strip() != "orch_policy_table_v1":
        raise RuntimeError("SCHEMA_FAIL:policy_table")
    return table


def _p90(values: list[int]) -> int:
    if not values:
        return 0
    sorted_vals = sorted(int(v) for v in values)
    idx = (9 * (len(sorted_vals) - 1)) // 10
    return int(sorted_vals[idx])


def _mean_floor(values: list[int]) -> int:
    if not values:
        return 0
    total = int(sum(int(v) for v in values))
    return int(total // len(values))


def build_uncertainty_report(
    *,
    tick_u64: int,
    worldmodel_bundle: dict[str, Any],
    transition_dataset_manifest: dict[str, Any],
    repo_root: Path,
    top_k_u64: int = 64,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    if str(worldmodel_bundle.get("schema_version", "")).strip() != "orch_policy_bundle_v1":
        raise RuntimeError("SCHEMA_FAIL:orch_policy_bundle_v1")
    if str(transition_dataset_manifest.get("schema_version", "")).strip() != "orch_transition_dataset_manifest_v1":
        raise RuntimeError("SCHEMA_FAIL:orch_transition_dataset_manifest_v1")

    events_rel = str(transition_dataset_manifest.get("transition_events_relpath", "")).strip()
    events_path = _resolve_rel(events_rel, repo_root)
    events = _load_jsonl(events_path)

    policy_table = _find_policy_table(worldmodel_bundle, repo_root)
    scores = _policy_scores(policy_table)

    by_feature: dict[str, list[int]] = {}
    for row in events:
        if str(row.get("schema_version", "")).strip() != "orch_transition_event_v1":
            raise RuntimeError("SCHEMA_FAIL:orch_transition_event_v1")
        context_key = str(row.get("context_key", "")).strip()
        capability_id = str(row.get("action_capability_id", "")).strip()
        objective_kind = str(row.get("objective_kind", "")).strip()
        if not context_key or not capability_id:
            continue
        predicted = int(scores.get((context_key, capability_id), 0))
        observed = int(row.get("reward_q32", 0))
        residual = abs(int(observed) - int(predicted))
        feature_id = objective_kind if objective_kind else capability_id
        by_feature.setdefault(feature_id, []).append(int(residual))

    rows: list[dict[str, Any]] = []
    for feature_id in sorted(by_feature.keys()):
        values = by_feature[feature_id]
        if not values:
            continue
        mean_abs = int(_mean_floor(values))
        p90_abs = int(_p90(values))
        rows.append(
            {
                "feature_id": feature_id,
                "metric_kind": "HOLDOUT_RESIDUAL_Q32",
                "uncertainty_q32": int(p90_abs),
                "evidence": {
                    "mean_abs_error_q32": int(mean_abs),
                    "p90_abs_error_q32": int(p90_abs),
                    "n_u64": int(len(values)),
                },
            }
        )

    rows.sort(key=lambda r: (-int(r.get("uncertainty_q32", 0)), str(r.get("feature_id", ""))))
    rows = rows[: max(1, int(top_k_u64))]

    report = {
        "schema_id": "orch_worldmodel_uncertainty_report_v1",
        "id": "sha256:" + ("0" * 64),
        "tick_u64": int(max(0, int(tick_u64))),
        "worldmodel_bundle_hash": canon_hash_obj(worldmodel_bundle),
        "transition_dataset_manifest_hash": canon_hash_obj(transition_dataset_manifest),
        "top_k_u64": int(max(1, int(top_k_u64))),
        "uncertain_features": rows,
        "created_at_utc": str(created_at_utc or _utc_now_rfc3339()),
    }
    report["id"] = canon_hash_obj({k: v for k, v in report.items() if k != "id"})
    validate_schema(report, "orch_worldmodel_uncertainty_report_v1")
    return report


def write_uncertainty_report(*, out_dir: Path, report: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    validate_schema(report, "orch_worldmodel_uncertainty_report_v1")
    path, obj, digest = write_hashed_json(out_dir, "orch_worldmodel_uncertainty_report_v1.json", report, id_field="id")
    validate_schema(obj, "orch_worldmodel_uncertainty_report_v1")
    return path, obj, digest


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="uncertainty_report_v1")
    ap.add_argument("--worldmodel_bundle", required=True)
    ap.add_argument("--transition_dataset_manifest", required=True)
    ap.add_argument("--tick_u64", type=int, default=0)
    ap.add_argument("--top_k_u64", type=int, default=64)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--created_at_utc", default="")
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    bundle = _load_json(Path(args.worldmodel_bundle).resolve())
    manifest = _load_json(Path(args.transition_dataset_manifest).resolve())
    repo_root = Path(__file__).resolve().parents[2]

    report = build_uncertainty_report(
        tick_u64=int(args.tick_u64),
        worldmodel_bundle=bundle,
        transition_dataset_manifest=manifest,
        repo_root=repo_root,
        top_k_u64=int(args.top_k_u64),
        created_at_utc=(str(args.created_at_utc).strip() or None),
    )
    path, _obj, digest = write_uncertainty_report(out_dir=Path(args.out_dir).resolve(), report=report)
    print(json.dumps({"report_hash": digest, "report_path": path.as_posix()}, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
