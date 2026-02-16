"""Fail-closed verifier for RSI SAS-Metasearch v16.0."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import warnings
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from ..v13_0.sas_science_eval_v1 import compute_report_hash
from ..v13_0.verify_rsi_sas_science_v1 import SASScienceError, verify as verify_v13
from .metasearch_build_rust_v1 import (
    MetaSearchRustBuildError,
    build_release_binary,
    file_hash,
    load_py_toolchain_manifest,
    load_rust_toolchain_manifest,
    run_planner,
    scan_rust_sources,
)
from .metasearch_corpus_v1 import MetaSearchCorpusError, load_suitepack
from .metasearch_run_v1 import run_sas_metasearch

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


def _fail(reason: str) -> None:
    raise MetaSearchVerifyError(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema_dir() -> Path:
    return _repo_root() / "Genesis" / "schema" / "v16_0"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        obj = load_canon_json(path)
    except CanonError:
        _fail("INVALID:SCHEMA_FAIL")
    if not isinstance(obj, dict):
        _fail("INVALID:SCHEMA_FAIL")
    return obj


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        _fail("INVALID:SCHEMA_FAIL")
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            _fail("INVALID:SCHEMA_FAIL")
        if not isinstance(obj, dict):
            _fail("INVALID:SCHEMA_FAIL")
        rows.append(obj)
    return rows


def _assert_no_holdout_leak(rows: list[dict[str, Any]]) -> None:
    seen_heldout = False
    for row in rows:
        kind = row.get("eval_kind")
        if kind == "HELDOUT":
            seen_heldout = True
        elif seen_heldout:
            _fail("INVALID:TRACE_LEAK")


def _validate_jsonschema(obj: dict[str, Any], schema_name: str, schema_dir: Path) -> None:
    if Draft202012Validator is None:
        return
    schema_path = schema_dir / f"{schema_name}.jsonschema"
    if not schema_path.exists():
        _fail("INVALID:SCHEMA_FAIL")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema = dict(schema)
    schema["$id"] = schema_path.resolve().as_uri()
    store: dict[str, Any] = {}
    for path in schema_dir.glob("*.jsonschema"):
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
    if RefResolver is not None:
        resolver = RefResolver.from_schema(schema, store=store)
        Draft202012Validator(schema, resolver=resolver).validate(obj)
    else:
        Draft202012Validator(schema).validate(obj)


def _resolve_run_state(path: Path) -> tuple[Path, Path]:
    root = path.resolve()
    # run root -> daemon/<tag>/state
    candidate = root / "daemon" / "rsi_sas_metasearch_v16_0" / "state"
    if candidate.exists():
        return candidate, candidate.parent
    # daemon root
    candidate = root / "state"
    if candidate.exists() and (root / "config").exists():
        return candidate, root
    # state dir directly
    if (root / "control").exists() and (root.parent / "config").exists():
        return root, root.parent
    _fail("INVALID:SCHEMA_FAIL")
    return root, root


def _scan_trace_corpus(corpus_path: Path) -> dict[str, Any]:
    corpus = load_suitepack(corpus_path, min_cases=1)
    raw = canon_bytes(corpus)
    if b"HELDOUT" in raw:
        _fail("INVALID:TRACE_LEAK")
    return corpus


def _extract_binary_hash_from_ledger(ledger_path: Path) -> str:
    if not ledger_path.exists():
        _fail("INVALID:SCHEMA_FAIL")
    target = None
    for raw in ledger_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        row = json.loads(raw)
        if row.get("event_type") == "METASEARCH_PLAN_READY":
            payload = row.get("payload")
            if isinstance(payload, dict):
                target = payload.get("binary_hash")
    if not isinstance(target, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", target):
        _fail("INVALID:BINARY_HASH_MISMATCH")
    return target


def _collect_single(path: Path, pattern: str) -> Path:
    rows = sorted(path.glob(pattern))
    if len(rows) != 1:
        _fail("INVALID:SCHEMA_FAIL")
    return rows[0]


def _replay_eval_trace(
    *,
    state_dir: Path,
    py_toolchain: dict[str, Any],
    rows: list[dict[str, Any]],
) -> int:
    total = 0
    python_exe = str(py_toolchain["python_executable"])
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_repo_root() / "CDEL-v2") + os.pathsep + str(_repo_root() / "Extension-1" / "agi-orchestrator")

    for row in rows:
        _validate_jsonschema(row, "metasearch_eval_trace_v1", _schema_dir())
        rels = row.get("input_rels")
        if not isinstance(rels, dict):
            _fail("INVALID:SCHEMA_FAIL")

        def _rp(key: str) -> Path | None:
            value = rels.get(key)
            if value is None:
                return None
            if not isinstance(value, str):
                _fail("INVALID:SCHEMA_FAIL")
            return (state_dir / value).resolve()

        dataset_manifest = _rp("dataset_manifest_rel")
        dataset_csv = _rp("dataset_csv_rel")
        dataset_receipt = _rp("dataset_receipt_rel")
        split_receipt = _rp("split_receipt_rel")
        theory_ir = _rp("theory_ir_rel")
        fit_receipt = _rp("fit_receipt_rel")
        suitepack = _rp("suitepack_rel")
        perf_policy = _rp("perf_policy_rel")
        ir_policy = _rp("ir_policy_rel")
        lease = _rp("lease_rel")

        if None in [dataset_manifest, dataset_csv, dataset_receipt, split_receipt, theory_ir, fit_receipt, suitepack, perf_policy, ir_policy]:
            _fail("INVALID:SCHEMA_FAIL")

        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            out_eval = tmpdir / "eval.json"
            out_sealed = tmpdir / "sealed.json"
            cmd = [
                python_exe,
                "-m",
                "cdel.v13_0.sealed_science_eval_v1",
                "--dataset_manifest",
                str(dataset_manifest),
                "--dataset_csv",
                str(dataset_csv),
                "--dataset_receipt",
                str(dataset_receipt),
                "--split_receipt",
                str(split_receipt),
                "--theory_ir",
                str(theory_ir),
                "--fit_receipt",
                str(fit_receipt),
                "--suitepack",
                str(suitepack),
                "--perf_policy",
                str(perf_policy),
                "--ir_policy",
                str(ir_policy),
                "--eval_kind",
                str(row.get("eval_kind")),
                "--out_eval",
                str(out_eval),
                "--out_sealed",
                str(out_sealed),
            ]
            if lease is not None:
                cmd.extend(["--lease", str(lease)])
            rc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
            if rc.returncode != 0:
                _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
            eval_report = load_canon_json(out_eval)
            if not isinstance(eval_report, dict):
                _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
            report_hash = compute_report_hash(eval_report)
            if report_hash != row.get("eval_report_hash"):
                _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
            work = int(eval_report.get("workmeter", {}).get("work_cost_total", 0))
            if work != int(row.get("work_cost_total", -1)):
                _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
            total += work
    return total


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


def _determinism_replay(*, config_dir: Path, state_dir: Path) -> None:
    tmp_base = _repo_root() / "runs" / "_v16_0_verify_replay"
    run_a = tmp_base / "run_a"
    run_b = tmp_base / "run_b"
    if tmp_base.exists():
        shutil.rmtree(tmp_base)
    tmp_base.mkdir(parents=True, exist_ok=True)

    pack_path = config_dir / "rsi_sas_metasearch_pack_v1.json"
    result_a = run_sas_metasearch(campaign_pack=pack_path, out_dir=run_a, min_corpus_cases=1)
    result_b = run_sas_metasearch(campaign_pack=pack_path, out_dir=run_b, min_corpus_cases=1)

    def _extract(hash_key: str, run_root: Path) -> str:
        out_state = run_root / "daemon" / "rsi_sas_metasearch_v16_0" / "state"
        if hash_key == "promotion":
            promo = _collect_single(out_state / "promotion", "sha256_*.sas_metasearch_promotion_bundle_v1.json")
            return "sha256:" + promo.name.split(".", 1)[0].split("_", 1)[1]
        if hash_key == "plan":
            plan = _collect_single(out_state / "plan", "sha256_*.metasearch_plan_v1.json")
            return "sha256:" + plan.name.split(".", 1)[0].split("_", 1)[1]
        if hash_key == "compute":
            comp = _collect_single(out_state / "reports", "sha256_*.metasearch_compute_report_v1.json")
            return "sha256:" + comp.name.split(".", 1)[0].split("_", 1)[1]
        _fail("INVALID:NONDETERMINISTIC")
        return ""

    a_vals = {
        "promotion": _extract("promotion", run_a),
        "plan": _extract("plan", run_a),
        "compute": _extract("compute", run_a),
    }
    b_vals = {
        "promotion": _extract("promotion", run_b),
        "plan": _extract("plan", run_b),
        "compute": _extract("compute", run_b),
    }

    if a_vals != b_vals:
        _fail("INVALID:NONDETERMINISTIC")


# tempfile needed in _replay_eval_trace
import tempfile  # noqa: E402
import subprocess  # noqa: E402


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        _fail("INVALID:MODE_UNSUPPORTED")

    state_dir, daemon_root = _resolve_run_state(state_dir)
    config_dir = daemon_root / "config"
    schema_dir = _schema_dir()

    # 1) schema validation of core configs.
    pack = _load_json(config_dir / "rsi_sas_metasearch_pack_v1.json")
    policy = _load_json(config_dir / "sas_metasearch_policy_v1.json")
    baseline_cfg = _load_json(config_dir / "baseline_search_config_v1.json")
    candidate_cfg = _load_json(config_dir / "candidate_search_config_v1.json")

    _validate_jsonschema(pack, "rsi_sas_metasearch_pack_v1", schema_dir)
    _validate_jsonschema(policy, "sas_metasearch_policy_v1", schema_dir)

    # 2) trace corpus: dev only and no HELDOUT token.
    corpus_path = _collect_single(state_dir / "trace_corpus", "sha256_*.metasearch_trace_corpus_suitepack_v1.json")
    corpus = _scan_trace_corpus(corpus_path)
    _validate_jsonschema(corpus, "metasearch_trace_corpus_suitepack_v1", schema_dir)

    # 3) rebuild rust and binary hash match.
    rust_tool = load_rust_toolchain_manifest(config_dir / "toolchain_manifest_rust_v1.json")
    py_tool = load_py_toolchain_manifest(config_dir / "toolchain_manifest_py_v1.json")

    crate = _repo_root() / "CDEL-v2" / "cdel" / "v16_0" / "rust" / "sas_metasearch_rs_v1"
    try:
        scan_rust_sources(crate / "src", forbidden_tokens=list(policy.get("forbidden_rust_tokens") or []))
        binary = build_release_binary(crate_dir=crate, rust_toolchain=rust_tool)
        rebuilt_hash = file_hash(binary)
    except MetaSearchRustBuildError as exc:
        _fail(str(exc))
    expected_binary_hash = _extract_binary_hash_from_ledger(state_dir / "ledger" / "metasearch_ledger_v1.jsonl")
    if rebuilt_hash != expected_binary_hash:
        _fail("INVALID:BINARY_HASH_MISMATCH")

    # 4) rerun planner and hash compare.
    prior_path = _collect_single(state_dir / "prior", "sha256_*.metasearch_prior_v1.json")
    plan_path = _collect_single(state_dir / "plan", "sha256_*.metasearch_plan_v1.json")
    plan_expected = _load_json(plan_path)
    _validate_jsonschema(plan_expected, "metasearch_plan_v1", schema_dir)
    expected_plan_hash = sha256_prefixed(canon_bytes(plan_expected))

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_plan = Path(tmp) / "plan.json"
            replay_plan = run_planner(binary_path=binary, prior_path=prior_path, out_plan_path=tmp_plan)
    except MetaSearchRustBuildError as exc:
        _fail(str(exc))
    _validate_jsonschema(replay_plan, "metasearch_plan_v1", schema_dir)
    replay_plan_hash = sha256_prefixed(canon_bytes(replay_plan))
    if replay_plan_hash != expected_plan_hash:
        _fail("INVALID:SEARCH_PLAN_REPLAY_MISMATCH")

    # 5) replay compute via eval traces.
    baseline_trace = state_dir / "eval_trace" / "baseline.metasearch_eval_trace_v1.jsonl"
    candidate_trace = state_dir / "eval_trace" / "candidate.metasearch_eval_trace_v1.jsonl"
    baseline_rows = _load_jsonl(baseline_trace)
    candidate_rows = _load_jsonl(candidate_trace)
    _assert_no_holdout_leak(baseline_rows)
    _assert_no_holdout_leak(candidate_rows)

    c_base = _replay_eval_trace(state_dir=state_dir, py_toolchain=py_tool, rows=baseline_rows)
    c_cand = _replay_eval_trace(state_dir=state_dir, py_toolchain=py_tool, rows=candidate_rows)

    compute_path = _collect_single(state_dir / "reports", "sha256_*.metasearch_compute_report_v1.json")
    compute = _load_json(compute_path)
    _validate_jsonschema(compute, "metasearch_compute_report_v1", schema_dir)

    if int(compute.get("c_base_work_cost_total", -1)) != int(c_base):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    if int(compute.get("c_cand_work_cost_total", -1)) != int(c_cand):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    # 6) efficiency gate.
    if c_cand * 2 > c_base:
        _fail("INVALID:COGNITIVE_EFFICIENCY_GATE_FAIL")

    # 7) v13 downstream verifier checks.
    baseline_science = state_dir / "science_runs" / "baseline_science"
    candidate_science = state_dir / "science_runs" / "candidate_science"
    try:
        verify_v13(baseline_science, mode="full")
        verify_v13(candidate_science, mode="full")
    except SASScienceError:
        _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")

    # 8) foil anti-cheat gate.
    foil_run = state_dir / "science_runs" / "candidate_foil_hooke"
    foil_law = _law_kind_from_science_run(foil_run)
    if foil_law in ("NEWTON_CENTRAL_V1", "NEWTON_NBODY_V1"):
        _fail("INVALID:NEWTON_ALWAYS_OUTPUT")

    # 9) determinism check (two fresh runs, same inputs).
    _determinism_replay(config_dir=config_dir, state_dir=state_dir)

    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_sas_metasearch_v1")
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
