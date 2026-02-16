"""Fail-closed verifier for RSI SAS-Metasearch v16.1."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from ..v13_0.sas_science_eval_v1 import compute_report_hash
from ..v13_0.sealed_science_eval_client_v1 import SealedEvalClientError, start as start_sealed_eval_client
from ..v13_0.verify_rsi_sas_science_v1 import SASScienceError, verify as verify_v13
from .metasearch_build_rust_v1 import (
    MetaSearchRustBuildError,
    build_release_binary_with_receipt,
    crate_tree_hash,
    file_hash,
    load_py_toolchain_manifest,
    load_rust_toolchain_manifest,
    run_planner,
    scan_rust_sources,
)
from .metasearch_corpus_v1 import MetaSearchCorpusError, load_suitepack
from .metasearch_run_v1 import run_sas_metasearch
from .metasearch_selection_v1 import build_selection_receipt
from .metasearch_trace_v2 import load_trace_rows, validate_hash_chain

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message="jsonschema.RefResolver is deprecated.*",
)

try:
    from jsonschema import Draft202012Validator
    from jsonschema import RefResolver
except Exception:  # pragma: no cover
    Draft202012Validator = None
    RefResolver = None


class MetaSearchVerifyError(CanonError):
    pass


SCHEMA_STORE_CACHE: dict[str, dict[str, Any]] = {}
VALIDATOR_CACHE: dict[tuple[str, str], Any] = {}


def _fail(reason: str) -> None:
    raise MetaSearchVerifyError(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema_dir() -> Path:
    return _repo_root() / "Genesis" / "schema" / "v16_1"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        obj = load_canon_json(path)
    except CanonError:
        _fail("INVALID:SCHEMA_FAIL")
    if not isinstance(obj, dict):
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


def _resolve_run_state(path: Path) -> tuple[Path, Path]:
    root = path.resolve()
    candidate = root / "daemon" / "rsi_sas_metasearch_v16_1" / "state"
    if candidate.exists():
        return candidate, candidate.parent
    candidate = root / "state"
    if candidate.exists() and (root / "config").exists():
        return candidate, root
    if (root / "control").exists() and (root.parent / "config").exists():
        return root, root.parent
    _fail("INVALID:SCHEMA_FAIL")
    return root, root


def _collect_single(path: Path, pattern: str) -> Path:
    rows = sorted(path.glob(pattern))
    if len(rows) != 1:
        _fail("INVALID:SCHEMA_FAIL")
    return rows[0]


def _collect_by_hash(path: Path, suffix: str, h: str) -> Path:
    if not isinstance(h, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", h):
        _fail("INVALID:SCHEMA_FAIL")
    target = path / f"sha256_{h.split(':',1)[1]}.{suffix}"
    if not target.exists() or not target.is_file():
        _fail("INVALID:MISSING_STATE_INPUT")
    return target


def _require_bundle_fields(bundle: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "created_utc",
        "bundle_id",
        "pack_hash",
        "policy_hash",
        "trace_corpus_hash",
        "prior_hash",
        "plan_hash",
        "baseline_search_config_hash",
        "candidate_search_config_hash",
        "dataset_manifest_hash",
        "dataset_csv_hash",
        "dataset_receipt_hash",
        "split_receipt_hash",
        "toolchain_manifest_py_hash",
        "toolchain_manifest_rust_hash",
        "rust_crate_tree_hash",
        "rust_build_receipt_hash",
        "rust_binary_hash",
        "baseline_eval_trace_hash",
        "candidate_eval_trace_hash",
        "baseline_selection_receipt_hash",
        "candidate_selection_receipt_hash",
        "compute_report_hash",
        "baseline_selected_law_kind",
        "baseline_selected_theory_id",
        "candidate_selected_law_kind",
        "candidate_selected_theory_id",
        "acceptance_decision",
    }
    missing = [k for k in sorted(required) if k not in bundle]
    if missing:
        _fail("INVALID:BUNDLE_MISSING_FIELD")


def _hash_matches(path: Path, expected: str) -> None:
    got = file_hash(path)
    if got != expected:
        _fail("INVALID:SCHEMA_FAIL")


def _canon_hash_matches(path: Path, expected: str) -> None:
    obj = _load_json(path)
    got = sha256_prefixed(canon_bytes(obj))
    if got != expected:
        _fail("INVALID:SCHEMA_FAIL")


def _assert_no_holdout_leak(rows: list[dict[str, Any]]) -> None:
    seen_heldout = False
    for row in rows:
        kind = row.get("eval_kind")
        if kind == "HELDOUT":
            seen_heldout = True
        elif seen_heldout:
            _fail("INVALID:TRACE_LEAK")


def _rust_binary_path(crate_dir: Path) -> Path:
    return crate_dir / "target" / "release" / "sas_metasearch_rs_v1"


def _should_rebuild_rust_binary(
    *,
    crate_dir: Path,
    expected_crate_hash: str,
    expected_bin_hash: str,
) -> bool:
    if crate_tree_hash(crate_dir) != expected_crate_hash:
        _fail("INVALID:BIN_HASH_MISMATCH")

    existing_binary = _rust_binary_path(crate_dir)
    if not existing_binary.exists() or not existing_binary.is_file():
        return True
    if file_hash(existing_binary) != expected_bin_hash:
        _fail("INVALID:BIN_HASH_MISMATCH")
    return False


def _resolve_rust_binary_for_planner(
    *,
    crate_dir: Path,
    rust_toolchain: dict[str, Any],
    expected_crate_hash: str,
    expected_bin_hash: str,
) -> tuple[Path, dict[str, Any] | None]:
    if not _should_rebuild_rust_binary(
        crate_dir=crate_dir,
        expected_crate_hash=expected_crate_hash,
        expected_bin_hash=expected_bin_hash,
    ):
        return _rust_binary_path(crate_dir), None

    rebuilt_binary, rebuilt_receipt = build_release_binary_with_receipt(
        crate_dir=crate_dir,
        rust_toolchain=rust_toolchain,
    )
    if str(rebuilt_receipt.get("crate_tree_hash")) != expected_crate_hash:
        _fail("INVALID:BIN_HASH_MISMATCH")
    if file_hash(rebuilt_binary) != expected_bin_hash:
        _fail("INVALID:BIN_HASH_MISMATCH")
    return rebuilt_binary, rebuilt_receipt


def _path_from_row_hashes(*, state_dir: Path, row: dict[str, Any]) -> dict[str, Path | None]:
    lease_rel = (row.get("input_rels") or {}).get("lease_rel")
    lease = None
    if isinstance(lease_rel, str) and lease_rel:
        lease = (state_dir / lease_rel).resolve()
        if not lease.exists():
            _fail("INVALID:MISSING_STATE_INPUT")

    dataset_manifest = _collect_by_hash(
        state_dir / "search_workspace" / "data" / "manifest",
        "sas_science_dataset_manifest_v1.json",
        str(row.get("dataset_manifest_hash")),
    )
    dataset_csv = _collect_by_hash(
        state_dir / "search_workspace" / "data" / "csv",
        "dataset.csv",
        str(row.get("dataset_csv_hash")),
    )
    dataset_receipt = _collect_by_hash(
        state_dir / "search_workspace" / "data" / "receipts",
        "sas_science_dataset_receipt_v1.json",
        str(row.get("dataset_receipt_hash")),
    )
    split_receipt = _collect_by_hash(
        state_dir / "search_workspace" / "data" / "receipts",
        "sas_science_split_receipt_v1.json",
        str(row.get("split_receipt_hash")),
    )
    theory_ir = _collect_by_hash(
        state_dir / "search_workspace" / "theory" / "ir",
        "sas_science_theory_ir_v1.json",
        str(row.get("theory_ir_hash")),
    )
    fit_receipt = _collect_by_hash(
        state_dir / "search_workspace" / "fit" / "receipts",
        "sas_science_fit_receipt_v1.json",
        str(row.get("fit_receipt_hash")),
    )

    if row.get("eval_kind") == "DEV":
        suitepack = state_dir / "search_workspace" / "config" / "sas_science_suitepack_dev_v1.json"
    else:
        suitepack = state_dir / "search_workspace" / "config" / "sas_science_suitepack_heldout_v1.json"
    if not suitepack.exists():
        _fail("INVALID:MISSING_STATE_INPUT")
    if file_hash(suitepack) != row.get("suitepack_hash"):
        _fail("INVALID:SCHEMA_FAIL")

    ir_policy = state_dir / "search_workspace" / "config" / "sas_science_ir_policy_v1.json"
    perf_policy = state_dir / "search_workspace" / "config" / "sas_science_perf_policy_v1.json"
    if not ir_policy.exists() or not perf_policy.exists():
        _fail("INVALID:MISSING_STATE_INPUT")
    if file_hash(ir_policy) != row.get("ir_policy_hash"):
        _fail("INVALID:SCHEMA_FAIL")
    if file_hash(perf_policy) != row.get("perf_policy_hash"):
        _fail("INVALID:SCHEMA_FAIL")

    return {
        "dataset_manifest": dataset_manifest,
        "dataset_csv": dataset_csv,
        "dataset_receipt": dataset_receipt,
        "split_receipt": split_receipt,
        "theory_ir": theory_ir,
        "fit_receipt": fit_receipt,
        "suitepack": suitepack,
        "perf_policy": perf_policy,
        "ir_policy": ir_policy,
        "lease": lease,
    }


def _replay_eval_trace(*, state_dir: Path, py_toolchain: dict[str, Any], rows: list[dict[str, Any]], schema_dir: Path) -> tuple[int, dict[str, dict[str, Any]]]:
    total = 0
    python_exe = str(py_toolchain["python_executable"])
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_repo_root()) + os.pathsep + str(_repo_root() / "CDEL-v2") + os.pathsep + str(_repo_root() / "Extension-1" / "agi-orchestrator")

    reports: dict[str, dict[str, Any]] = {}
    replay_rows: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []

    for row in rows:
        _validate_jsonschema(row, "metasearch_eval_trace_v2", schema_dir)
        paths = _path_from_row_hashes(state_dir=state_dir, row=row)
        replay_rows.append(row)
        jobs.append(
            {
                "schema_version": "sealed_science_eval_job_v1",
                "dataset_manifest": str(paths["dataset_manifest"]),
                "dataset_csv": str(paths["dataset_csv"]),
                "dataset_receipt": str(paths["dataset_receipt"]),
                "split_receipt": str(paths["split_receipt"]),
                "theory_ir": str(paths["theory_ir"]),
                "fit_receipt": str(paths["fit_receipt"]),
                "suitepack": str(paths["suitepack"]),
                "perf_policy": str(paths["perf_policy"]),
                "ir_policy": str(paths["ir_policy"]),
                "eval_kind": str(row.get("eval_kind")),
                "lease": None if paths["lease"] is None else str(paths["lease"]),
                "cache_keys": {
                    "dataset_manifest_hash": str(row.get("dataset_manifest_hash")),
                    "dataset_csv_hash": str(row.get("dataset_csv_hash")),
                    "dataset_receipt_hash": str(row.get("dataset_receipt_hash")),
                    "split_receipt_hash": str(row.get("split_receipt_hash")),
                    "suitepack_hash": str(row.get("suitepack_hash")),
                    "perf_policy_hash": str(row.get("perf_policy_hash")),
                    "ir_policy_hash": str(row.get("ir_policy_hash")),
                },
            }
        )

    if not replay_rows:
        return total, reports

    replay_results: list[dict[str, Any]] = []
    try:
        sealed_client = start_sealed_eval_client(python_exe, env)
    except SealedEvalClientError:
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    try:
        replay_results = sealed_client.run_jobs(jobs)
    except SealedEvalClientError:
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    finally:
        try:
            sealed_client.close()
        except SealedEvalClientError:
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    if len(replay_results) != len(replay_rows):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    for row, result in zip(replay_rows, replay_results):
        if not isinstance(result, dict):
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
        eval_report = result.get("eval_report")
        sealed_receipt = result.get("sealed_receipt")
        if not isinstance(eval_report, dict) or not isinstance(sealed_receipt, dict):
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

        report_hash = compute_report_hash(eval_report)
        if report_hash != result.get("eval_report_hash"):
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
        if report_hash != row.get("eval_report_hash"):
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

        sealed_receipt_hash = sha256_prefixed(canon_bytes(sealed_receipt))
        if sealed_receipt_hash != result.get("sealed_receipt_hash"):
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
        if sealed_receipt.get("eval_report_hash") != report_hash:
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

        try:
            work_from_report = int(eval_report.get("workmeter", {}).get("work_cost_total", -1))
            work_from_result = int(result.get("work_cost_total", -1))
            work_expected = int(row.get("work_cost_total", -1))
        except Exception:
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
        if work_from_report != work_from_result or work_from_report != work_expected:
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

        total += work_from_report
        reports[report_hash] = eval_report

    return total, reports


def _load_theory_meta(state_dir: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    ir_dir = state_dir / "search_workspace" / "theory" / "ir"
    for path in sorted(ir_dir.glob("sha256_*.sas_science_theory_ir_v1.json")):
        obj = _load_json(path)
        theory_id = str(obj.get("theory_id", ""))
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", theory_id):
            continue
        out[theory_id] = {
            "theory_ir_hash": sha256_prefixed(canon_bytes(obj)),
            "complexity": dict(obj.get("complexity") or {}),
        }
    return out


def _recompute_selection_hash(
    *,
    algo_label: str,
    policy_hash: str,
    trace_rows: list[dict[str, Any]],
    eval_reports_by_hash: dict[str, dict[str, Any]],
    theory_meta_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    dev_rows = [row for row in trace_rows if row.get("eval_kind") == "DEV"]
    receipt = build_selection_receipt(
        algo_label=algo_label,
        policy_hash=policy_hash,
        trace_rows_dev=dev_rows,
        eval_reports_by_hash=eval_reports_by_hash,
        theory_meta_by_id=theory_meta_by_id,
    )
    return receipt, sha256_prefixed(canon_bytes(receipt))


def _law_kind_from_science_run(run_root: Path) -> str:
    promo_dir = run_root / "state" / "promotion"
    promo_path = _collect_single(promo_dir, "sha256_*.sas_science_promotion_bundle_v1.json")
    promo = _load_json(promo_path)
    discovery = promo.get("discovery_bundle")
    if not isinstance(discovery, dict):
        _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
    law = discovery.get("law_kind")
    if not isinstance(law, str):
        _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
    return law


def _determinism_replay(*, config_dir: Path) -> None:
    tmp_base = _repo_root() / "runs" / "_v16_1_verify_replay"
    run_a = tmp_base / "run_a"
    run_b = tmp_base / "run_b"
    if tmp_base.exists():
        shutil.rmtree(tmp_base)
    tmp_base.mkdir(parents=True, exist_ok=True)

    pack_path = config_dir / "rsi_sas_metasearch_pack_v16_1.json"
    run_sas_metasearch(campaign_pack=pack_path, out_dir=run_a, min_corpus_cases=1)
    run_sas_metasearch(campaign_pack=pack_path, out_dir=run_b, min_corpus_cases=1)

    def _extract(run_root: Path, kind: str) -> str:
        out_state = run_root / "daemon" / "rsi_sas_metasearch_v16_1" / "state"
        if kind == "promotion":
            path = _collect_single(out_state / "promotion", "sha256_*.sas_metasearch_promotion_bundle_v2.json")
        elif kind == "plan":
            path = _collect_single(out_state / "plan", "sha256_*.metasearch_plan_v1.json")
        elif kind == "compute":
            path = _collect_single(out_state / "reports", "sha256_*.metasearch_compute_report_v1.json")
        else:
            _fail("INVALID:NONDETERMINISTIC")
            return ""
        return "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]

    a = {k: _extract(run_a, k) for k in ["promotion", "plan", "compute"]}
    b = {k: _extract(run_b, k) for k in ["promotion", "plan", "compute"]}
    if a != b:
        _fail("INVALID:NONDETERMINISTIC")


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        _fail("INVALID:MODE_UNSUPPORTED")

    state_dir, daemon_root = _resolve_run_state(state_dir)
    config_dir = daemon_root / "config"
    schema_dir = _schema_dir()

    pack = _load_json(config_dir / "rsi_sas_metasearch_pack_v16_1.json")
    policy = _load_json(config_dir / "sas_metasearch_policy_v1.json")
    baseline_cfg = _load_json(config_dir / "baseline_search_config_v1.json")
    candidate_cfg = _load_json(config_dir / "candidate_search_config_v1.json")

    _validate_jsonschema(pack, "rsi_sas_metasearch_pack_v16_1", schema_dir)
    _validate_jsonschema(policy, "sas_metasearch_policy_v1", schema_dir)

    promo_path = _collect_single(state_dir / "promotion", "sha256_*.sas_metasearch_promotion_bundle_v2.json")
    promotion = _load_json(promo_path)
    _require_bundle_fields(promotion)
    _validate_jsonschema(promotion, "sas_metasearch_promotion_bundle_v2", schema_dir)

    # Ensure promotion field hashes resolve to concrete state/config artifacts.
    _canon_hash_matches(config_dir / "rsi_sas_metasearch_pack_v16_1.json", str(promotion["pack_hash"]))
    _canon_hash_matches(config_dir / "sas_metasearch_policy_v1.json", str(promotion["policy_hash"]))
    _canon_hash_matches(config_dir / "baseline_search_config_v1.json", str(promotion["baseline_search_config_hash"]))
    _canon_hash_matches(config_dir / "candidate_search_config_v1.json", str(promotion["candidate_search_config_hash"]))
    _hash_matches(config_dir / "toolchain_manifest_py_v1.json", str(promotion["toolchain_manifest_py_hash"]))
    _hash_matches(config_dir / "toolchain_manifest_rust_v1.json", str(promotion["toolchain_manifest_rust_hash"]))
    _collect_by_hash(
        state_dir / "search_workspace" / "data" / "manifest",
        "sas_science_dataset_manifest_v1.json",
        str(promotion["dataset_manifest_hash"]),
    )
    _collect_by_hash(
        state_dir / "search_workspace" / "data" / "csv",
        "dataset.csv",
        str(promotion["dataset_csv_hash"]),
    )
    _collect_by_hash(
        state_dir / "search_workspace" / "data" / "receipts",
        "sas_science_dataset_receipt_v1.json",
        str(promotion["dataset_receipt_hash"]),
    )
    _collect_by_hash(
        state_dir / "search_workspace" / "data" / "receipts",
        "sas_science_split_receipt_v1.json",
        str(promotion["split_receipt_hash"]),
    )

    corpus_path = _collect_by_hash(
        state_dir / "trace_corpus",
        "metasearch_trace_corpus_suitepack_v1.json",
        str(promotion["trace_corpus_hash"]),
    )
    corpus = load_suitepack(corpus_path, min_cases=1)
    _validate_jsonschema(corpus, "metasearch_trace_corpus_suitepack_v1", schema_dir)
    if b"HELDOUT" in canon_bytes(corpus):
        _fail("INVALID:TRACE_LEAK")

    prior_path = _collect_by_hash(state_dir / "prior", "metasearch_prior_v1.json", str(promotion["prior_hash"]))
    plan_path = _collect_by_hash(state_dir / "plan", "metasearch_plan_v1.json", str(promotion["plan_hash"]))
    build_receipt_path = _collect_by_hash(
        state_dir / "build",
        "metasearch_build_receipt_v1.json",
        str(promotion["rust_build_receipt_hash"]),
    )
    baseline_sel_path = _collect_by_hash(
        state_dir / "selection",
        "metasearch_selection_receipt_v1.json",
        str(promotion["baseline_selection_receipt_hash"]),
    )
    candidate_sel_path = _collect_by_hash(
        state_dir / "selection",
        "metasearch_selection_receipt_v1.json",
        str(promotion["candidate_selection_receipt_hash"]),
    )
    compute_path = _collect_by_hash(
        state_dir / "reports",
        "metasearch_compute_report_v1.json",
        str(promotion["compute_report_hash"]),
    )

    _validate_jsonschema(_load_json(prior_path), "metasearch_prior_v1", schema_dir)
    _validate_jsonschema(_load_json(plan_path), "metasearch_plan_v1", schema_dir)

    build_receipt = _load_json(build_receipt_path)
    _validate_jsonschema(build_receipt, "metasearch_build_receipt_v1", schema_dir)
    if sha256_prefixed(canon_bytes(build_receipt)) != str(promotion["rust_build_receipt_hash"]):
        _fail("INVALID:BIN_HASH_MISMATCH")
    expected_crate_hash = str(promotion.get("rust_crate_tree_hash"))
    expected_bin_hash = str(promotion.get("rust_binary_hash"))
    if str(build_receipt.get("crate_tree_hash")) != expected_crate_hash:
        _fail("INVALID:BIN_HASH_MISMATCH")
    if str(build_receipt.get("binary_sha256")) != expected_bin_hash:
        _fail("INVALID:BIN_HASH_MISMATCH")

    rust_tool = load_rust_toolchain_manifest(config_dir / "toolchain_manifest_rust_v1.json")
    py_tool = load_py_toolchain_manifest(config_dir / "toolchain_manifest_py_v1.json")

    crate = _repo_root() / "CDEL-v2" / "cdel" / "v16_1" / "rust" / "sas_metasearch_rs_v1"
    scan_rust_sources(crate / "src", forbidden_tokens=list(policy.get("forbidden_rust_tokens") or []))
    rebuilt_binary, _rebuilt_receipt = _resolve_rust_binary_for_planner(
        crate_dir=crate,
        rust_toolchain=rust_tool,
        expected_crate_hash=expected_crate_hash,
        expected_bin_hash=expected_bin_hash,
    )

    # Planner replay hash check.
    plan_expected = _load_json(plan_path)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_plan = Path(tmp) / "plan.json"
        replay_plan = run_planner(binary_path=rebuilt_binary, prior_path=prior_path, out_plan_path=tmp_plan)
    if sha256_prefixed(canon_bytes(replay_plan)) != str(promotion["plan_hash"]):
        _fail("INVALID:SEARCH_PLAN_REPLAY_MISMATCH")
    if sha256_prefixed(canon_bytes(plan_expected)) != str(promotion["plan_hash"]):
        _fail("INVALID:SEARCH_PLAN_REPLAY_MISMATCH")

    baseline_trace = state_dir / "eval_trace" / "baseline.metasearch_eval_trace_v2.jsonl"
    candidate_trace = state_dir / "eval_trace" / "candidate.metasearch_eval_trace_v2.jsonl"
    if not baseline_trace.exists() or not candidate_trace.exists():
        _fail("INVALID:MISSING_STATE_INPUT")
    if file_hash(baseline_trace) != promotion.get("baseline_eval_trace_hash"):
        _fail("INVALID:TRACE_CHAIN_MISMATCH")
    if file_hash(candidate_trace) != promotion.get("candidate_eval_trace_hash"):
        _fail("INVALID:TRACE_CHAIN_MISMATCH")

    baseline_rows = load_trace_rows(baseline_trace)
    candidate_rows = load_trace_rows(candidate_trace)

    try:
        validate_hash_chain(baseline_rows)
        validate_hash_chain(candidate_rows)
    except ValueError:
        _fail("INVALID:TRACE_CHAIN_MISMATCH")

    _assert_no_holdout_leak(baseline_rows)
    _assert_no_holdout_leak(candidate_rows)

    c_base, base_reports = _replay_eval_trace(state_dir=state_dir, py_toolchain=py_tool, rows=baseline_rows, schema_dir=schema_dir)
    c_cand, cand_reports = _replay_eval_trace(state_dir=state_dir, py_toolchain=py_tool, rows=candidate_rows, schema_dir=schema_dir)
    baseline_dev_eval_count = sum(1 for row in baseline_rows if str(row.get("eval_kind")) == "DEV")
    candidate_dev_eval_count = sum(1 for row in candidate_rows if str(row.get("eval_kind")) == "DEV")
    all_reports = dict(base_reports)
    all_reports.update(cand_reports)

    compute = _load_json(compute_path)
    _validate_jsonschema(compute, "metasearch_compute_report_v1", schema_dir)
    if sha256_prefixed(canon_bytes(compute)) != str(promotion["compute_report_hash"]):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    if int(compute.get("c_base_work_cost_total", -1)) != int(c_base):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    if int(compute.get("c_cand_work_cost_total", -1)) != int(c_cand):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    if int(compute.get("baseline_dev_eval_count_u64", -1)) != int(baseline_dev_eval_count):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    if int(compute.get("candidate_dev_eval_count_u64", -1)) != int(candidate_dev_eval_count):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    if str(compute.get("baseline_eval_trace_hash")) != str(promotion.get("baseline_eval_trace_hash")):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    if str(compute.get("candidate_eval_trace_hash")) != str(promotion.get("candidate_eval_trace_hash")):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    theory_meta = _load_theory_meta(state_dir)

    baseline_sel = _load_json(baseline_sel_path)
    candidate_sel = _load_json(candidate_sel_path)
    _validate_jsonschema(baseline_sel, "metasearch_selection_receipt_v1", schema_dir)
    _validate_jsonschema(candidate_sel, "metasearch_selection_receipt_v1", schema_dir)
    if sha256_prefixed(canon_bytes(baseline_sel)) != str(promotion["baseline_selection_receipt_hash"]):
        _fail("INVALID:SELECTION_MISMATCH")
    if sha256_prefixed(canon_bytes(candidate_sel)) != str(promotion["candidate_selection_receipt_hash"]):
        _fail("INVALID:SELECTION_MISMATCH")

    baseline_recomputed, baseline_hash = _recompute_selection_hash(
        algo_label="baseline",
        policy_hash=str(promotion["policy_hash"]),
        trace_rows=baseline_rows,
        eval_reports_by_hash=all_reports,
        theory_meta_by_id=theory_meta,
    )
    candidate_recomputed, candidate_hash = _recompute_selection_hash(
        algo_label="candidate",
        policy_hash=str(promotion["policy_hash"]),
        trace_rows=candidate_rows,
        eval_reports_by_hash=all_reports,
        theory_meta_by_id=theory_meta,
    )

    if baseline_hash != str(promotion["baseline_selection_receipt_hash"]):
        _fail("INVALID:SELECTION_MISMATCH")
    if candidate_hash != str(promotion["candidate_selection_receipt_hash"]):
        _fail("INVALID:SELECTION_MISMATCH")
    if sha256_prefixed(canon_bytes(baseline_sel)) != baseline_hash:
        _fail("INVALID:SELECTION_MISMATCH")
    if sha256_prefixed(canon_bytes(candidate_sel)) != candidate_hash:
        _fail("INVALID:SELECTION_MISMATCH")
    if baseline_sel != baseline_recomputed or candidate_sel != candidate_recomputed:
        _fail("INVALID:SELECTION_MISMATCH")

    if c_cand * 2 > c_base:
        _fail("INVALID:COGNITIVE_EFFICIENCY_GATE_FAIL")

    baseline_science = state_dir / "science_runs" / "baseline_science"
    candidate_science = state_dir / "science_runs" / "candidate_science"
    try:
        verify_v13(baseline_science, mode="full")
        verify_v13(candidate_science, mode="full")
    except SASScienceError:
        _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")

    foil_run = state_dir / "science_runs" / "candidate_foil_hooke"
    foil_law = _law_kind_from_science_run(foil_run)
    if foil_law in ("NEWTON_CENTRAL_V1", "NEWTON_NBODY_V1"):
        _fail("INVALID:NEWTON_ALWAYS_OUTPUT")

    if os.environ.get("V16_1_SKIP_DETERMINISM", "0") != "1":
        _determinism_replay(config_dir=config_dir)

    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_sas_metasearch_v16_1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        result = verify(Path(args.state_dir), mode=args.mode)
        print(result)
    except (MetaSearchVerifyError, MetaSearchRustBuildError, MetaSearchCorpusError) as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
