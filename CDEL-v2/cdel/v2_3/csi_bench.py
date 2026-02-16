"""CSI benchmark runner for v2.3."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any, Callable

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from .constants import require_constants
from .csi_meter import csi_meter_v1

MAX_U64 = (1 << 64) - 1

sys.dont_write_bytecode = True


def _load_entrypoint(entrypoint: str) -> Callable[..., Any]:
    if ":" not in entrypoint:
        raise CanonError("SCHEMA_INVALID")
    module_name, func_name = entrypoint.split(":", 1)
    module = importlib.import_module(module_name)
    func = getattr(module, func_name, None)
    if not callable(func):
        raise CanonError("SCHEMA_INVALID")
    return func


def compute_work_cost(meter_counts: dict[str, int], weights: dict[str, int]) -> int:
    total = 0
    for key, weight in weights.items():
        count = meter_counts.get(key)
        if not isinstance(count, int) or count < 0:
            raise CanonError("NONDETERMINISM")
        if not isinstance(weight, int) or weight < 0:
            raise CanonError("NONDETERMINISM")
        if weight != 0 and count > MAX_U64 // weight:
            raise CanonError("NONDETERMINISM")
        contrib = count * weight
        if total > MAX_U64 - contrib:
            raise CanonError("NONDETERMINISM")
        total += contrib
    return int(total)


def _build_report(
    *,
    run_id: str,
    attempt_id: str,
    tree_hash: str,
    suite: dict[str, Any],
    outputs: dict[str, Any],
    meter_counts: dict[str, int],
    work_cost: int,
) -> dict[str, Any]:
    case_output_hashes = []
    cases = suite.get("cases", [])
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("case_id")
        if not isinstance(case_id, str):
            raise CanonError("SCHEMA_INVALID")
        output = outputs.get(case_id)
        if output is None:
            raise CanonError("SCHEMA_INVALID")
        output_sha = sha256_prefixed(canon_bytes(output))
        case_output_hashes.append({"case_id": case_id, "output_sha256": output_sha})

    report = {
        "schema": "csi_bench_report_v1",
        "run_id": run_id,
        "attempt_id": attempt_id,
        "tree_hash": tree_hash,
        "suite_id": suite.get("suite_id"),
        "case_output_hashes": case_output_hashes,
        "meter_counts": meter_counts,
        "work_cost": int(work_cost),
        "report_head_hash": "__SELF__",
    }
    head = dict(report)
    head.pop("report_head_hash", None)
    report["report_head_hash"] = sha256_prefixed(canon_bytes(head))
    return report


def run_bench_once(
    *,
    run_id: str,
    attempt_id: str,
    tree_hash: str,
    suite: dict[str, Any],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    entrypoint = suite.get("bench_api_entrypoint")
    if not isinstance(entrypoint, str):
        raise CanonError("SCHEMA_INVALID")
    run_suite = _load_entrypoint(entrypoint)

    with csi_meter_v1() as meter:
        outputs = run_suite(suite, inputs)

    if not isinstance(outputs, dict):
        raise CanonError("SCHEMA_INVALID")

    constants = require_constants()
    weights = constants.get("CSI_WORK_COST_WEIGHTS_V1", {})
    if not isinstance(weights, dict):
        raise CanonError("SCHEMA_INVALID")
    work_cost = compute_work_cost(meter.counts, weights)

    return _build_report(
        run_id=run_id,
        attempt_id=attempt_id,
        tree_hash=tree_hash,
        suite=suite,
        outputs=outputs,
        meter_counts=dict(meter.counts),
        work_cost=work_cost,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CSI benchmark v1")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--run_id", required=True)
    parser.add_argument("--attempt_id", required=True)
    parser.add_argument("--tree_hash", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    suite = load_canon_json(Path(args.suite))
    inputs = load_canon_json(Path(args.inputs))

    report = run_bench_once(
        run_id=args.run_id,
        attempt_id=args.attempt_id,
        tree_hash=args.tree_hash,
        suite=suite,
        inputs=inputs,
    )
    write_canon_json(Path(args.out), report)


if __name__ == "__main__":
    main()
