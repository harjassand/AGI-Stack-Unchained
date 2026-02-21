"""Deterministic epistemic ECAC/EUFC wrapper certificates (R5)."""

from __future__ import annotations

from typing import Any

from ..common_v1 import canon_hash_obj, ensure_sha256, fail, validate_schema, verify_object_id

_Q32_ONE = 1 << 32


def _binding_hash(
    *,
    capsule_id: str,
    graph_id: str,
    type_binding_id: str,
    strip_receipt_id: str,
    objective_profile_id: str,
    cert_profile_id: str,
    stats: dict[str, int],
    task_eval_hash: str,
    task_input_ids: list[str],
) -> str:
    return canon_hash_obj(
        {
            "schema_version": "epistemic_eval_binding_v1",
            "capsule_id": capsule_id,
            "graph_id": graph_id,
            "type_binding_id": type_binding_id,
            "strip_receipt_id": strip_receipt_id,
            "objective_profile_id": objective_profile_id,
            "cert_profile_id": cert_profile_id,
            "stats": dict(stats),
            "task_eval_hash": task_eval_hash,
            "task_input_ids": list(task_input_ids),
        }
    )


def _graph_stats(graph: dict[str, Any]) -> dict[str, int]:
    validate_schema(graph, "qxwmr_graph_v1")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise RuntimeError("SCHEMA_FAIL")
    low_conf = 0
    for row in nodes:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL")
        if int(row.get("confidence_q32", 0)) < (_Q32_ONE // 2):
            low_conf += 1
    return {
        "node_count_u64": int(len(nodes)),
        "edge_count_u64": int(len(edges)),
        "low_conf_count_u64": int(low_conf),
    }


def _attribution_root(graph: dict[str, Any]) -> str:
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    node_ids = sorted(str(row.get("node_id", "")) for row in nodes if isinstance(row, dict)) if isinstance(nodes, list) else []
    edge_ids = sorted(str(row.get("edge_id", "")) for row in edges if isinstance(row, dict)) if isinstance(edges, list) else []
    return canon_hash_obj(
        {
            "schema_version": "epistemic_attribution_root_v1",
            "node_ids": node_ids,
            "edge_ids": edge_ids,
        }
    )


def _resolve_cert_profile(
    *,
    cert_profile: dict[str, Any] | None,
    objective_profile_id: str,
) -> tuple[str, int, int, list[dict[str, Any]], str]:
    objective_sha = ensure_sha256(objective_profile_id, reason="SCHEMA_FAIL")
    if cert_profile is None:
        return objective_sha, 0, 0, [], "TASK_ID_ASC"
    validate_schema(cert_profile, "epistemic_cert_profile_v1")
    cert_profile_id = verify_object_id(cert_profile, id_field="cert_profile_id")
    if str(cert_profile.get("acceptance_predicate", "")) != "ECAC_AND_EUFC_MIN_THRESHOLDS_V1":
        fail("SCHEMA_FAIL")
    min_ecac = int(cert_profile.get("min_ecac_lb_q32", 0))
    min_eufc = int(cert_profile.get("min_eufc_q32", 0))
    tasks_raw = cert_profile.get("tasks")
    if not isinstance(tasks_raw, list) or not tasks_raw:
        fail("SCHEMA_FAIL")
    tasks: list[dict[str, Any]] = []
    seen_task_ids: set[str] = set()
    for row in tasks_raw:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        task_id = str(row.get("task_id", "")).strip()
        formula_id = str(row.get("formula_id", "")).strip()
        budget_u64 = int(row.get("budget_u64", 0))
        if not task_id or not formula_id or budget_u64 <= 0:
            fail("SCHEMA_FAIL")
        if task_id in seen_task_ids:
            fail("SCHEMA_FAIL")
        seen_task_ids.add(task_id)
        tasks.append(
            {
                "task_id": task_id,
                "formula_id": formula_id,
                "budget_u64": int(budget_u64),
            }
        )
    tie_break_policy = str(cert_profile.get("tie_break_policy", "TASK_ID_ASC")).strip()
    if tie_break_policy != "TASK_ID_ASC":
        fail("SCHEMA_FAIL")
    return cert_profile_id, min_ecac, min_eufc, tasks, tie_break_policy


def _task_score_q32(*, task: dict[str, Any], stats: dict[str, int]) -> int:
    formula_id = str(task.get("formula_id", ""))
    node_count = int(stats["node_count_u64"])
    edge_count = int(stats["edge_count_u64"])
    good_nodes = max(0, node_count - int(stats["low_conf_count_u64"]))
    if formula_id == "DMPL_PLAN_DELTA_Q32":
        return int(good_nodes << 16)
    if formula_id == "RETRIEVAL_HIT_DELTA_Q32":
        return int((node_count + edge_count) << 15)
    if formula_id == "COMPRESSION_DELTA_Q32":
        return int(good_nodes << 15)
    fail("SCHEMA_FAIL")
    return 0


def _resolve_eufc_credit_context(
    *,
    capsule_tick_u64: int,
    eufc_credit_context: dict[str, Any] | None,
) -> tuple[list[str], str, int, int, list[str]]:
    if eufc_credit_context is None:
        return [], "EUFC_WINDOW", int(capsule_tick_u64), int(capsule_tick_u64), []
    if not isinstance(eufc_credit_context, dict):
        fail("SCHEMA_FAIL")
    mode = str(eufc_credit_context.get("credit_window_mode", "EUFC_WINDOW")).strip()
    if mode != "EUFC_WINDOW":
        fail("SCHEMA_FAIL")
    open_tick_u64 = int(eufc_credit_context.get("credit_window_open_tick_u64", capsule_tick_u64))
    close_tick_u64 = int(eufc_credit_context.get("credit_window_close_tick_u64", capsule_tick_u64))
    if open_tick_u64 < 0 or close_tick_u64 < int(open_tick_u64):
        fail("SCHEMA_FAIL")
    credited_keys_raw = eufc_credit_context.get("credited_credit_keys")
    if credited_keys_raw is None:
        credited_keys_raw = []
    if not isinstance(credited_keys_raw, list):
        fail("SCHEMA_FAIL")
    credited_keys = sorted({ensure_sha256(v, reason="SCHEMA_FAIL") for v in credited_keys_raw})
    receipt_ids_raw = eufc_credit_context.get("credit_window_receipt_ids")
    if receipt_ids_raw is None:
        receipt_ids_raw = []
    if not isinstance(receipt_ids_raw, list):
        fail("SCHEMA_FAIL")
    receipt_ids = [ensure_sha256(v, reason="SCHEMA_FAIL") for v in receipt_ids_raw]
    if len(set(receipt_ids)) != len(receipt_ids):
        fail("SCHEMA_FAIL")
    return credited_keys, mode, int(open_tick_u64), int(close_tick_u64), receipt_ids


def compute_epistemic_certs(
    *,
    capsule: dict[str, Any],
    graph: dict[str, Any],
    type_binding: dict[str, Any],
    objective_profile_id: str,
    cert_profile: dict[str, Any] | None = None,
    eufc_credit_context: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    validate_schema(capsule, "epistemic_capsule_v1")
    validate_schema(type_binding, "epistemic_type_binding_v1")

    capsule_id = ensure_sha256(capsule.get("capsule_id"), reason="SCHEMA_FAIL")
    graph_id = ensure_sha256(graph.get("graph_id"), reason="SCHEMA_FAIL")
    type_binding_id = ensure_sha256(type_binding.get("binding_id"), reason="SCHEMA_FAIL")
    strip_receipt_id = ensure_sha256(capsule.get("strip_receipt_id"), reason="SCHEMA_FAIL")
    objective_profile_id = ensure_sha256(objective_profile_id, reason="SCHEMA_FAIL")
    cert_profile_id, min_ecac_q32, min_eufc_q32, tasks, _tie_break_policy = _resolve_cert_profile(
        cert_profile=cert_profile,
        objective_profile_id=objective_profile_id,
    )

    stats = _graph_stats(graph)
    good_nodes = max(0, int(stats["node_count_u64"]) - int(stats["low_conf_count_u64"]))
    ordered_tasks = sorted(tasks, key=lambda row: str(row.get("task_id", "")))
    task_eval_rows: list[dict[str, Any]] = []
    for task in ordered_tasks:
        task_eval_rows.append(
            {
                "task_id": str(task.get("task_id", "")),
                "formula_id": str(task.get("formula_id", "")),
                "budget_u64": int(task.get("budget_u64", 0)),
                "score_q32": _task_score_q32(task=task, stats=stats),
            }
        )
    if task_eval_rows:
        task_input_ids = sorted(
            canon_hash_obj(
                {
                    "schema_version": "epistemic_cert_task_input_v1",
                    "task_id": str(row.get("task_id", "")),
                    "formula_id": str(row.get("formula_id", "")),
                    "capsule_id": capsule_id,
                    "graph_id": graph_id,
                    "type_binding_id": type_binding_id,
                    "strip_receipt_id": strip_receipt_id,
                }
            )
            for row in task_eval_rows
        )
    else:
        task_input_ids = [
            canon_hash_obj(
                {
                    "schema_version": "epistemic_cert_task_input_v1",
                    "task_id": "default",
                    "formula_id": "default",
                    "capsule_id": capsule_id,
                    "graph_id": graph_id,
                    "type_binding_id": type_binding_id,
                    "strip_receipt_id": strip_receipt_id,
                }
            )
        ]
    task_eval_hash = canon_hash_obj(
        {
            "schema_version": "epistemic_cert_task_eval_v1",
            "rows": task_eval_rows,
        }
    )
    if task_eval_rows:
        score_total = sum(int(row["score_q32"]) for row in task_eval_rows)
        advantage_lb_q32 = int(score_total // len(task_eval_rows))
        utility_delta_q32 = int(score_total)
    else:
        advantage_lb_q32 = int(good_nodes << 16)
        utility_delta_q32 = int((int(stats["node_count_u64"]) + int(stats["edge_count_u64"])) << 16)
    binding_hash = _binding_hash(
        capsule_id=capsule_id,
        graph_id=graph_id,
        type_binding_id=type_binding_id,
        strip_receipt_id=strip_receipt_id,
        objective_profile_id=objective_profile_id,
        cert_profile_id=cert_profile_id,
        stats=stats,
        task_eval_hash=task_eval_hash,
        task_input_ids=task_input_ids,
    )

    ok_b = str(type_binding.get("outcome", "")) == "ACCEPT"
    ecac_ok = ok_b and int(advantage_lb_q32) >= int(min_ecac_q32)
    eufc_ok = ok_b and int(utility_delta_q32) >= int(min_eufc_q32)
    status = "OK" if (ecac_ok and eufc_ok) else "FAIL"
    reason_code = "EPI_OK" if (ecac_ok and eufc_ok) else "CERT_PROFILE_THRESHOLD_FAIL"
    credited_keys, credit_window_mode, credit_window_open_tick_u64, credit_window_close_tick_u64, credit_window_receipt_ids = (
        _resolve_eufc_credit_context(
            capsule_tick_u64=int(capsule.get("tick_u64", 0)),
            eufc_credit_context=eufc_credit_context,
        )
    )

    ecac = {
        "schema_version": "epistemic_ecac_v1",
        "ecac_id": "sha256:" + ("0" * 64),
        "capsule_id": capsule_id,
        "graph_id": graph_id,
        "type_binding_id": type_binding_id,
        "objective_profile_id": objective_profile_id,
        "cert_profile_id": cert_profile_id,
        "strip_receipt_id": strip_receipt_id,
        "task_input_ids": list(task_input_ids),
        "advantage_lb_q32": int(advantage_lb_q32),
        "evaluation_binding_hash": binding_hash,
        "status": status,
        "reason_code": reason_code,
    }
    ecac["ecac_id"] = canon_hash_obj({k: v for k, v in ecac.items() if k != "ecac_id"})
    validate_schema(ecac, "epistemic_ecac_v1")
    verify_object_id(ecac, id_field="ecac_id")

    eufc = {
        "schema_version": "epistemic_eufc_v1",
        "eufc_id": "sha256:" + ("0" * 64),
        "capsule_id": capsule_id,
        "graph_id": graph_id,
        "type_binding_id": type_binding_id,
        "objective_profile_id": objective_profile_id,
        "cert_profile_id": cert_profile_id,
        "strip_receipt_id": strip_receipt_id,
        "task_input_ids": list(task_input_ids),
        "utility_delta_q32": int(utility_delta_q32),
        "attribution_root_hash": _attribution_root(graph),
        "credited_credit_keys": list(credited_keys),
        "credit_window_mode": credit_window_mode,
        "credit_window_open_tick_u64": int(credit_window_open_tick_u64),
        "credit_window_close_tick_u64": int(credit_window_close_tick_u64),
        "credit_window_receipt_ids": list(credit_window_receipt_ids),
        "status": status,
        "reason_code": reason_code,
    }
    eufc["eufc_id"] = canon_hash_obj({k: v for k, v in eufc.items() if k != "eufc_id"})
    validate_schema(eufc, "epistemic_eufc_v1")
    verify_object_id(eufc, id_field="eufc_id")

    return {
        "ecac": ecac,
        "eufc": eufc,
    }


__all__ = ["compute_epistemic_certs"]
