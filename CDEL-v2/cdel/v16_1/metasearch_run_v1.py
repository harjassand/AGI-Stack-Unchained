"""Runtime coordinator for SAS-Metasearch v16.1."""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line
from ..v13_0.sas_science_dataset_v1 import load_dataset
from ..v13_0.sas_science_canon_v1 import canonicalize_law
from ..v13_0.sas_science_eval_v1 import compute_report_hash
from ..v13_0.sealed_science_eval_client_v1 import SealedEvalClient, SealedEvalClientError, start as start_sealed_eval_client
from ..v13_0.sas_science_fit_v1 import fit_theory
from ..v13_0.sas_science_ir_v1 import compute_complexity, compute_theory_id, validate_ir
from ..v13_0.sas_science_math_v1 import parse_q32_obj
from .metasearch_build_rust_v1 import (
    build_release_binary_with_receipt,
    load_py_toolchain_manifest,
    load_rust_toolchain_manifest,
    run_planner,
    scan_rust_sources,
    write_hashed_build_receipt,
)
from .metasearch_codegen_rust_v1 import materialize_rust_crate
from .metasearch_corpus_v1 import load_suitepack
from .metasearch_policy_ir_v1 import (
    CandidateSearchConfig,
    Hypothesis,
    enumerate_hypotheses,
    load_baseline_search_config,
    load_candidate_search_config,
    load_policy,
)
from .metasearch_prior_v1 import build_prior_from_corpus
from .metasearch_promotion_bundle_v2 import build_promotion_bundle, write_hashed_bundle
from .metasearch_selection_v1 import build_selection_receipt, write_hashed_selection_receipt
from .metasearch_state_snapshot_v1 import hash_file, hash_json_obj, ingest_dataset_snapshot
from .metasearch_trace_v2 import append_trace_row, trace_file_hash


class MetaSearchRunError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise MetaSearchRunError(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _cdel_root() -> Path:
    return _repo_root() / "CDEL-v2"


def _orch_root() -> Path:
    # v16.1 keeps compatibility with existing command env.
    return _repo_root() / "Extension-1" / "agi-orchestrator"


def _now_utc() -> str:
    return "1970-01-01T00:00:00Z"


def _resolve_path(base: Path, rel_or_abs: str) -> Path:
    p = Path(str(rel_or_abs))
    if p.is_absolute():
        return p
    return base / p


def _write_hashed_json(out_dir: Path, suffix: str, payload: dict[str, Any]) -> tuple[Path, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    h = sha256_prefixed(canon_bytes(payload))
    path = out_dir / f"sha256_{h.split(':', 1)[1]}.{suffix}"
    write_canon_json(path, payload)
    return path, h


def _copy_json(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(dst, load_canon_json(src))


def _copy_csv(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def _pythonpath_env(existing_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(existing_env or os.environ)
    parts: list[str] = [str(_repo_root()), str(_cdel_root()), str(_orch_root())]
    old = env.get("PYTHONPATH", "")
    if old:
        parts.append(old)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _append_ledger(ledger_path: Path, event_type: str, payload: dict[str, Any], tick: int) -> None:
    row = {
        "schema_version": "metasearch_ledger_event_v1",
        "tick_u64": int(tick),
        "event_type": str(event_type),
        "payload": payload,
    }
    write_jsonl_line(ledger_path, row)


def _instantiate_baseline(template: dict[str, Any], manifest: dict[str, Any], *, central: bool) -> dict[str, Any]:
    ir = dict(template)
    targets = list(manifest.get("bodies") or [])
    ir["target_bodies"] = targets
    if central:
        frame = manifest.get("frame_kind")
        ir["source_bodies"] = ["Origin"] if frame == "HELIOCENTRIC_SUN_AT_ORIGIN_V1" else ["Sun"]
    else:
        sources = list(targets)
        frame = manifest.get("frame_kind")
        if frame == "BARYCENTRIC_WITH_SUN_ROW_V1" and "Sun" not in sources:
            sources.append("Sun")
        ir["source_bodies"] = sources
    ir["complexity"] = compute_complexity(ir)
    ir["theory_id"] = compute_theory_id(ir)
    return ir


def _build_candidate_ir(manifest: dict[str, Any], hypothesis: Hypothesis) -> dict[str, Any]:
    kind = hypothesis.theory_kind
    p = hypothesis.norm_pow_p
    targets = list(manifest.get("bodies") or [])
    frame = manifest.get("frame_kind")
    if kind == "CANDIDATE_CENTRAL_POWERLAW_V1":
        sources = ["Origin"] if frame == "HELIOCENTRIC_SUN_AT_ORIGIN_V1" else ["Sun"]
    else:
        sources = list(targets)
        if frame == "BARYCENTRIC_WITH_SUN_ROW_V1" and "Sun" not in sources:
            sources.append("Sun")

    ir = {
        "ir_version": "sas_science_theory_ir_v1",
        "theory_kind": kind,
        "target_bodies": targets,
        "source_bodies": sources,
        "force_law": {
            "vector_form": "DISPLACEMENT_OVER_NORM_POW_V1",
            "norm_pow_p": int(p),
            "coeff_sharing": "SOURCE_MASS_ONLY_V1",
        },
        "parameters": {},
        "complexity": {"node_count": 0, "term_count": 0, "param_count": 0},
        "theory_id": "",
    }
    ir["complexity"] = compute_complexity(ir)
    ir["theory_id"] = compute_theory_id(ir)
    return ir


def _prepare_eval_workspace(
    *,
    state_dir: Path,
    dataset_manifest_path: Path,
    dataset_csv_path: Path,
) -> dict[str, Any]:
    snapshot = ingest_dataset_snapshot(
        state_dir=state_dir,
        dataset_manifest_src=dataset_manifest_path,
        dataset_csv_src=dataset_csv_path,
    )

    workspace = Path(snapshot["workspace"])
    ir_dir = workspace / "theory" / "ir"
    fit_dir = workspace / "fit" / "receipts"
    eval_reports_dir = workspace / "eval" / "reports"
    eval_sealed_dir = workspace / "eval" / "sealed"
    ws_config = workspace / "config"

    for path in [ir_dir, fit_dir, eval_reports_dir, eval_sealed_dir, ws_config]:
        path.mkdir(parents=True, exist_ok=True)

    source_cfg = _repo_root() / "campaigns" / "rsi_sas_science_v13_0"
    _copy_json(source_cfg / "sas_science_ir_policy_v1.json", ws_config / "sas_science_ir_policy_v1.json")
    _copy_json(source_cfg / "sas_science_perf_policy_v1.json", ws_config / "sas_science_perf_policy_v1.json")
    _copy_json(source_cfg / "sas_science_suitepack_dev_v1.json", ws_config / "sas_science_suitepack_dev_v1.json")
    _copy_json(source_cfg / "sas_science_suitepack_heldout_v1.json", ws_config / "sas_science_suitepack_heldout_v1.json")

    manifest = dict(snapshot["manifest"])
    dataset_obj = load_dataset(Path(snapshot["csv_path"]), manifest)
    split_receipt = dict(snapshot["split_receipt"])
    ir_policy = load_canon_json(ws_config / "sas_science_ir_policy_v1.json")

    baseline_const_template = load_canon_json(source_cfg / "baselines" / "baseline_constant_velocity_v1.sas_science_theory_ir_v1.json")
    baseline_hooke_template = load_canon_json(source_cfg / "baselines" / "baseline_hooke_central_v1.sas_science_theory_ir_v1.json")

    baseline_const = _instantiate_baseline(baseline_const_template, manifest, central=True)
    baseline_hooke = _instantiate_baseline(baseline_hooke_template, manifest, central=True)
    validate_ir(baseline_const, manifest=manifest, ir_policy=ir_policy)
    validate_ir(baseline_hooke, manifest=manifest, ir_policy=ir_policy)

    theories: dict[str, dict[str, Any]] = {}
    hypos = enumerate_hypotheses()
    for hypothesis in hypos:
        ir = _build_candidate_ir(manifest, hypothesis)
        validate_ir(ir, manifest=manifest, ir_policy=ir_policy)
        theories[ir["theory_id"]] = {
            "ir": ir,
            "theory_kind": ir["theory_kind"],
            "norm_pow_p": int(ir["force_law"]["norm_pow_p"]),
            "hypothesis": hypothesis,
        }

    for ir in [baseline_const, baseline_hooke]:
        theories[ir["theory_id"]] = {
            "ir": ir,
            "theory_kind": ir["theory_kind"],
            "norm_pow_p": int(ir["force_law"]["norm_pow_p"]),
            "hypothesis": None,
        }

    theory_meta_by_id: dict[str, dict[str, Any]] = {}
    for theory_id, row in theories.items():
        ir = row["ir"]
        ir_hash = sha256_prefixed(canon_bytes(ir))
        ir_out = ir_dir / f"sha256_{ir_hash.split(':', 1)[1]}.sas_science_theory_ir_v1.json"
        write_canon_json(ir_out, ir)

        fit = fit_theory(dataset=dataset_obj, ir=ir, split_receipt=split_receipt, ir_policy=ir_policy)
        fit_hash = sha256_prefixed(canon_bytes(fit))
        fit_out = fit_dir / f"sha256_{fit_hash.split(':', 1)[1]}.sas_science_fit_receipt_v1.json"
        write_canon_json(fit_out, fit)

        row["ir_path"] = ir_out
        row["fit_receipt"] = fit
        row["fit_path"] = fit_out
        row["theory_ir_hash"] = ir_hash
        row["fit_receipt_hash"] = fit_hash

        theory_meta_by_id[theory_id] = {
            "theory_ir_hash": ir_hash,
            "complexity": dict(ir.get("complexity") or {}),
        }

    hypothesis_to_theory_id: dict[tuple[str, int], str] = {}
    for theory_id, row in theories.items():
        h = row.get("hypothesis")
        if h is None:
            continue
        hypothesis_to_theory_id[(h.theory_kind, h.norm_pow_p)] = theory_id

    ir_policy_path = ws_config / "sas_science_ir_policy_v1.json"
    perf_policy_path = ws_config / "sas_science_perf_policy_v1.json"
    suite_dev_path = ws_config / "sas_science_suitepack_dev_v1.json"
    suite_heldout_path = ws_config / "sas_science_suitepack_heldout_v1.json"

    return {
        "workspace": workspace,
        "manifest": manifest,
        "manifest_path": Path(snapshot["manifest_path"]),
        "manifest_hash": str(snapshot["manifest_hash"]),
        "csv_path": Path(snapshot["csv_path"]),
        "csv_hash": str(snapshot["csv_hash"]),
        "dataset_receipt": dict(snapshot["dataset_receipt"]),
        "dataset_receipt_path": Path(snapshot["dataset_receipt_path"]),
        "dataset_receipt_hash": str(snapshot["dataset_receipt_hash"]),
        "split_receipt": split_receipt,
        "split_receipt_path": Path(snapshot["split_receipt_path"]),
        "split_receipt_hash": str(snapshot["split_receipt_hash"]),
        "ir_policy_path": ir_policy_path,
        "ir_policy_hash": hash_file(ir_policy_path),
        "perf_policy_path": perf_policy_path,
        "perf_policy_hash": hash_file(perf_policy_path),
        "suite_dev_path": suite_dev_path,
        "suite_dev_hash": hash_file(suite_dev_path),
        "suite_heldout_path": suite_heldout_path,
        "suite_heldout_hash": hash_file(suite_heldout_path),
        "theories": theories,
        "theory_meta_by_id": theory_meta_by_id,
        "hypothesis_to_theory_id": hypothesis_to_theory_id,
        "baseline_const_theory_id": baseline_const["theory_id"],
        "baseline_hooke_theory_id": baseline_hooke["theory_id"],
        "eval_reports_dir": eval_reports_dir,
        "eval_sealed_dir": eval_sealed_dir,
        "eval_reports_by_hash": {},
    }


def _run_sealed_eval(
    *,
    sealed_eval_client: SealedEvalClient,
    dataset_manifest: Path,
    dataset_csv: Path,
    dataset_receipt: Path,
    split_receipt: Path,
    theory_ir: Path,
    fit_receipt: Path,
    suitepack: Path,
    perf_policy: Path,
    ir_policy: Path,
    eval_kind: str,
    lease: Path | None,
    dataset_manifest_hash: str,
    dataset_csv_hash: str,
    dataset_receipt_hash: str,
    split_receipt_hash: str,
    suitepack_hash: str,
    perf_policy_hash: str,
    ir_policy_hash: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    job = {
        "schema_version": "sealed_science_eval_job_v1",
        "dataset_manifest": str(dataset_manifest),
        "dataset_csv": str(dataset_csv),
        "dataset_receipt": str(dataset_receipt),
        "split_receipt": str(split_receipt),
        "theory_ir": str(theory_ir),
        "fit_receipt": str(fit_receipt),
        "suitepack": str(suitepack),
        "perf_policy": str(perf_policy),
        "ir_policy": str(ir_policy),
        "eval_kind": str(eval_kind),
        "lease": None if lease is None else str(lease),
        "cache_keys": {
            "dataset_manifest_hash": str(dataset_manifest_hash),
            "dataset_csv_hash": str(dataset_csv_hash),
            "dataset_receipt_hash": str(dataset_receipt_hash),
            "split_receipt_hash": str(split_receipt_hash),
            "suitepack_hash": str(suitepack_hash),
            "perf_policy_hash": str(perf_policy_hash),
            "ir_policy_hash": str(ir_policy_hash),
        },
    }
    try:
        results = sealed_eval_client.run_jobs([job])
    except SealedEvalClientError:
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    if len(results) != 1:
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    result = results[0]
    if not isinstance(result, dict):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    eval_report = result.get("eval_report")
    sealed = result.get("sealed_receipt")
    if not isinstance(eval_report, dict) or not isinstance(sealed, dict):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    report_hash = compute_report_hash(eval_report)
    if report_hash != result.get("eval_report_hash"):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    sealed_hash = sha256_prefixed(canon_bytes(sealed))
    if sealed_hash != result.get("sealed_receipt_hash"):
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    if sealed.get("eval_report_hash") != report_hash:
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    try:
        work_report = int(eval_report.get("workmeter", {}).get("work_cost_total", -1))
        work_result = int(result.get("work_cost_total", -1))
    except Exception:
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    if work_report != work_result:
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    return eval_report, sealed


def _persist_eval_artifacts(
    *,
    eval_report: dict[str, Any],
    sealed_receipt: dict[str, Any],
    eval_reports_dir: Path,
    eval_sealed_dir: Path,
) -> tuple[Path, Path, str, int]:
    report_hash = compute_report_hash(eval_report)
    report_path = eval_reports_dir / f"sha256_{report_hash.split(':', 1)[1]}.sas_science_eval_report_v1.json"
    if not report_path.exists():
        write_canon_json(report_path, eval_report)

    sealed_hash = sha256_prefixed(canon_bytes(sealed_receipt))
    sealed_path = eval_sealed_dir / f"sha256_{sealed_hash.split(':', 1)[1]}.sealed_science_eval_receipt_v1.json"
    if not sealed_path.exists():
        write_canon_json(sealed_path, sealed_receipt)

    work_cost_total = int(eval_report.get("workmeter", {}).get("work_cost_total", 0))
    return report_path, sealed_path, report_hash, work_cost_total


def _is_better(*, rmse_q: int, work_cost: int, theory_id: str, best: tuple[int, int, str] | None) -> bool:
    key = (int(rmse_q), int(work_cost), str(theory_id))
    if best is None:
        return True
    return key < best


def _trace_row_v2(
    *,
    state_dir: Path,
    seq_u64: int,
    algo_label: str,
    algo_seed_u64: int,
    eval_kind: str,
    theory_id: str,
    theory_kind: str,
    norm_pow_p: int,
    theory_ir_hash: str,
    fit_receipt_hash: str,
    report_hash: str,
    work_cost_total: int,
    workspace: dict[str, Any],
    suitepack_hash: str,
    lease_path: Path | None,
    theory_ir_path: Path,
    fit_receipt_path: Path,
) -> dict[str, Any]:
    rels: dict[str, Any] = {
        "dataset_manifest_rel": str(Path(workspace["manifest_path"]).resolve().relative_to(state_dir.resolve())),
        "dataset_csv_rel": str(Path(workspace["csv_path"]).resolve().relative_to(state_dir.resolve())),
        "dataset_receipt_rel": str(Path(workspace["dataset_receipt_path"]).resolve().relative_to(state_dir.resolve())),
        "split_receipt_rel": str(Path(workspace["split_receipt_path"]).resolve().relative_to(state_dir.resolve())),
        "theory_ir_rel": str(theory_ir_path.resolve().relative_to(state_dir.resolve())),
        "fit_receipt_rel": str(fit_receipt_path.resolve().relative_to(state_dir.resolve())),
        "suitepack_rel": str(
            (Path(workspace["suite_dev_path"]) if eval_kind == "DEV" else Path(workspace["suite_heldout_path"])).resolve().relative_to(state_dir.resolve())
        ),
        "perf_policy_rel": str(Path(workspace["perf_policy_path"]).resolve().relative_to(state_dir.resolve())),
        "ir_policy_rel": str(Path(workspace["ir_policy_path"]).resolve().relative_to(state_dir.resolve())),
        "lease_rel": None if lease_path is None else str(lease_path.resolve().relative_to(state_dir.resolve())),
    }

    return {
        "schema_version": "metasearch_eval_trace_v2",
        "seq_u64": int(seq_u64),
        "algo_label": str(algo_label),
        "algo_seed_u64": int(algo_seed_u64),
        "eval_kind": str(eval_kind),
        "theory_kind": str(theory_kind),
        "norm_pow_p": int(norm_pow_p),
        "theory_id": str(theory_id),
        "theory_ir_hash": str(theory_ir_hash),
        "eval_report_hash": str(report_hash),
        "invocation_id": "",
        "prev_invocation_id": "",
        "work_cost_total": int(work_cost_total),
        "dataset_manifest_hash": str(workspace["manifest_hash"]),
        "dataset_csv_hash": str(workspace["csv_hash"]),
        "dataset_receipt_hash": str(workspace["dataset_receipt_hash"]),
        "split_receipt_hash": str(workspace["split_receipt_hash"]),
        "ir_policy_hash": str(workspace["ir_policy_hash"]),
        "perf_policy_hash": str(workspace["perf_policy_hash"]),
        "suitepack_hash": str(suitepack_hash),
        "fit_receipt_hash": str(fit_receipt_hash),
        "input_rels": rels,
    }


def _run_baseline_ga(
    *,
    state_dir: Path,
    workspace: dict[str, Any],
    sealed_eval_client: SealedEvalClient,
    policy_hash: str,
    baseline_cfg: Any,
    lease_path: Path,
    trace_path: Path,
    selection_dir: Path,
) -> dict[str, Any]:
    rng = random.Random(int(baseline_cfg.seed_u64))
    best_theory_id = ""
    best_key: tuple[int, int, str] | None = None
    seq = 0
    prev_invocation_id = "GENESIS"

    hypos = enumerate_hypotheses()
    dev_rows: list[dict[str, Any]] = []

    for _ in range(int(baseline_cfg.max_dev_evals)):
        hypothesis = hypos[rng.randrange(len(hypos))]
        theory_id = workspace["hypothesis_to_theory_id"][(hypothesis.theory_kind, hypothesis.norm_pow_p)]
        trow = workspace["theories"][theory_id]

        eval_report, sealed = _run_sealed_eval(
            sealed_eval_client=sealed_eval_client,
            dataset_manifest=workspace["manifest_path"],
            dataset_csv=workspace["csv_path"],
            dataset_receipt=workspace["dataset_receipt_path"],
            split_receipt=workspace["split_receipt_path"],
            theory_ir=trow["ir_path"],
            fit_receipt=trow["fit_path"],
            suitepack=workspace["suite_dev_path"],
            perf_policy=workspace["perf_policy_path"],
            ir_policy=workspace["ir_policy_path"],
            eval_kind="DEV",
            lease=None,
            dataset_manifest_hash=str(workspace["manifest_hash"]),
            dataset_csv_hash=str(workspace["csv_hash"]),
            dataset_receipt_hash=str(workspace["dataset_receipt_hash"]),
            split_receipt_hash=str(workspace["split_receipt_hash"]),
            suitepack_hash=str(workspace["suite_dev_hash"]),
            perf_policy_hash=str(workspace["perf_policy_hash"]),
            ir_policy_hash=str(workspace["ir_policy_hash"]),
        )
        _, _, report_hash, work_cost = _persist_eval_artifacts(
            eval_report=eval_report,
            sealed_receipt=sealed,
            eval_reports_dir=workspace["eval_reports_dir"],
            eval_sealed_dir=workspace["eval_sealed_dir"],
        )
        workspace["eval_reports_by_hash"][report_hash] = eval_report
        rmse_q = parse_q32_obj(eval_report["metrics"]["rmse_pos1_q32"])

        if _is_better(rmse_q=rmse_q, work_cost=work_cost, theory_id=theory_id, best=best_key):
            best_key = (int(rmse_q), int(work_cost), theory_id)
            best_theory_id = theory_id

        row = _trace_row_v2(
            state_dir=state_dir,
            seq_u64=seq,
            algo_label="baseline",
            algo_seed_u64=int(baseline_cfg.seed_u64),
            eval_kind="DEV",
            theory_id=theory_id,
            theory_kind=trow["theory_kind"],
            norm_pow_p=trow["norm_pow_p"],
            theory_ir_hash=trow["theory_ir_hash"],
            fit_receipt_hash=trow["fit_receipt_hash"],
            report_hash=report_hash,
            work_cost_total=work_cost,
            workspace=workspace,
            suitepack_hash=workspace["suite_dev_hash"],
            lease_path=None,
            theory_ir_path=trow["ir_path"],
            fit_receipt_path=trow["fit_path"],
        )
        row = append_trace_row(trace_path, row, prev_invocation_id=prev_invocation_id)
        prev_invocation_id = str(row["invocation_id"])
        seq += 1
        dev_rows.append(row)

    if not best_theory_id:
        _fail("INVALID:SCHEMA_FAIL")

    selection = build_selection_receipt(
        algo_label="baseline",
        policy_hash=policy_hash,
        trace_rows_dev=dev_rows,
        eval_reports_by_hash=workspace["eval_reports_by_hash"],
        theory_meta_by_id=workspace["theory_meta_by_id"],
    )
    selection_path, selection_hash = write_hashed_selection_receipt(selection_dir, selection)
    if selection["selected_theory_id"] != best_theory_id:
        _fail("INVALID:SELECTION_MISMATCH")

    for theory_id in [best_theory_id, workspace["baseline_const_theory_id"], workspace["baseline_hooke_theory_id"]]:
        trow = workspace["theories"][theory_id]
        eval_report, sealed = _run_sealed_eval(
            sealed_eval_client=sealed_eval_client,
            dataset_manifest=workspace["manifest_path"],
            dataset_csv=workspace["csv_path"],
            dataset_receipt=workspace["dataset_receipt_path"],
            split_receipt=workspace["split_receipt_path"],
            theory_ir=trow["ir_path"],
            fit_receipt=trow["fit_path"],
            suitepack=workspace["suite_heldout_path"],
            perf_policy=workspace["perf_policy_path"],
            ir_policy=workspace["ir_policy_path"],
            eval_kind="HELDOUT",
            lease=lease_path,
            dataset_manifest_hash=str(workspace["manifest_hash"]),
            dataset_csv_hash=str(workspace["csv_hash"]),
            dataset_receipt_hash=str(workspace["dataset_receipt_hash"]),
            split_receipt_hash=str(workspace["split_receipt_hash"]),
            suitepack_hash=str(workspace["suite_heldout_hash"]),
            perf_policy_hash=str(workspace["perf_policy_hash"]),
            ir_policy_hash=str(workspace["ir_policy_hash"]),
        )
        _, _, report_hash, work_cost = _persist_eval_artifacts(
            eval_report=eval_report,
            sealed_receipt=sealed,
            eval_reports_dir=workspace["eval_reports_dir"],
            eval_sealed_dir=workspace["eval_sealed_dir"],
        )
        workspace["eval_reports_by_hash"][report_hash] = eval_report

        row = _trace_row_v2(
            state_dir=state_dir,
            seq_u64=seq,
            algo_label="baseline",
            algo_seed_u64=int(baseline_cfg.seed_u64),
            eval_kind="HELDOUT",
            theory_id=theory_id,
            theory_kind=trow["theory_kind"],
            norm_pow_p=trow["norm_pow_p"],
            theory_ir_hash=trow["theory_ir_hash"],
            fit_receipt_hash=trow["fit_receipt_hash"],
            report_hash=report_hash,
            work_cost_total=work_cost,
            workspace=workspace,
            suitepack_hash=workspace["suite_heldout_hash"],
            lease_path=lease_path,
            theory_ir_path=trow["ir_path"],
            fit_receipt_path=trow["fit_path"],
        )
        row = append_trace_row(trace_path, row, prev_invocation_id=prev_invocation_id)
        prev_invocation_id = str(row["invocation_id"])
        seq += 1

    return {
        "selected_theory_id": best_theory_id,
        "selection_receipt_path": selection_path,
        "selection_receipt_hash": selection_hash,
    }


def _run_candidate_trace_prior(
    *,
    state_dir: Path,
    workspace: dict[str, Any],
    sealed_eval_client: SealedEvalClient,
    policy_hash: str,
    candidate_cfg: CandidateSearchConfig,
    lease_path: Path,
    trace_path: Path,
    selection_dir: Path,
    plan: dict[str, Any],
) -> dict[str, Any]:
    best_theory_id = ""
    best_key: tuple[int, int, str] | None = None
    seq = 0
    prev_invocation_id = "GENESIS"

    ranked = list(plan.get("ranked") or [])
    if not ranked:
        _fail("INVALID:SEARCH_PLAN_REPLAY_MISMATCH")

    dev_rows: list[dict[str, Any]] = []

    for entry in ranked[: int(candidate_cfg.max_dev_evals)]:
        kind = str(entry.get("theory_kind"))
        p = int(entry.get("norm_pow_p", 0))
        theory_id = workspace["hypothesis_to_theory_id"].get((kind, p))
        if theory_id is None:
            _fail("INVALID:SEARCH_PLAN_REPLAY_MISMATCH")
        trow = workspace["theories"][theory_id]

        eval_report, sealed = _run_sealed_eval(
            sealed_eval_client=sealed_eval_client,
            dataset_manifest=workspace["manifest_path"],
            dataset_csv=workspace["csv_path"],
            dataset_receipt=workspace["dataset_receipt_path"],
            split_receipt=workspace["split_receipt_path"],
            theory_ir=trow["ir_path"],
            fit_receipt=trow["fit_path"],
            suitepack=workspace["suite_dev_path"],
            perf_policy=workspace["perf_policy_path"],
            ir_policy=workspace["ir_policy_path"],
            eval_kind="DEV",
            lease=None,
            dataset_manifest_hash=str(workspace["manifest_hash"]),
            dataset_csv_hash=str(workspace["csv_hash"]),
            dataset_receipt_hash=str(workspace["dataset_receipt_hash"]),
            split_receipt_hash=str(workspace["split_receipt_hash"]),
            suitepack_hash=str(workspace["suite_dev_hash"]),
            perf_policy_hash=str(workspace["perf_policy_hash"]),
            ir_policy_hash=str(workspace["ir_policy_hash"]),
        )
        _, _, report_hash, work_cost = _persist_eval_artifacts(
            eval_report=eval_report,
            sealed_receipt=sealed,
            eval_reports_dir=workspace["eval_reports_dir"],
            eval_sealed_dir=workspace["eval_sealed_dir"],
        )
        workspace["eval_reports_by_hash"][report_hash] = eval_report
        rmse_q = parse_q32_obj(eval_report["metrics"]["rmse_pos1_q32"])

        if _is_better(rmse_q=rmse_q, work_cost=work_cost, theory_id=theory_id, best=best_key):
            best_key = (int(rmse_q), int(work_cost), theory_id)
            best_theory_id = theory_id

        row = _trace_row_v2(
            state_dir=state_dir,
            seq_u64=seq,
            algo_label="candidate",
            algo_seed_u64=int(candidate_cfg.seed_u64),
            eval_kind="DEV",
            theory_id=theory_id,
            theory_kind=trow["theory_kind"],
            norm_pow_p=trow["norm_pow_p"],
            theory_ir_hash=trow["theory_ir_hash"],
            fit_receipt_hash=trow["fit_receipt_hash"],
            report_hash=report_hash,
            work_cost_total=work_cost,
            workspace=workspace,
            suitepack_hash=workspace["suite_dev_hash"],
            lease_path=None,
            theory_ir_path=trow["ir_path"],
            fit_receipt_path=trow["fit_path"],
        )
        row = append_trace_row(trace_path, row, prev_invocation_id=prev_invocation_id)
        prev_invocation_id = str(row["invocation_id"])
        seq += 1
        dev_rows.append(row)

    if not best_theory_id:
        _fail("INVALID:SEARCH_PLAN_REPLAY_MISMATCH")

    selection = build_selection_receipt(
        algo_label="candidate",
        policy_hash=policy_hash,
        trace_rows_dev=dev_rows,
        eval_reports_by_hash=workspace["eval_reports_by_hash"],
        theory_meta_by_id=workspace["theory_meta_by_id"],
    )
    selection_path, selection_hash = write_hashed_selection_receipt(selection_dir, selection)
    if selection["selected_theory_id"] != best_theory_id:
        _fail("INVALID:SELECTION_MISMATCH")

    for theory_id in [best_theory_id, workspace["baseline_const_theory_id"], workspace["baseline_hooke_theory_id"]]:
        trow = workspace["theories"][theory_id]
        eval_report, sealed = _run_sealed_eval(
            sealed_eval_client=sealed_eval_client,
            dataset_manifest=workspace["manifest_path"],
            dataset_csv=workspace["csv_path"],
            dataset_receipt=workspace["dataset_receipt_path"],
            split_receipt=workspace["split_receipt_path"],
            theory_ir=trow["ir_path"],
            fit_receipt=trow["fit_path"],
            suitepack=workspace["suite_heldout_path"],
            perf_policy=workspace["perf_policy_path"],
            ir_policy=workspace["ir_policy_path"],
            eval_kind="HELDOUT",
            lease=lease_path,
            dataset_manifest_hash=str(workspace["manifest_hash"]),
            dataset_csv_hash=str(workspace["csv_hash"]),
            dataset_receipt_hash=str(workspace["dataset_receipt_hash"]),
            split_receipt_hash=str(workspace["split_receipt_hash"]),
            suitepack_hash=str(workspace["suite_heldout_hash"]),
            perf_policy_hash=str(workspace["perf_policy_hash"]),
            ir_policy_hash=str(workspace["ir_policy_hash"]),
        )
        _, _, report_hash, work_cost = _persist_eval_artifacts(
            eval_report=eval_report,
            sealed_receipt=sealed,
            eval_reports_dir=workspace["eval_reports_dir"],
            eval_sealed_dir=workspace["eval_sealed_dir"],
        )
        workspace["eval_reports_by_hash"][report_hash] = eval_report

        row = _trace_row_v2(
            state_dir=state_dir,
            seq_u64=seq,
            algo_label="candidate",
            algo_seed_u64=int(candidate_cfg.seed_u64),
            eval_kind="HELDOUT",
            theory_id=theory_id,
            theory_kind=trow["theory_kind"],
            norm_pow_p=trow["norm_pow_p"],
            theory_ir_hash=trow["theory_ir_hash"],
            fit_receipt_hash=trow["fit_receipt_hash"],
            report_hash=report_hash,
            work_cost_total=work_cost,
            workspace=workspace,
            suitepack_hash=workspace["suite_heldout_hash"],
            lease_path=lease_path,
            theory_ir_path=trow["ir_path"],
            fit_receipt_path=trow["fit_path"],
        )
        row = append_trace_row(trace_path, row, prev_invocation_id=prev_invocation_id)
        prev_invocation_id = str(row["invocation_id"])
        seq += 1

    return {
        "selected_theory_id": best_theory_id,
        "selection_receipt_path": selection_path,
        "selection_receipt_hash": selection_hash,
    }


def _sum_work_cost(trace_path: Path) -> int:
    total = 0
    if not trace_path.exists():
        return 0
    for raw in trace_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        row = json.loads(raw)
        total += int(row.get("work_cost_total", 0))
    return total


def _count_eval_kind(trace_path: Path, *, eval_kind: str) -> int:
    total = 0
    if not trace_path.exists():
        return 0
    for raw in trace_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        row = json.loads(raw)
        if str(row.get("eval_kind")) == eval_kind:
            total += 1
    return int(total)


def _run_v13_science(*, dataset_manifest: Path, dataset_csv: Path, out_root: Path, python_exe: str) -> None:
    if out_root.exists():
        shutil.rmtree(out_root)
    control_dir = out_root / "state" / "control"
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "ENABLE_RESEARCH").write_text("enable\n", encoding="utf-8")
    (control_dir / "ENABLE_SAS_SCIENCE").write_text("enable\n", encoding="utf-8")
    write_canon_json(control_dir / "SAS_SCIENCE_LEASE.json", {"lease_id": "v16_1"})

    cmd = [
        python_exe,
        "-m",
        "orchestrator.rsi_sas_science_v13_0",
        "--dataset_csv",
        str(dataset_csv),
        "--dataset_manifest",
        str(dataset_manifest),
        "--campaign_pack",
        str(_repo_root() / "campaigns" / "rsi_sas_science_v13_0" / "rsi_sas_science_pack_v1.json"),
        "--state_dir",
        str(out_root),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=_pythonpath_env())
    if result.returncode != 0:
        _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")


def _selected_from_v13_run(run_root: Path) -> tuple[str, str]:
    def _from_promotion(state_dir: Path) -> tuple[str, str] | None:
        promo_dir = state_dir / "promotion"
        promos = sorted(promo_dir.glob("sha256_*.sas_science_promotion_bundle_v1.json"))
        if len(promos) > 1:
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
        if len(promos) == 0:
            return None
        promo = load_canon_json(promos[0])
        if not isinstance(promo, dict):
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
        discovery = promo.get("discovery_bundle")
        if not isinstance(discovery, dict):
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
        theory_id = discovery.get("theory_id")
        law_kind = discovery.get("law_kind")
        if not isinstance(theory_id, str) or not theory_id.startswith("sha256:"):
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
        if not isinstance(law_kind, str) or not law_kind:
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
        return theory_id, law_kind

    def _from_selection(state_dir: Path, config_dir: Path) -> tuple[str, str] | None:
        selection_dir = state_dir / "selection"
        selections = sorted(selection_dir.glob("sha256_*.sas_science_selection_receipt_v1.json"))
        if len(selections) == 0:
            return None
        if len(selections) != 1:
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
        selection = load_canon_json(selections[0])
        if not isinstance(selection, dict):
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
        selected_theory_id = selection.get("selected_theory_id")
        if not isinstance(selected_theory_id, str) or not selected_theory_id.startswith("sha256:"):
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
        theory_hex = selected_theory_id.split(":", 1)[1]
        if len(theory_hex) != 64:
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
        ir_path = state_dir / "theory" / "ir" / f"sha256_{theory_hex}.sas_science_theory_ir_v1.json"
        if not ir_path.exists() or not ir_path.is_file():
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
        ir_obj = load_canon_json(ir_path)
        if not isinstance(ir_obj, dict):
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")

        fit_receipts: list[dict[str, Any]] = []
        fit_dir = state_dir / "fit" / "receipts"
        for path in sorted(fit_dir.glob("sha256_*.sas_science_fit_receipt_v1.json")):
            row = load_canon_json(path)
            if isinstance(row, dict) and str(row.get("theory_id")) == selected_theory_id:
                fit_receipts.append(row)
        if len(fit_receipts) != 1:
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")

        ir_policy_path = config_dir / "sas_science_ir_policy_v1.json"
        if not ir_policy_path.exists() or not ir_policy_path.is_file():
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
        ir_policy = load_canon_json(ir_policy_path)
        if not isinstance(ir_policy, dict):
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
        law = canonicalize_law(
            ir=ir_obj,
            fit_receipt=fit_receipts[0],
            ir_policy=ir_policy,
        ).get("law_kind")
        if not isinstance(law, str) or not law:
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
        return selected_theory_id, law

    state_candidates = [
        (run_root / "state", run_root / "config"),
        (run_root / "daemon" / "rsi_sas_science_v13_0" / "state", run_root / "daemon" / "rsi_sas_science_v13_0" / "config"),
    ]
    results: list[tuple[str, str]] = []
    for state_dir, config_dir in state_candidates:
        if not state_dir.exists() or not state_dir.is_dir():
            continue
        from_promotion = _from_promotion(state_dir)
        if from_promotion is not None:
            results.append(from_promotion)
            continue
        from_selection = _from_selection(state_dir, config_dir)
        if from_selection is not None:
            results.append(from_selection)
    if not results:
        _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
    first = results[0]
    for row in results[1:]:
        if row != first:
            _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
    return first


def _frozen_pack_from_config(*, config_dir: Path) -> dict[str, Any]:
    pack = {
        "schema_version": "rsi_sas_metasearch_pack_v16_1",
        "policy_rel": "sas_metasearch_policy_v1.json",
        "policy_hash": hash_file(config_dir / "sas_metasearch_policy_v1.json"),
        "baseline_search_config_rel": "baseline_search_config_v1.json",
        "baseline_search_config_hash": hash_file(config_dir / "baseline_search_config_v1.json"),
        "candidate_search_config_rel": "candidate_search_config_v1.json",
        "candidate_search_config_hash": hash_file(config_dir / "candidate_search_config_v1.json"),
        "gravity_dataset_manifest_rel": "datasets/gravity_dataset_manifest_v1.json",
        "gravity_dataset_manifest_hash": hash_file(config_dir / "datasets" / "gravity_dataset_manifest_v1.json"),
        "gravity_dataset_rel": "datasets/gravity_dataset.csv",
        "gravity_dataset_hash": hash_file(config_dir / "datasets" / "gravity_dataset.csv"),
        "hooke_dataset_manifest_rel": "datasets/hooke_dataset_manifest_v1.json",
        "hooke_dataset_manifest_hash": hash_file(config_dir / "datasets" / "hooke_dataset_manifest_v1.json"),
        "hooke_dataset_rel": "datasets/hooke_dataset.csv",
        "hooke_dataset_hash": hash_file(config_dir / "datasets" / "hooke_dataset.csv"),
        "trace_corpus_rel": "trace_corpus/science_trace_corpus_suitepack_dev_v1.json",
        "trace_corpus_hash": hash_file(config_dir / "trace_corpus" / "science_trace_corpus_suitepack_dev_v1.json"),
    }
    return pack


def _parse_intensity_env_int(name: str) -> int | None:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except Exception as exc:  # noqa: BLE001
        raise MetaSearchRunError(f"INVALID:{name}") from exc
    if parsed < 1 or parsed > 100000:
        _fail(f"INVALID:{name}")
    return int(parsed)


def _maybe_apply_omega_intensity_v16(*, config_dir: Path, state_dir: Path) -> int | None:
    candidate_parsed = _parse_intensity_env_int("V16_MAX_DEV_EVALS")
    baseline_parsed = _parse_intensity_env_int("V16_BASELINE_MAX_DEV_EVALS")
    min_corpus_cases_parsed = _parse_intensity_env_int("V16_MIN_CORPUS_CASES")

    candidate_cfg_path = config_dir / "candidate_search_config_v1.json"
    baseline_cfg_path = config_dir / "baseline_search_config_v1.json"

    if candidate_parsed is not None:
        candidate_cfg = load_canon_json(candidate_cfg_path)
        if not isinstance(candidate_cfg, dict) or candidate_cfg.get("schema_version") != "candidate_search_config_v1":
            _fail("INVALID:SCHEMA_FAIL")
        candidate_cfg["max_dev_evals"] = int(candidate_parsed)
        write_canon_json(candidate_cfg_path, candidate_cfg)

    if baseline_parsed is not None:
        baseline_cfg = load_canon_json(baseline_cfg_path)
        if not isinstance(baseline_cfg, dict) or baseline_cfg.get("schema_version") != "baseline_search_config_v1":
            _fail("INVALID:SCHEMA_FAIL")
        baseline_cfg["max_dev_evals"] = int(baseline_parsed)
        # Keep baseline config internally self-consistent for loader validation.
        baseline_cfg["population"] = int(baseline_parsed)
        baseline_cfg["generations"] = 1
        write_canon_json(baseline_cfg_path, baseline_cfg)

    env_payload: dict[str, str] = {}
    if candidate_parsed is not None:
        env_payload["V16_MAX_DEV_EVALS"] = str(candidate_parsed)
    if baseline_parsed is not None:
        env_payload["V16_BASELINE_MAX_DEV_EVALS"] = str(baseline_parsed)
    if min_corpus_cases_parsed is not None:
        env_payload["V16_MIN_CORPUS_CASES"] = str(min_corpus_cases_parsed)

    receipt = {
        "schema_version": "omega_intensity_receipt_v1",
        "campaign_id": "rsi_sas_metasearch_v16_1",
        "env": env_payload,
        "applied": {
            "candidate_search_config_rel": "candidate_search_config_v1.json",
            "candidate_search_config_hash": hash_file(candidate_cfg_path),
            "baseline_search_config_rel": "baseline_search_config_v1.json",
            "baseline_search_config_hash": hash_file(baseline_cfg_path),
        },
    }
    write_canon_json(state_dir / "control" / "omega_intensity_receipt_v1.json", receipt)
    return min_corpus_cases_parsed


def run_sas_metasearch(
    *,
    campaign_pack: Path,
    out_dir: Path,
    campaign_tag: str = "rsi_sas_metasearch_v16_1",
    min_corpus_cases: int = 100,
) -> dict[str, Any]:
    pack_path = campaign_pack.resolve()
    if not pack_path.exists():
        _fail("INVALID:SCHEMA_FAIL")

    run_root = out_dir.resolve()
    daemon_root = run_root / "daemon" / campaign_tag
    config_dir = daemon_root / "config"
    state_dir = daemon_root / "state"

    if daemon_root.exists():
        shutil.rmtree(daemon_root)

    for path in [
        config_dir,
        state_dir / "control",
        state_dir / "trace_corpus",
        state_dir / "prior",
        state_dir / "plan",
        state_dir / "build",
        state_dir / "selection",
        state_dir / "eval_trace",
        state_dir / "science_runs",
        state_dir / "reports",
        state_dir / "promotion",
        state_dir / "ledger",
    ]:
        path.mkdir(parents=True, exist_ok=True)

    raw_pack = load_canon_json(pack_path)
    if not isinstance(raw_pack, dict) or raw_pack.get("schema_version") != "rsi_sas_metasearch_pack_v16_1":
        _fail("INVALID:SCHEMA_FAIL")

    # Freeze config into canonical filenames under config/ so replay is filename-invariant.
    for key, dst_name in [
        ("policy_rel", "sas_metasearch_policy_v1.json"),
        ("baseline_search_config_rel", "baseline_search_config_v1.json"),
        ("candidate_search_config_rel", "candidate_search_config_v1.json"),
    ]:
        src = _resolve_path(pack_path.parent, str(raw_pack[key]))
        _copy_json(src, config_dir / dst_name)

    for key, dst_name in [
        ("gravity_dataset_manifest_rel", "gravity_dataset_manifest_v1.json"),
        ("hooke_dataset_manifest_rel", "hooke_dataset_manifest_v1.json"),
    ]:
        src = _resolve_path(pack_path.parent, str(raw_pack[key]))
        _copy_json(src, config_dir / "datasets" / dst_name)
    for key, dst_name in [
        ("gravity_dataset_rel", "gravity_dataset.csv"),
        ("hooke_dataset_rel", "hooke_dataset.csv"),
    ]:
        src = _resolve_path(pack_path.parent, str(raw_pack[key]))
        _copy_csv(src, config_dir / "datasets" / dst_name)

    trace_src = _resolve_path(pack_path.parent, str(raw_pack["trace_corpus_rel"]))
    _copy_json(trace_src, config_dir / "trace_corpus" / "science_trace_corpus_suitepack_dev_v1.json")

    source_daemon_cfg = _repo_root() / "daemon" / campaign_tag / "config"
    for name in ["toolchain_manifest_py_v1.json", "toolchain_manifest_rust_v1.json"]:
        src = pack_path.parent / name
        if not src.exists():
            src = source_daemon_cfg / name
        if not src.exists():
            _fail("INVALID:TOOLCHAIN_MANIFEST")
        _copy_json(src, config_dir / name)

    min_corpus_cases_override = _maybe_apply_omega_intensity_v16(config_dir=config_dir, state_dir=state_dir)
    effective_min_corpus_cases = int(min_corpus_cases_override) if min_corpus_cases_override is not None else int(min_corpus_cases)

    frozen_pack = _frozen_pack_from_config(config_dir=config_dir)
    write_canon_json(config_dir / "rsi_sas_metasearch_pack_v16_1.json", frozen_pack)

    policy = load_policy(config_dir / "sas_metasearch_policy_v1.json")
    policy_hash = sha256_prefixed(canon_bytes(load_canon_json(config_dir / "sas_metasearch_policy_v1.json")))
    baseline_cfg = load_baseline_search_config(config_dir / "baseline_search_config_v1.json")
    candidate_cfg = load_candidate_search_config(config_dir / "candidate_search_config_v1.json")
    py_toolchain = load_py_toolchain_manifest(config_dir / "toolchain_manifest_py_v1.json")
    rust_toolchain = load_rust_toolchain_manifest(config_dir / "toolchain_manifest_rust_v1.json")

    control = state_dir / "control"
    (control / "ENABLE_RESEARCH").write_text("enable\n", encoding="utf-8")
    (control / "ENABLE_SAS_METASEARCH").write_text("enable\n", encoding="utf-8")
    lease_path = control / "SAS_METASEARCH_LEASE.json"
    write_canon_json(lease_path, {"lease_id": "v16_1"})

    ledger_path = state_dir / "ledger" / "metasearch_ledger_v1.jsonl"
    tick = 0
    _append_ledger(ledger_path, "METASEARCH_BOOT", {}, tick)
    tick += 1

    corpus = load_suitepack(
        config_dir / "trace_corpus" / "science_trace_corpus_suitepack_dev_v1.json",
        min_cases=effective_min_corpus_cases,
    )
    corpus_path, corpus_hash = _write_hashed_json(
        state_dir / "trace_corpus",
        "metasearch_trace_corpus_suitepack_v1.json",
        corpus,
    )
    _append_ledger(ledger_path, "METASEARCH_CORPUS_FROZEN", {"trace_corpus_hash": corpus_hash}, tick)
    tick += 1

    prior = build_prior_from_corpus(corpus, alpha=1)
    prior_path, prior_hash = _write_hashed_json(state_dir / "prior", "metasearch_prior_v1.json", prior)
    _append_ledger(ledger_path, "METASEARCH_PRIOR_READY", {"prior_hash": prior_hash}, tick)
    tick += 1

    crate = materialize_rust_crate(prior=prior, k_max_dev_evals=candidate_cfg.max_dev_evals)
    scan_rust_sources(crate / "src", forbidden_tokens=list(policy.get("forbidden_rust_tokens") or []))
    binary_path, build_receipt = build_release_binary_with_receipt(crate_dir=crate, rust_toolchain=rust_toolchain)
    build_receipt_path, build_receipt_hash = write_hashed_build_receipt(state_dir / "build", build_receipt)
    binary_hash = str(build_receipt["binary_sha256"])

    tmp_plan = state_dir / "plan" / "metasearch_plan_raw_v1.json"
    plan = run_planner(binary_path=binary_path, prior_path=prior_path, out_plan_path=tmp_plan)
    plan_path, plan_hash = _write_hashed_json(state_dir / "plan", "metasearch_plan_v1.json", plan)
    if tmp_plan.exists():
        tmp_plan.unlink()
    _append_ledger(
        ledger_path,
        "METASEARCH_PLAN_READY",
        {
            "plan_hash": plan_hash,
            "binary_hash": binary_hash,
            "build_receipt_hash": build_receipt_hash,
        },
        tick,
    )
    tick += 1

    workspace = _prepare_eval_workspace(
        state_dir=state_dir,
        dataset_manifest_path=config_dir / "datasets" / "gravity_dataset_manifest_v1.json",
        dataset_csv_path=config_dir / "datasets" / "gravity_dataset.csv",
    )

    baseline_trace = state_dir / "eval_trace" / "baseline.metasearch_eval_trace_v2.jsonl"
    candidate_trace = state_dir / "eval_trace" / "candidate.metasearch_eval_trace_v2.jsonl"
    try:
        sealed_eval_client = start_sealed_eval_client(str(py_toolchain["python_executable"]), _pythonpath_env())
    except SealedEvalClientError:
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    try:
        baseline_result = _run_baseline_ga(
            state_dir=state_dir,
            workspace=workspace,
            sealed_eval_client=sealed_eval_client,
            policy_hash=policy_hash,
            baseline_cfg=baseline_cfg,
            lease_path=lease_path,
            trace_path=baseline_trace,
            selection_dir=state_dir / "selection",
        )
        candidate_result = _run_candidate_trace_prior(
            state_dir=state_dir,
            workspace=workspace,
            sealed_eval_client=sealed_eval_client,
            policy_hash=policy_hash,
            candidate_cfg=candidate_cfg,
            lease_path=lease_path,
            trace_path=candidate_trace,
            selection_dir=state_dir / "selection",
            plan=plan,
        )
    finally:
        try:
            sealed_eval_client.close()
        except SealedEvalClientError:
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    c_base = _sum_work_cost(baseline_trace)
    c_cand = _sum_work_cost(candidate_trace)
    baseline_dev_eval_count = _count_eval_kind(baseline_trace, eval_kind="DEV")
    candidate_dev_eval_count = _count_eval_kind(candidate_trace, eval_kind="DEV")
    gate_pass = c_cand * 2 <= c_base

    compute = {
        "schema_version": "metasearch_compute_report_v1",
        "report_id": "",
        "baseline_eval_trace_hash": trace_file_hash(baseline_trace),
        "candidate_eval_trace_hash": trace_file_hash(candidate_trace),
        "baseline_selection_receipt_hash": baseline_result["selection_receipt_hash"],
        "candidate_selection_receipt_hash": candidate_result["selection_receipt_hash"],
        "c_base_work_cost_total": int(c_base),
        "c_cand_work_cost_total": int(c_cand),
        "baseline_dev_eval_count_u64": int(baseline_dev_eval_count),
        "candidate_dev_eval_count_u64": int(candidate_dev_eval_count),
        "efficiency_gate_pass": bool(gate_pass),
    }
    compute["report_id"] = sha256_prefixed(canon_bytes({k: v for k, v in compute.items() if k != "report_id"}))
    compute_path, compute_hash = _write_hashed_json(state_dir / "reports", "metasearch_compute_report_v1.json", compute)
    _append_ledger(ledger_path, "METASEARCH_COMPUTE_READY", {"compute_hash": compute_hash}, tick)
    tick += 1

    science_runs = state_dir / "science_runs"
    baseline_science = science_runs / "baseline_science"
    candidate_science = science_runs / "candidate_science"
    foil_science = science_runs / "candidate_foil_hooke"

    py_exe = str(py_toolchain["python_executable"])
    _run_v13_science(
        dataset_manifest=config_dir / "datasets" / "gravity_dataset_manifest_v1.json",
        dataset_csv=config_dir / "datasets" / "gravity_dataset.csv",
        out_root=baseline_science,
        python_exe=py_exe,
    )
    _run_v13_science(
        dataset_manifest=config_dir / "datasets" / "gravity_dataset_manifest_v1.json",
        dataset_csv=config_dir / "datasets" / "gravity_dataset.csv",
        out_root=candidate_science,
        python_exe=py_exe,
    )
    _run_v13_science(
        dataset_manifest=config_dir / "datasets" / "hooke_dataset_manifest_v1.json",
        dataset_csv=config_dir / "datasets" / "hooke_dataset.csv",
        out_root=foil_science,
        python_exe=py_exe,
    )

    baseline_theory_id_v13, baseline_law_kind = _selected_from_v13_run(baseline_science)
    candidate_theory_id_v13, candidate_law_kind = _selected_from_v13_run(candidate_science)
    _, foil_law_kind = _selected_from_v13_run(foil_science)

    acceptance_reasons = [
        reason
        for reason, cond in [
            ("COGNITIVE_EFFICIENCY_GATE_FAIL", not gate_pass),
            ("LAW_NOT_NEWTONIAN", candidate_law_kind not in ("NEWTON_CENTRAL_V1", "NEWTON_NBODY_V1")),
            ("NEWTON_ALWAYS_OUTPUT", foil_law_kind in ("NEWTON_CENTRAL_V1", "NEWTON_NBODY_V1")),
        ]
        if cond
    ]

    promotion_payload = {
        "pack_hash": sha256_prefixed(canon_bytes(frozen_pack)),
        "policy_hash": policy_hash,
        "trace_corpus_hash": corpus_hash,
        "prior_hash": prior_hash,
        "plan_hash": plan_hash,
        "baseline_search_config_hash": sha256_prefixed(canon_bytes(load_canon_json(config_dir / "baseline_search_config_v1.json"))),
        "candidate_search_config_hash": sha256_prefixed(canon_bytes(load_canon_json(config_dir / "candidate_search_config_v1.json"))),
        "dataset_manifest_hash": workspace["manifest_hash"],
        "dataset_csv_hash": workspace["csv_hash"],
        "dataset_receipt_hash": workspace["dataset_receipt_hash"],
        "split_receipt_hash": workspace["split_receipt_hash"],
        "toolchain_manifest_py_hash": hash_file(config_dir / "toolchain_manifest_py_v1.json"),
        "toolchain_manifest_rust_hash": hash_file(config_dir / "toolchain_manifest_rust_v1.json"),
        "rust_crate_tree_hash": build_receipt["crate_tree_hash"],
        "rust_build_receipt_hash": build_receipt_hash,
        "rust_binary_hash": binary_hash,
        "baseline_eval_trace_hash": compute["baseline_eval_trace_hash"],
        "candidate_eval_trace_hash": compute["candidate_eval_trace_hash"],
        "baseline_selection_receipt_hash": baseline_result["selection_receipt_hash"],
        "candidate_selection_receipt_hash": candidate_result["selection_receipt_hash"],
        "compute_report_hash": compute_hash,
        "baseline_selected_law_kind": baseline_law_kind,
        "baseline_selected_theory_id": baseline_theory_id_v13,
        "candidate_selected_law_kind": candidate_law_kind,
        "candidate_selected_theory_id": candidate_theory_id_v13,
        "acceptance_decision": {
            "pass": bool(
                gate_pass
                and candidate_law_kind in ("NEWTON_CENTRAL_V1", "NEWTON_NBODY_V1")
                and foil_law_kind not in ("NEWTON_CENTRAL_V1", "NEWTON_NBODY_V1")
            ),
            "reasons": acceptance_reasons,
        },
    }
    promotion = build_promotion_bundle(promotion_payload)
    promotion_path, promotion_hash = write_hashed_bundle(state_dir / "promotion", promotion)
    _append_ledger(ledger_path, "METASEARCH_PROMOTION_WRITTEN", {"promotion_hash": promotion_hash}, tick)

    return {
        "status": "OK",
        "state_dir": str(state_dir),
        "promotion_bundle": str(promotion_path),
        "plan_hash": plan_hash,
        "compute_report_hash": compute_hash,
        "baseline_selected_theory_id": baseline_result["selected_theory_id"],
        "candidate_selected_theory_id": candidate_result["selected_theory_id"],
        "candidate_law_kind": candidate_law_kind,
        "foil_law_kind": foil_law_kind,
        "build_receipt": str(build_receipt_path),
        "baseline_selection_receipt": str(baseline_result["selection_receipt_path"]),
        "candidate_selection_receipt": str(candidate_result["selection_receipt_path"]),
    }


__all__ = ["run_sas_metasearch", "MetaSearchRunError"]
