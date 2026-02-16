"""Pi0 gate evaluation helpers for v1.5r."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from decimal import Decimal, ROUND_FLOOR
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from cdel.sealed.harnesses.env_v1 import HARNESS_HASH, HARNESS_ID
from cdel.sealed.suites import compute_suite_hash_bytes

from .canon import hash_json, sha256_prefixed, write_canon_json
from .family_dsl.runtime import instantiate_family
from .pi0 import baseline_definition, parsed_definitions, programs
from .suite_eval import run_suite_eval


N_GATE = 3


@contextmanager
def _suites_dir(path: Path | None):
    prev = os.environ.get("CDEL_SUITES_DIR")
    tmp = None
    if path is None:
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name)
    os.environ["CDEL_SUITES_DIR"] = str(path)
    try:
        yield path
    finally:
        if prev is None:
            os.environ.pop("CDEL_SUITES_DIR", None)
        else:
            os.environ["CDEL_SUITES_DIR"] = prev
        if tmp is not None:
            tmp.cleanup()


def _decimal_to_str(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-"}:
        text = "0"
    if text == "-0":
        text = "0"
    return text


def _sample_fixed(min_val: str, max_val: str, step_val: str, draw: int) -> str:
    min_d = Decimal(min_val)
    max_d = Decimal(max_val)
    step_d = Decimal(step_val)
    if step_d <= 0:
        raise ValueError("fixed step must be > 0")
    span = max_d - min_d
    steps = int((span / step_d).to_integral_value(rounding=ROUND_FLOOR))
    idx = draw % (steps + 1)
    value = min_d + (step_d * idx)
    return _decimal_to_str(value)


def _sample_int(min_val: int, max_val: int, step: int, draw: int) -> int:
    if step <= 0:
        raise ValueError("int step must be > 0")
    if min_val > max_val:
        raise ValueError("min must be <= max")
    count = ((max_val - min_val) // step) + 1
    idx = draw % count
    return min_val + idx * step


def _u32_stream(seed: bytes, count: int) -> list[int]:
    out: list[int] = []
    counter = 0
    while len(out) < count:
        digest = sha256(seed + counter.to_bytes(4, "little")).digest()
        for i in range(0, len(digest), 4):
            if len(out) >= count:
                break
            out.append(int.from_bytes(digest[i : i + 4], "little", signed=False))
        counter += 1
    return out


def theta_gate(family: dict[str, Any], seed: bytes) -> list[dict[str, Any]]:
    params = family.get("params_schema", [])
    if not isinstance(params, list):
        raise ValueError("params_schema must be list")
    draws = _u32_stream(seed, N_GATE * max(1, len(params)))
    idx = 0
    samples: list[dict[str, Any]] = []
    for _ in range(N_GATE):
        theta: dict[str, Any] = {}
        for param in params:
            name = param.get("name")
            ptype = param.get("type")
            if not isinstance(name, str):
                raise ValueError("param name missing")
            draw = draws[idx]
            idx += 1
            if ptype == "int":
                theta[name] = _sample_int(int(param.get("min")), int(param.get("max")), int(param.get("step")), draw)
            elif ptype == "fixed":
                theta[name] = _sample_fixed(str(param.get("min")), str(param.get("max")), str(param.get("step")), draw)
            else:
                raise ValueError("unknown param type")
        samples.append(theta)
    return samples


def _suite_row_from_instance(instance_spec: dict[str, Any]) -> dict[str, Any]:
    payload = instance_spec.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("instance payload must be object")
    suite_row = payload.get("suite_row")
    if not isinstance(suite_row, dict):
        raise ValueError("instance payload missing suite_row")
    return suite_row


def _write_suite(path: Path, suite_row: dict[str, Any]) -> str:
    line = json.dumps(suite_row, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    suite_hash = compute_suite_hash_bytes(line)
    suite_path = path / f"{suite_hash}.jsonl"
    suite_path.write_bytes(line)
    return suite_hash


def _eval_instance(
    *,
    defs_env: dict[str, object],
    baseline_symbol: str,
    candidate_symbol: str,
    oracle_symbol: str,
    suite_dir: Path,
    suite_row: dict[str, Any],
) -> tuple[int, str]:
    suite_hash = _write_suite(suite_dir, suite_row)
    eval_cfg = {
        "episodes": 1,
        "max_steps": int(suite_row.get("max_steps", 1)),
        "eval_suite_hash": suite_hash,
        "eval_harness_id": HARNESS_ID,
        "eval_harness_hash": HARNESS_HASH,
    }
    diffs, _baseline, _candidate, transcript = run_suite_eval(
        eval_cfg=eval_cfg,
        defs_env=defs_env,
        baseline_symbol=baseline_symbol,
        candidate_symbol=candidate_symbol,
        oracle_symbol=oracle_symbol,
        seed_key=b"pi0-gate",
        project_root=Path("."),
        int_min=-3,
        int_max=3,
        list_max_len=4,
        fun_symbols=[],
        artifact_dir=None,
    )
    success_bit = 1 if diffs and diffs[0] > 0 else 0
    receipt_hash = sha256_prefixed(transcript)
    return success_bit, receipt_hash


def evaluate_pi0_gate(
    *,
    family: dict[str, Any],
    epoch_id: str,
    epoch_commit: dict[str, Any],
    gate_seed: bytes,
    epoch_key: bytes | None = None,
    diagnostics_dir: Path | None = None,
) -> tuple[bool, dict[str, Any], dict[str, Any]]:
    family_id = family.get("family_id")
    if not isinstance(family_id, str):
        raise ValueError("family_id missing")
    epoch_commitment = epoch_commit.get("commitment")
    if not isinstance(epoch_commitment, str):
        raise ValueError("epoch_commitment missing")

    theta_list = theta_gate(family, gate_seed)
    gate_instances = []
    for theta in theta_list:
        gate_instances.append(instantiate_family(family, theta, epoch_commit, epoch_key=epoch_key))

    base_def = baseline_definition()
    base_name = base_def["name"]
    defs_env = parsed_definitions()

    results: list[dict[str, Any]] = []
    pi0_results: list[dict[str, Any]] = []
    failure_reason_codes: list[str] = []

    with _suites_dir(diagnostics_dir) as suite_dir:
        try:
            for program in programs():
                pi_id = program["program_id"]
                defn_json = program["definition"]
                per_instance: list[int] = []
                for idx, instance in enumerate(gate_instances):
                    suite_row = _suite_row_from_instance(instance)
                    success_bit, receipt_hash = _eval_instance(
                        defs_env=defs_env,
                        baseline_symbol=base_name,
                        candidate_symbol=defn_json["name"],
                        oracle_symbol=base_name,
                        suite_dir=suite_dir,
                        suite_row=suite_row,
                    )
                    per_instance.append(success_bit)
                    results.append(
                        {
                            "pi_id": pi_id,
                            "theta_index": idx,
                            "instance_spec_hash": hash_json(instance),
                            "eval_receipt_hash": receipt_hash,
                            "success_bit": success_bit,
                        }
                    )
                pi0_results.append(
                    {
                        "pi_id": pi_id,
                        "per_instance_success": per_instance,
                        "min_success": min(per_instance) if per_instance else 0,
                    }
                )
        except ValueError:
            failure_reason_codes = ["SCHEMA_ERROR"]
        except Exception:
            failure_reason_codes = ["EVAL_ERROR"]

    learnable = False
    if not failure_reason_codes:
        learnable = any(entry["min_success"] == 1 for entry in pi0_results)
        if not learnable:
            failure_reason_codes = ["PI0_ALL_FAIL"]

    pi0_gate_eval = {
        "schema": "pi0_gate_eval_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "epoch_commitment": epoch_commitment,
        "family_id": family_id,
        "theta_gate_list": theta_list,
        "instance_specs": gate_instances,
        "pi0_policy_ids": [program["program_id"] for program in programs()],
        "results": results,
    }
    pi0_gate_eval["report_id"] = hash_json(pi0_gate_eval)

    learnability_report = {
        "schema": "learnability_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "family_id": family_id,
        "pi0_gate_eval_hash": pi0_gate_eval["report_id"],
        "theta_gate": theta_list,
        "gate_instances": [
            {
                "inst_hash": instance["inst_hash"],
                "family_id": instance["family_id"],
                "theta": instance["theta"],
            }
            for instance in gate_instances
        ],
        "pi0_results": pi0_results,
        "learnable": learnable,
        "failure_reason_codes": failure_reason_codes,
    }

    if diagnostics_dir is not None:
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        write_canon_json(diagnostics_dir / "pi0_gate_eval_v1.json", pi0_gate_eval)
        write_canon_json(diagnostics_dir / "learnability_report_v1.json", learnability_report)

    return learnable, learnability_report, pi0_gate_eval
