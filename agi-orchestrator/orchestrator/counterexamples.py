"""Counterexample extraction helpers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from cdel.config import load_config_from_path
from cdel.kernel.eval import BoolVal, Evaluator, EvalError, FunVal, IntVal, ListVal, OptionVal, PairVal, Value
from cdel.kernel.parse import parse_definition
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions
from cdel.sealed.config import load_sealed_config


@dataclass(frozen=True)
class CounterexampleResult:
    examples: list[dict]
    harness_id: str


def capture_counterexamples(
    *,
    root_dir: Path,
    config_path: Path,
    baseline: str,
    candidate: str,
    oracle: str,
    candidate_payload: dict,
    artifact_dir: Path | None,
    max_examples: int,
) -> CounterexampleResult:
    if artifact_dir is None or not artifact_dir.exists():
        return CounterexampleResult(examples=[], harness_id="unknown")

    cfg = load_config_from_path(root_dir, config_path)
    sealed_cfg = load_sealed_config(cfg.data, require_keys=False)
    harness_id = sealed_cfg.eval_harness_id
    rows = _load_artifact_rows(artifact_dir)
    if not rows:
        return CounterexampleResult(examples=[], harness_id=harness_id)

    if harness_id == "io-harness-v1":
        examples = _capture_io(
            cfg,
            baseline,
            candidate,
            oracle,
            candidate_payload,
            rows,
            max_examples,
        )
    elif harness_id == "env-harness-v1":
        examples = _capture_env(rows, max_examples)
    elif harness_id == "pyut-harness-v1":
        examples = _capture_pyut(cfg.root, cfg.data, rows, max_examples)
    else:
        examples = []

    return CounterexampleResult(examples=examples, harness_id=harness_id)


def _load_artifact_rows(artifact_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(artifact_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _capture_io(
    cfg,
    baseline: str,
    candidate: str,
    oracle: str,
    candidate_payload: dict,
    rows: list[dict],
    max_examples: int,
) -> list[dict]:
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    defs = load_definitions(cfg, conn, [baseline, oracle])
    for defn in candidate_payload.get("definitions", []):
        parsed = parse_definition(defn)
        defs[parsed.name] = parsed

    max_steps = int((cfg.data.get("evaluator") or {}).get("step_limit", 100000))
    evaluator = Evaluator(max_steps)
    examples: list[dict] = []
    for row in rows:
        if len(examples) >= max_examples:
            break
        if not _row_is_counterexample(row):
            continue
        args_raw = row.get("args")
        target_raw = row.get("target")
        if not isinstance(args_raw, list):
            continue
        try:
            args_vals = [_decode_value(item) for item in args_raw]
        except ValueError:
            continue
        baseline_out = _safe_apply(evaluator, baseline, args_vals, defs)
        candidate_out = _safe_apply(evaluator, candidate, args_vals, defs)
        examples.append(
            {
                "kind": "io",
                "args": args_raw,
                "target": target_raw,
                "baseline_output": _encode_value(baseline_out),
                "candidate_output": _encode_value(candidate_out),
                "baseline_success": row.get("baseline_success"),
                "candidate_success": row.get("candidate_success"),
                "diff": row.get("diff"),
            }
        )
    return examples


def _capture_env(rows: list[dict], max_examples: int) -> list[dict]:
    examples: list[dict] = []
    for row in rows:
        if len(examples) >= max_examples:
            break
        if not _row_is_counterexample(row):
            continue
        example = {
            "kind": "env",
            "episode": row.get("episode") or row.get("i"),
            "start": row.get("start"),
            "goal": row.get("goal"),
            "baseline_success": row.get("baseline_success"),
            "candidate_success": row.get("candidate_success"),
            "baseline_steps": row.get("baseline_steps"),
            "candidate_steps": row.get("candidate_steps"),
            "diff": row.get("diff"),
        }
        examples.append(example)
    return examples


def _capture_pyut(root_dir: Path, cfg_data: dict, rows: list[dict], max_examples: int) -> list[dict]:
    sealed = cfg_data.get("sealed") or {}
    suite_hash = sealed.get("eval_suite_hash")
    if not isinstance(suite_hash, str) or not suite_hash:
        return []
    suite_path = _suite_path(root_dir, suite_hash)
    if suite_path is None or not suite_path.exists():
        return []
    suite_rows = _parse_pyut_suite(suite_path)

    examples: list[dict] = []
    for row in rows:
        if len(examples) >= max_examples:
            break
        if not _row_is_counterexample(row):
            continue
        episode = row.get("episode")
        if not isinstance(episode, int):
            continue
        if episode < 0 or episode >= len(suite_rows):
            continue
        failed_idx = row.get("candidate_failed_test")
        if not isinstance(failed_idx, int):
            continue
        tests = suite_rows[episode].get("tests", [])
        if failed_idx < 0 or failed_idx >= len(tests):
            continue
        test = tests[failed_idx]
        examples.append(
            {
                "kind": "pyut",
                "task_id": suite_rows[episode].get("task_id"),
                "fn_name": suite_rows[episode].get("fn_name"),
                "args": test.get("args"),
                "expected": test.get("expected"),
                "baseline_success": row.get("baseline_success"),
                "candidate_success": row.get("candidate_success"),
                "candidate_error": row.get("candidate_error"),
                "candidate_timeout": row.get("candidate_timeout"),
                "diff": row.get("diff"),
            }
        )
    return examples


def _suite_path(root_dir: Path, suite_hash: str) -> Path | None:
    suites_dir = os.environ.get("CDEL_SUITES_DIR")
    if suites_dir:
        return Path(suites_dir) / f"{suite_hash}.jsonl"
    return root_dir / "sealed_suites" / f"{suite_hash}.jsonl"


def _parse_pyut_suite(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _row_is_counterexample(row: dict) -> bool:
    baseline_success = row.get("baseline_success")
    candidate_success = row.get("candidate_success")
    if isinstance(baseline_success, bool) and isinstance(candidate_success, bool):
        return baseline_success != candidate_success
    return False


def _safe_apply(evaluator: Evaluator, symbol: str, args: list[Value], defs: dict) -> Value | None:
    try:
        return evaluator._apply(FunVal(symbol), args, defs)
    except (EvalError, ValueError):
        return None


def _decode_value(raw: object) -> Value:
    if not isinstance(raw, dict):
        raise ValueError("value must be object")
    tag = raw.get("tag")
    if tag == "int":
        value = raw.get("value")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("int value must be int")
        return IntVal(value)
    if tag == "bool":
        value = raw.get("value")
        if not isinstance(value, bool):
            raise ValueError("bool value must be bool")
        return BoolVal(value)
    if tag == "list":
        items = raw.get("items")
        if not isinstance(items, list):
            raise ValueError("list items must be list")
        return ListVal(tuple(_decode_value(item) for item in items))
    if tag == "none":
        return OptionVal(False, None)
    if tag == "some":
        if "value" not in raw:
            raise ValueError("some value missing")
        return OptionVal(True, _decode_value(raw["value"]))
    if tag == "pair":
        if "left" not in raw or "right" not in raw:
            raise ValueError("pair missing fields")
        return PairVal(_decode_value(raw["left"]), _decode_value(raw["right"]))
    raise ValueError("unknown value tag")


def _encode_value(value: Value | None) -> dict | None:
    if value is None:
        return None
    if isinstance(value, IntVal):
        return {"tag": "int", "value": value.value}
    if isinstance(value, BoolVal):
        return {"tag": "bool", "value": value.value}
    if isinstance(value, ListVal):
        return {"tag": "list", "items": [_encode_value(item) for item in value.items]}
    if isinstance(value, OptionVal):
        if value.is_some:
            return {"tag": "some", "value": _encode_value(value.value)}
        return {"tag": "none"}
    if isinstance(value, PairVal):
        return {"tag": "pair", "left": _encode_value(value.left), "right": _encode_value(value.right)}
    return None
