#!/usr/bin/env python3
"""Frozen oracle benchmark suite runner (v1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from tools.omega.oracle_dsl_v1 import OracleDslError, eval_program_with_stats, parse_ast

_Q32_ONE = 1 << 32
_ZERO_SHA = "sha256:" + ("0" * 64)


def _q32(num: int, den: int) -> int:
    if den <= 0:
        return 0
    return int((int(num) * _Q32_ONE) // int(den))


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"payload is not object: {path.as_posix()}")
    return payload


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise RuntimeError("predictions row must be JSON object")
        rows.append(payload)
    return rows


def _count_nodes(node: Any) -> int:
    if not isinstance(node, dict):
        raise OracleDslError("AST_INVALID")
    if set(node.keys()) != {"v", "op", "a"}:
        raise OracleDslError("AST_INVALID")
    args = node.get("a")
    if not isinstance(args, list):
        raise OracleDslError("AST_INVALID")
    total = 1
    for row in args:
        if isinstance(row, dict):
            total += _count_nodes(row)
    return int(total)


def _prediction_map(predictions_path: Path) -> dict[str, str]:
    rows = _jsonl_rows(predictions_path)
    out: dict[str, str] = {}
    for row in rows:
        task_id = str(row.get("id", "")).strip()
        if not task_id:
            raise RuntimeError("prediction id missing")
        if task_id in out:
            raise RuntimeError(f"duplicate prediction id: {task_id}")
        out[task_id] = str(row.get("prediction", "")).strip()
    return out


def run_oracle_benchmark_once(
    *,
    inputs_pack_path: Path,
    hidden_tests_pack_path: Path,
    predictions_path: Path,
    suite_id: str,
    suite_name: str,
    suite_set_id: str,
) -> dict[str, Any]:
    inputs_pack = _load_json(inputs_pack_path)
    hidden_pack = _load_json(hidden_tests_pack_path)
    if str(inputs_pack.get("schema_version", "")).strip() != "oracle_task_inputs_pack_v1":
        raise RuntimeError("inputs pack schema mismatch")
    if str(hidden_pack.get("schema_version", "")).strip() != "oracle_hidden_tests_pack_v1":
        raise RuntimeError("hidden tests pack schema mismatch")

    inputs_tasks = inputs_pack.get("tasks")
    hidden_tasks = hidden_pack.get("tasks")
    if not isinstance(inputs_tasks, list) or not isinstance(hidden_tasks, list):
        raise RuntimeError("pack tasks must be arrays")

    hidden_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in hidden_tasks:
        if not isinstance(row, dict):
            raise RuntimeError("hidden task must be object")
        task_id = str(row.get("id", "")).strip()
        hidden_examples = row.get("hidden_examples")
        if not task_id or not isinstance(hidden_examples, list) or len(hidden_examples) != 32:
            raise RuntimeError("hidden task malformed")
        hidden_by_id[task_id] = [dict(item) for item in hidden_examples if isinstance(item, dict)]
        if len(hidden_by_id[task_id]) != 32:
            raise RuntimeError("hidden examples malformed")

    predictions = _prediction_map(predictions_path)

    tasks_total = 0
    tasks_with_prediction = 0
    tasks_passed = 0
    ast_nodes_sum = 0
    ast_nodes_count = 0
    eval_steps_sum = 0
    eval_calls = 0

    per_task_rows: list[dict[str, Any]] = []

    for row in inputs_tasks:
        if not isinstance(row, dict):
            raise RuntimeError("input task must be object")
        task_id = str(row.get("id", "")).strip()
        if not task_id:
            raise RuntimeError("input task id missing")
        hidden_examples = hidden_by_id.get(task_id)
        if hidden_examples is None:
            raise RuntimeError(f"missing hidden task id: {task_id}")

        tasks_total += 1
        pred_text = predictions.get(task_id, "")
        if not pred_text:
            per_task_rows.append({"id": task_id, "pass_b": False, "reason": "MISSING_PREDICTION"})
            continue

        tasks_with_prediction += 1
        pass_b = False
        reason = "OK"
        node_count = 0
        try:
            ast_obj = json.loads(pred_text)
            node_count = _count_nodes(ast_obj)
            if node_count > 64:
                reason = "MAX_AST_NODES_EXCEEDED"
            else:
                program = parse_ast(ast_obj)
                all_match = True
                for ex in hidden_examples:
                    in_obj = ex.get("in")
                    expected = ex.get("out")
                    actual, steps_used = eval_program_with_stats(program, in_obj, 2000)
                    eval_steps_sum += int(steps_used)
                    eval_calls += 1
                    if actual != expected:
                        all_match = False
                        reason = "MISMATCH"
                        break
                if all_match:
                    pass_b = True
        except OracleDslError as exc:
            reason = str(exc.code)
        except Exception:
            reason = "RUNTIME_ERROR"

        if node_count > 0:
            ast_nodes_sum += int(node_count)
            ast_nodes_count += 1

        if pass_b:
            tasks_passed += 1
        per_task_rows.append({"id": task_id, "pass_b": bool(pass_b), "reason": str(reason), "ast_nodes_u32": int(node_count)})

    pass_rate_q32 = _q32(tasks_passed, tasks_total)
    coverage_q32 = _q32(tasks_with_prediction, tasks_total)
    avg_ast_nodes_q32 = _q32(ast_nodes_sum, ast_nodes_count)
    avg_eval_steps_q32 = _q32(eval_steps_sum, eval_calls)

    metrics = {
        "pass_rate_q32": {"q": int(pass_rate_q32)},
        "coverage_q32": {"q": int(coverage_q32)},
        "avg_ast_nodes_q32": {"q": int(avg_ast_nodes_q32)},
        "avg_eval_steps_q32": {"q": int(avg_eval_steps_q32)},
        "holdout_accuracy_q32": {"q": int(pass_rate_q32)},
        "holdout_coverage_q32": {"q": int(coverage_q32)},
    }

    predictions_sha = "sha256:" + hashlib.sha256(predictions_path.read_bytes()).hexdigest()
    predictions_bytes = int(predictions_path.stat().st_size)

    suite_gate_results = [
        {
            "gate_id": "ORACLE_COVERAGE_FULL",
            "passed_b": bool(coverage_q32 == _Q32_ONE),
            "detail": f"coverage_q32={int(coverage_q32)}",
        },
        {
            "gate_id": "ORACLE_EVAL_EXECUTED",
            "passed_b": True,
            "detail": f"tasks_total={int(tasks_total)}",
        },
    ]

    suite_outcome = "PASS" if bool(coverage_q32 == _Q32_ONE) else "FAIL"

    executed_suite = {
        "suite_id": str(suite_id or _ZERO_SHA),
        "suite_name": str(suite_name or "oracle_suite"),
        "suite_set_id": str(suite_set_id or _ZERO_SHA),
        "suite_source": "ANCHOR",
        "suite_visibility": "HOLDOUT",
        "ledger_ordinal_u64": 0,
        "suite_outcome": suite_outcome,
        "metrics": metrics,
        "gate_results": suite_gate_results,
        "holdout_execution": {
            "holdout_policy_id": _ZERO_SHA,
            "inputs_pack_id": str(inputs_pack.get("pack_id", _ZERO_SHA)),
            "hidden_tests_pack_id": str(hidden_pack.get("pack_id", _ZERO_SHA)),
            "harness_truth_pack_id": str(hidden_pack.get("pack_id", _ZERO_SHA)),
            "candidate_outputs_hash": str(predictions_sha),
            "candidate_outputs_bytes_u64": int(predictions_bytes),
            "candidate_output_files": [
                {
                    "path": "predictions.jsonl",
                    "sha256": str(predictions_sha),
                    "bytes_u64": int(predictions_bytes),
                }
            ],
            "io_contract_enforced_b": True,
            "candidate_stage_status": "PASS",
            "harness_stage_status": "PASS" if tasks_passed == tasks_total else "FAIL",
            "sandbox_available_b": False,
            "sandbox_enforced_b": False,
            "gates": suite_gate_results,
            "oracle_task_rows": per_task_rows,
            "tasks_total_u64": int(tasks_total),
            "tasks_passed_u64": int(tasks_passed),
            "tasks_with_prediction_u64": int(tasks_with_prediction),
        },
        "budget_outcome": {
            "within_budget_b": True,
            "cpu_ms_u64": 0,
            "wall_ms_u64": 0,
            "disk_mb_u64": 0,
        },
    }

    receipt_no_id = {
        "schema_version": "benchmark_run_receipt_v2",
        "receipt_id": _ZERO_SHA,
        "ek_id": _ZERO_SHA,
        "anchor_suite_set_id": str(suite_set_id or _ZERO_SHA),
        "extensions_ledger_id": _ZERO_SHA,
        "suite_runner_id": _ZERO_SHA,
        "executed_suites": [executed_suite],
        "aggregate_metrics": metrics,
        "gate_results": suite_gate_results,
        "budget_outcome": {
            "within_budget_b": True,
            "cpu_ms_u64": 0,
            "wall_ms_u64": 0,
            "disk_mb_u64": 0,
        },
    }
    payload = dict(receipt_no_id)
    no_id = dict(receipt_no_id)
    no_id.pop("receipt_id", None)
    payload["receipt_id"] = canon_hash_obj(no_id)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="omega_benchmark_suite_oracle_v1")
    parser.add_argument("--inputs_pack_path", required=True)
    parser.add_argument("--hidden_tests_pack_path", required=True)
    parser.add_argument("--predictions_path", required=True)
    parser.add_argument("--suite_id", default=_ZERO_SHA)
    parser.add_argument("--suite_name", default="oracle_suite")
    parser.add_argument("--suite_set_id", default=_ZERO_SHA)
    parser.add_argument("--out", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = run_oracle_benchmark_once(
        inputs_pack_path=Path(str(args.inputs_pack_path)).resolve(),
        hidden_tests_pack_path=Path(str(args.hidden_tests_pack_path)).resolve(),
        predictions_path=Path(str(args.predictions_path)).resolve(),
        suite_id=str(args.suite_id).strip() or _ZERO_SHA,
        suite_name=str(args.suite_name).strip() or "oracle_suite",
        suite_set_id=str(args.suite_set_id).strip() or _ZERO_SHA,
    )

    out = str(args.out).strip()
    if out:
        out_path = Path(out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_canon_json(out_path, payload)

    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
