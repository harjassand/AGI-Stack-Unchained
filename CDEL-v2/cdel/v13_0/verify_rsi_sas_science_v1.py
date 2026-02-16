"""Verifier for RSI SAS-Science v13.0."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from .sas_science_dataset_v1 import load_manifest, compute_dataset_receipt, compute_split_receipt, load_dataset
from .sas_science_ir_v1 import validate_ir, compute_complexity
from .sas_science_fit_v1 import fit_theory
from .sas_science_eval_v1 import compute_report_hash
from .sealed_science_eval_client_v1 import SealedEvalClientError, start as start_sealed_eval_client
from .sas_science_selection_v1 import select_candidate
from .sas_science_canon_v1 import canonicalize_law
from .sas_science_ledger_v1 import SAS_SCIENCE_EVENT_TYPES, load_ledger, validate_chain
from .sas_science_math_v1 import parse_q32_obj

try:
    from jsonschema import Draft202012Validator
    from jsonschema import RefResolver
except Exception:  # pragma: no cover
    Draft202012Validator = None
    RefResolver = None


class SASScienceError(CanonError):
    pass


SCHEMA_STORE_CACHE: dict[str, dict[str, Any]] = {}
VALIDATOR_CACHE: dict[tuple[str, str], Any] = {}


def _fail(reason: str) -> None:
    raise SASScienceError(reason)


def _load_json(path: Path) -> Any:
    try:
        return load_canon_json(path)
    except CanonError:
        _fail("INVALID:SCHEMA_FAIL")
    return {}


def _require_schema(obj: Any, schema_version: str) -> dict[str, Any]:
    if not isinstance(obj, dict) or obj.get("schema_version") != schema_version:
        _fail("INVALID:SCHEMA_FAIL")
    return obj


def _validate_jsonschema(obj: dict[str, Any], schema_name: str, schema_dir: Path) -> None:
    if Draft202012Validator is None:
        return

    schema_root = schema_dir.resolve()
    schema_root_key = schema_root.as_posix()
    schema_path = schema_dir / f"{schema_name}.jsonschema"
    if not schema_path.exists():
        _fail("INVALID:SCHEMA_FAIL")

    store = SCHEMA_STORE_CACHE.get(schema_root_key)
    if store is None:
        store = {}
        for path in schema_root.glob("*.jsonschema"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                schema_id = payload.get("$id")
                if isinstance(schema_id, str):
                    store[schema_id] = payload
                    if not schema_id.endswith(".jsonschema"):
                        store[f"{schema_id}.jsonschema"] = payload
                store[path.name] = payload
                store[path.resolve().as_uri()] = payload
        SCHEMA_STORE_CACHE[schema_root_key] = store

    validator_key = (schema_root_key, schema_name)
    validator = VALIDATOR_CACHE.get(validator_key)
    if validator is None:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema = dict(schema)
        schema["$id"] = schema_path.resolve().as_uri()
        if RefResolver is not None:
            resolver = RefResolver.from_schema(schema, store=store)
            validator = Draft202012Validator(schema, resolver=resolver)
        else:
            validator = Draft202012Validator(schema)
        VALIDATOR_CACHE[validator_key] = validator

    validator.validate(obj)


def _require_sha256(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        _fail("INVALID:SCHEMA_FAIL")
    return value


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema_dir() -> Path:
    return _repo_root() / "Genesis" / "schema" / "v13_0"


def _check_root_manifest(state_dir: Path, campaign_tag: str) -> None:
    health_dir = state_dir / "health"
    manifests = list(health_dir.glob("sha256_*.sas_root_manifest_v1.json"))
    if not manifests:
        return
    manifest = _load_json(manifests[0])
    if manifest.get("schema_version") != "sas_root_manifest_v1":
        _fail("INVALID:SCHEMA_FAIL")


def _hash_name_ok(path: Path, payload: dict[str, Any], suffix: str) -> None:
    h = sha256_prefixed(canon_bytes(payload))
    expected = f"sha256_{h.split(':',1)[1]}.{suffix}"
    if path.name != expected:
        _fail("INVALID:SCHEMA_FAIL")


def verify(state_dir: Path, *, mode: str = "full") -> str:
    state_dir = state_dir.resolve()
    # Accept either run root (with state/ subdir) or direct state directory.
    if (state_dir / "state").exists():
        state_dir = state_dir / "state"
    _check_root_manifest(state_dir, "rsi_sas_science_v13_0")
    schema_dir = _schema_dir()

    config_dir = state_dir.parent / "config"
    control_dir = state_dir / "control"
    ledger_path = state_dir / "ledger" / "sas_science_synthesis_ledger_v1.jsonl"

    for name in ["ENABLE_RESEARCH", "ENABLE_SAS_SCIENCE", "SAS_SCIENCE_LEASE.json"]:
        if not (control_dir / name).exists():
            _fail("INVALID:LOCKED")

    pack_path = config_dir / "rsi_sas_science_pack_v1.json"
    pack = _load_json(pack_path)
    if not isinstance(pack, dict) or pack.get("schema_version") != "rsi_sas_science_pack_v1":
        _fail("INVALID:SCHEMA_FAIL")

    perf_policy = _load_json(config_dir / "sas_science_perf_policy_v1.json")
    ir_policy = _load_json(config_dir / "sas_science_ir_policy_v1.json")
    perf_hash = sha256_prefixed(canon_bytes(perf_policy))
    ir_hash = sha256_prefixed(canon_bytes(ir_policy))
    if pack.get("perf_policy_hash") != perf_hash:
        _fail("INVALID:PERF_POLICY_HASH_MISMATCH")
    if pack.get("ir_policy_hash") != ir_hash:
        _fail("INVALID:IR_POLICY_HASH_MISMATCH")

    suite_dev = _load_json(config_dir / "sas_science_suitepack_dev_v1.json")
    suite_held = _load_json(config_dir / "sas_science_suitepack_heldout_v1.json")
    suite_dev_hash = sha256_prefixed(canon_bytes(suite_dev))
    suite_held_hash = sha256_prefixed(canon_bytes(suite_held))

    # dataset artifacts
    data_dir = state_dir / "data"
    manifest_path = next(data_dir.glob("manifest/sha256_*.sas_science_dataset_manifest_v1.json"), None)
    csv_path = next(data_dir.glob("csv/sha256_*.dataset.csv"), None)
    if not manifest_path or not csv_path:
        _fail("INVALID:SCHEMA_FAIL")
    manifest = load_manifest(manifest_path)
    csv_bytes = csv_path.read_bytes()
    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    csv_hash = sha256_prefixed(csv_bytes)

    receipt_path = next(data_dir.glob("receipts/sha256_*.sas_science_dataset_receipt_v1.json"), None)
    split_path = next(data_dir.glob("receipts/sha256_*.sas_science_split_receipt_v1.json"), None)
    if not receipt_path or not split_path:
        _fail("INVALID:SCHEMA_FAIL")
    dataset_receipt = _load_json(receipt_path)
    split_receipt = _load_json(split_path)

    _validate_jsonschema(dataset_receipt, "sas_science_dataset_receipt_v1", schema_dir)
    _validate_jsonschema(split_receipt, "sas_science_split_receipt_v1", schema_dir)

    recomputed_receipt = compute_dataset_receipt(
        manifest=manifest,
        csv_bytes=csv_bytes,
        row_count=len(load_dataset(csv_path, manifest).times_q32),
    )
    if dataset_receipt.get("dataset_id") != recomputed_receipt.get("dataset_id"):
        _fail("INVALID:DATASET_HASH_MISMATCH")

    recomputed_split = compute_split_receipt(
        manifest=manifest,
        dataset_id=recomputed_receipt.get("dataset_id"),
        row_count=recomputed_receipt.get("row_count"),
    )
    if split_receipt.get("split_id") != recomputed_split.get("split_id"):
        _fail("INVALID:SPLIT_HASH_MISMATCH")

    # IRs
    ir_dir = state_dir / "theory" / "ir"
    ir_paths = list(ir_dir.glob("sha256_*.sas_science_theory_ir_v1.json"))
    if not ir_paths:
        _fail("INVALID:SCHEMA_FAIL")
    irs: dict[str, dict[str, Any]] = {}
    for path in ir_paths:
        ir = _load_json(path)
        _validate_jsonschema(ir, "sas_science_theory_ir_v1", schema_dir)
        validate_ir(ir, manifest=manifest, ir_policy=ir_policy)
        theory_id = ir.get("theory_id")
        if not isinstance(theory_id, str):
            _fail("INVALID:SCHEMA_FAIL")
        irs[theory_id] = ir

    # Fit receipts
    fit_dir = state_dir / "fit" / "receipts"
    fit_paths = list(fit_dir.glob("sha256_*.sas_science_fit_receipt_v1.json"))
    if not fit_paths:
        _fail("INVALID:SCHEMA_FAIL")
    fit_map: dict[str, dict[str, Any]] = {}
    dataset_obj = load_dataset(csv_path, manifest)
    for path in fit_paths:
        receipt = _load_json(path)
        _validate_jsonschema(receipt, "sas_science_fit_receipt_v1", schema_dir)
        theory_id = receipt.get("theory_id")
        if theory_id not in irs:
            _fail("INVALID:SCHEMA_FAIL")
        recomputed = fit_theory(dataset=dataset_obj, ir=irs[theory_id], split_receipt=split_receipt, ir_policy=ir_policy)
        if recomputed.get("receipt_id") != receipt.get("receipt_id"):
            _fail("INVALID:FIT_POLICY_MISMATCH")
        fit_map[theory_id] = receipt

    # Eval reports + sealed receipts
    eval_dir = state_dir / "eval" / "reports"
    sealed_dir = state_dir / "eval" / "sealed"
    eval_reports: dict[tuple[str, str], dict[str, Any]] = {}
    for report_path in eval_dir.glob("sha256_*.sas_science_eval_report_v1.json"):
        report = _load_json(report_path)
        _validate_jsonschema(report, "sas_science_eval_report_v1", schema_dir)
        expected_name = f"sha256_{compute_report_hash(report).split(':',1)[1]}.sas_science_eval_report_v1.json"
        if report_path.name != expected_name:
            _fail("INVALID:SCHEMA_FAIL")
        theory_id = report.get("theory_id")
        eval_kind = report.get("eval_kind")
        if theory_id not in irs or eval_kind not in ("DEV", "HELDOUT"):
            _fail("INVALID:SCHEMA_FAIL")
        eval_reports[(theory_id, eval_kind)] = report

    if not eval_reports:
        _fail("INVALID:SCHEMA_FAIL")

    sealed_map: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sealed_dir.glob("sha256_*.sealed_science_eval_receipt_v1.json"):
        sealed = _load_json(path)
        _validate_jsonschema(sealed, "sealed_science_eval_receipt_v1", schema_dir)
        receipt_hash = sha256_prefixed(canon_bytes(sealed))
        expected_name = f"sha256_{receipt_hash.split(':',1)[1]}.sealed_science_eval_receipt_v1.json"
        if path.name != expected_name:
            _fail("INVALID:SCHEMA_FAIL")
        key = (sealed.get("theory_id"), sealed.get("eval_kind"))
        sealed_map[key] = sealed

    for (theory_id, eval_kind), report in eval_reports.items():
        sealed = sealed_map.get((theory_id, eval_kind))
        if sealed is None:
            _fail("INVALID:EVAL_OUTSIDE_SEALED")
        if sealed.get("eval_report_hash") != compute_report_hash(report):
            _fail("INVALID:SEALED_EVAL_RECEIPT_MISMATCH")

    # Re-run sealed eval for determinism
    lease_path = control_dir / "SAS_SCIENCE_LEASE.json"
    replay_targets = sorted(eval_reports.items(), key=lambda item: (item[0][0], item[0][1]))
    replay_jobs: list[dict[str, Any]] = []
    for (theory_id, eval_kind), _report in replay_targets:
        ir_path = ir_dir / f"sha256_{theory_id.split(':',1)[1]}.sas_science_theory_ir_v1.json"
        fit_receipt_id = str(fit_map[theory_id]["receipt_id"])
        fit_path = fit_dir / f"sha256_{fit_receipt_id.split(':',1)[1]}.sas_science_fit_receipt_v1.json"
        suite_path = config_dir / ("sas_science_suitepack_dev_v1.json" if eval_kind == "DEV" else "sas_science_suitepack_heldout_v1.json")
        replay_jobs.append(
            {
                "schema_version": "sealed_science_eval_job_v1",
                "dataset_manifest": str(manifest_path),
                "dataset_csv": str(csv_path),
                "dataset_receipt": str(receipt_path),
                "split_receipt": str(split_path),
                "theory_ir": str(ir_path),
                "fit_receipt": str(fit_path),
                "suitepack": str(suite_path),
                "perf_policy": str(config_dir / "sas_science_perf_policy_v1.json"),
                "ir_policy": str(config_dir / "sas_science_ir_policy_v1.json"),
                "eval_kind": eval_kind,
                "lease": str(lease_path) if eval_kind == "HELDOUT" else None,
                "cache_keys": {
                    "dataset_manifest_hash": manifest_hash,
                    "dataset_csv_hash": csv_hash,
                    "dataset_receipt_hash": sha256_prefixed(canon_bytes(dataset_receipt)),
                    "split_receipt_hash": sha256_prefixed(canon_bytes(split_receipt)),
                    "suitepack_hash": suite_dev_hash if eval_kind == "DEV" else suite_held_hash,
                    "perf_policy_hash": perf_hash,
                    "ir_policy_hash": ir_hash,
                },
            }
        )

    env = dict(os.environ)
    cdel_root = _repo_root() / "CDEL-v2"
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(cdel_root) + (os.pathsep + existing if existing else "")
    replay_results: list[dict[str, Any]] = []
    try:
        sealed_client = start_sealed_eval_client(sys.executable, env)
    except SealedEvalClientError:
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    try:
        replay_results = sealed_client.run_jobs(replay_jobs)
    except SealedEvalClientError:
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    finally:
        try:
            sealed_client.close()
        except SealedEvalClientError:
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    if len(replay_results) != len(replay_targets):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    for ((_, _eval_kind), report), result in zip(replay_targets, replay_results):
        if not isinstance(result, dict):
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
        eval_new = result.get("eval_report")
        sealed_new = result.get("sealed_receipt")
        if not isinstance(eval_new, dict) or not isinstance(sealed_new, dict):
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

        expected_report_hash = compute_report_hash(report)
        replay_report_hash = compute_report_hash(eval_new)
        if replay_report_hash != expected_report_hash:
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
        if replay_report_hash != result.get("eval_report_hash"):
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

        replay_sealed_hash = sha256_prefixed(canon_bytes(sealed_new))
        if replay_sealed_hash != result.get("sealed_receipt_hash"):
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
        if sealed_new.get("eval_report_hash") != expected_report_hash:
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

        expected_work = int(report.get("workmeter", {}).get("work_cost_total", -1))
        replay_work = int(eval_new.get("workmeter", {}).get("work_cost_total", -2))
        if replay_work != expected_work:
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
        if int(result.get("work_cost_total", -3)) != expected_work:
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    # Selection receipt
    sel_dir = state_dir / "selection"
    sel_paths = list(sel_dir.glob("sha256_*.sas_science_selection_receipt_v1.json"))
    if not sel_paths:
        _fail("INVALID:SCHEMA_FAIL")
    selection = _load_json(sel_paths[0])
    _validate_jsonschema(selection, "sas_science_selection_receipt_v1", schema_dir)

    selected_id = selection.get("selected_theory_id")
    if selected_id not in irs:
        _fail("INVALID:SCHEMA_FAIL")

    # Performance gates
    baseline_ids = [ir_id for ir_id, ir in irs.items() if str(ir.get("theory_kind")).startswith("BASELINE")]
    cand_ids = [ir_id for ir_id, ir in irs.items() if str(ir.get("theory_kind")).startswith("CANDIDATE")]

    def _metric(report: dict[str, Any], key: str) -> int:
        return parse_q32_obj(report.get("metrics", {}).get(key))

    def _work(report: dict[str, Any]) -> int:
        return int(report.get("workmeter", {}).get("work_cost_total", 0))

    base_reports_held = [eval_reports[(bid, "HELDOUT")] for bid in baseline_ids if (bid, "HELDOUT") in eval_reports]
    if not base_reports_held:
        _fail("INVALID:SCHEMA_FAIL")

    # baseline min for metrics
    base_mse = min(_metric(r, "mse_accel_q32") for r in base_reports_held)
    base_rmse = min(_metric(r, "rmse_pos1_q32") for r in base_reports_held)
    base_roll64 = min(_metric(r, "rmse_roll_64_q32") for r in base_reports_held)
    base_roll128 = min(_metric(r, "rmse_roll_128_q32") for r in base_reports_held)
    base_roll256 = min(_metric(r, "rmse_roll_256_q32") for r in base_reports_held)
    base_work = max(_work(r) for r in base_reports_held)

    cand_report = eval_reports.get((selected_id, "HELDOUT"))
    if cand_report is None:
        _fail("INVALID:SCHEMA_FAIL")

    cand_mse = _metric(cand_report, "mse_accel_q32")
    cand_rmse = _metric(cand_report, "rmse_pos1_q32")
    cand_roll64 = _metric(cand_report, "rmse_roll_64_q32")
    cand_roll128 = _metric(cand_report, "rmse_roll_128_q32")
    cand_roll256 = _metric(cand_report, "rmse_roll_256_q32")

    if cand_mse < 0 or cand_rmse < 0:
        _fail("INVALID:METRIC_OUT_OF_RANGE")

    if cand_mse * 100 > base_mse * 5:
        _fail("INVALID:PERF_GATE_FAIL:mse_accel")
    if cand_rmse * 100 > base_rmse * 10:
        _fail("INVALID:PERF_GATE_FAIL:rmse_pos1")
    if not (cand_roll64 <= cand_roll128 <= cand_roll256 * 2):
        _fail("INVALID:PERF_GATE_FAIL:rollout")

    cand_work = _work(cand_report)
    if cand_work * 100 > base_work * 500:
        _fail("INVALID:WORK_BUDGET_EXCEEDED")

    # Complexity gates
    comp = compute_complexity(irs[selected_id])
    if comp["term_count"] > int(ir_policy.get("max_term_count", 4)):
        _fail("INVALID:COMPLEXITY_GATE_FAIL")
    if comp["param_count"] > int(ir_policy.get("max_param_count", 4)):
        _fail("INVALID:COMPLEXITY_GATE_FAIL")
    if comp["node_count"] > int(ir_policy.get("max_node_count", 80)):
        _fail("INVALID:COMPLEXITY_GATE_FAIL")

    # MDL selection check
    lambda_q32 = perf_policy.get("mdl_lambda_q32")
    best_id, best_mdl = select_candidate(
        candidate_ids=cand_ids,
        eval_reports={cid: eval_reports[(cid, "HELDOUT")] for cid in cand_ids if (cid, "HELDOUT") in eval_reports},
        irs=irs,
        lambda_q32_obj=lambda_q32,
    )
    if best_id != selected_id:
        _fail("INVALID:MDL_SELECTION_INCONSISTENT")

    # Newton law check
    canon = canonicalize_law(ir=irs[selected_id], fit_receipt=fit_map[selected_id], ir_policy=ir_policy)
    if canon.get("law_kind") not in ("NEWTON_NBODY_V1", "NEWTON_CENTRAL_V1"):
        _fail("INVALID:LAW_NOT_NEWTONIAN")

    # Ledger check
    entries = load_ledger(ledger_path)
    validate_chain(entries, allowed_events=SAS_SCIENCE_EVENT_TYPES)

    return "VALID"


def report_path_hash(report: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(report))


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_sas_science_v1")
    parser.add_argument("--mode", default="full")
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()
    result = verify(Path(args.state_dir), mode=args.mode)
    print(result)


if __name__ == "__main__":
    import sys
    main()
