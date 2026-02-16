"""Runtime coordinator for SAS-Metasearch v16.0."""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import tempfile
import json
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line
from ..v13_0.sas_science_canon_v1 import canonicalize_law
from ..v13_0.sas_science_dataset_v1 import (
    compute_dataset_receipt,
    compute_split_receipt,
    load_dataset,
    load_manifest,
)
from ..v13_0.sas_science_eval_v1 import compute_report_hash
from ..v13_0.sas_science_fit_v1 import fit_theory
from ..v13_0.sas_science_ir_v1 import compute_complexity, compute_theory_id, validate_ir
from ..v13_0.sas_science_math_v1 import parse_q32_obj
from .metasearch_build_rust_v1 import (
    build_release_binary,
    file_hash,
    load_py_toolchain_manifest,
    load_rust_toolchain_manifest,
    run_planner,
    scan_rust_sources,
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
from .metasearch_trace_v1 import append_trace_row, trace_file_hash


class MetaSearchRunError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise MetaSearchRunError(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _cdel_root() -> Path:
    return _repo_root() / "CDEL-v2"


def _orch_root() -> Path:
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
    write_canon_json(dst, load_canon_json(src))


def _copy_csv(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def _pythonpath_env(existing_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(existing_env or os.environ)
    parts: list[str] = [str(_cdel_root()), str(_orch_root())]
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
    config_dir: Path,
    dataset_manifest_path: Path,
    dataset_csv_path: Path,
) -> dict[str, Any]:
    workspace = state_dir / "search_workspace"
    data_manifest_dir = workspace / "data" / "manifest"
    data_csv_dir = workspace / "data" / "csv"
    data_receipts_dir = workspace / "data" / "receipts"
    ir_dir = workspace / "theory" / "ir"
    fit_dir = workspace / "fit" / "receipts"
    eval_reports_dir = workspace / "eval" / "reports"
    eval_sealed_dir = workspace / "eval" / "sealed"
    ws_config = workspace / "config"

    for path in [
        data_manifest_dir,
        data_csv_dir,
        data_receipts_dir,
        ir_dir,
        fit_dir,
        eval_reports_dir,
        eval_sealed_dir,
        ws_config,
    ]:
        path.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(dataset_manifest_path)
    csv_bytes = dataset_csv_path.read_bytes()

    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    manifest_out = data_manifest_dir / f"sha256_{manifest_hash.split(':', 1)[1]}.sas_science_dataset_manifest_v1.json"
    write_canon_json(manifest_out, manifest)

    csv_hash = sha256_prefixed(csv_bytes)
    csv_out = data_csv_dir / f"sha256_{csv_hash.split(':', 1)[1]}.dataset.csv"
    csv_out.write_bytes(csv_bytes)

    dataset_obj = load_dataset(csv_out, manifest)
    dataset_receipt = compute_dataset_receipt(manifest=manifest, csv_bytes=csv_bytes, row_count=len(dataset_obj.times_q32))
    dataset_receipt_out = (
        data_receipts_dir / f"sha256_{dataset_receipt['dataset_id'].split(':', 1)[1]}.sas_science_dataset_receipt_v1.json"
    )
    write_canon_json(dataset_receipt_out, dataset_receipt)

    split_receipt = compute_split_receipt(
        manifest=manifest,
        dataset_id=dataset_receipt["dataset_id"],
        row_count=dataset_receipt["row_count"],
    )
    split_receipt_out = data_receipts_dir / f"sha256_{split_receipt['split_id'].split(':', 1)[1]}.sas_science_split_receipt_v1.json"
    write_canon_json(split_receipt_out, split_receipt)

    # Reuse v13 science policy configs exactly.
    source_cfg = _repo_root() / "campaigns" / "rsi_sas_science_v13_0"
    _copy_json(source_cfg / "sas_science_ir_policy_v1.json", ws_config / "sas_science_ir_policy_v1.json")
    _copy_json(source_cfg / "sas_science_perf_policy_v1.json", ws_config / "sas_science_perf_policy_v1.json")
    _copy_json(source_cfg / "sas_science_suitepack_dev_v1.json", ws_config / "sas_science_suitepack_dev_v1.json")
    _copy_json(source_cfg / "sas_science_suitepack_heldout_v1.json", ws_config / "sas_science_suitepack_heldout_v1.json")

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

    for theory_id, row in theories.items():
        ir = row["ir"]
        ir_out = ir_dir / f"sha256_{theory_id.split(':', 1)[1]}.sas_science_theory_ir_v1.json"
        write_canon_json(ir_out, ir)
        fit = fit_theory(dataset=dataset_obj, ir=ir, split_receipt=split_receipt, ir_policy=ir_policy)
        fit_out = fit_dir / f"sha256_{fit['receipt_id'].split(':', 1)[1]}.sas_science_fit_receipt_v1.json"
        write_canon_json(fit_out, fit)
        row["ir_path"] = ir_out
        row["fit_receipt"] = fit
        row["fit_path"] = fit_out

    hypothesis_to_theory_id: dict[tuple[str, int], str] = {}
    for theory_id, row in theories.items():
        h = row.get("hypothesis")
        if h is None:
            continue
        hypothesis_to_theory_id[(h.theory_kind, h.norm_pow_p)] = theory_id

    return {
        "workspace": workspace,
        "manifest": manifest,
        "manifest_path": manifest_out,
        "csv_path": csv_out,
        "dataset_receipt": dataset_receipt,
        "dataset_receipt_path": dataset_receipt_out,
        "split_receipt": split_receipt,
        "split_receipt_path": split_receipt_out,
        "ir_policy_path": ws_config / "sas_science_ir_policy_v1.json",
        "perf_policy_path": ws_config / "sas_science_perf_policy_v1.json",
        "suite_dev_path": ws_config / "sas_science_suitepack_dev_v1.json",
        "suite_heldout_path": ws_config / "sas_science_suitepack_heldout_v1.json",
        "theories": theories,
        "hypothesis_to_theory_id": hypothesis_to_theory_id,
        "baseline_const_theory_id": baseline_const["theory_id"],
        "baseline_hooke_theory_id": baseline_hooke["theory_id"],
        "eval_reports_dir": eval_reports_dir,
        "eval_sealed_dir": eval_sealed_dir,
    }


def _run_sealed_eval(
    *,
    py_toolchain: dict[str, Any],
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
) -> tuple[dict[str, Any], dict[str, Any]]:
    python_exe = str(py_toolchain["python_executable"])
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
            eval_kind,
            "--out_eval",
            str(out_eval),
            "--out_sealed",
            str(out_sealed),
        ]
        if lease is not None:
            cmd.extend(["--lease", str(lease)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=_pythonpath_env(),
        )
        if result.returncode != 0:
            _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

        eval_report = load_canon_json(out_eval)
        sealed = load_canon_json(out_sealed)
        if not isinstance(eval_report, dict) or not isinstance(sealed, dict):
            _fail("INVALID:SCHEMA_FAIL")
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


def _is_better(
    *,
    rmse_q: int,
    work_cost: int,
    theory_id: str,
    best: tuple[int, int, str] | None,
) -> bool:
    key = (int(rmse_q), int(work_cost), str(theory_id))
    if best is None:
        return True
    return key < best


def _trace_row(
    *,
    state_dir: Path,
    seq_u64: int,
    algo_label: str,
    eval_kind: str,
    theory_id: str,
    theory_kind: str,
    norm_pow_p: int,
    report_hash: str,
    work_cost_total: int,
    input_paths: dict[str, Path | None],
) -> dict[str, Any]:
    rels: dict[str, Any] = {}
    for key, path in input_paths.items():
        if path is None:
            rels[key] = None
        else:
            rels[key] = str(path.resolve().relative_to(state_dir.resolve()))
    return {
        "schema_version": "metasearch_eval_trace_v1",
        "invocation_id": "",
        "algo_label": algo_label,
        "seq_u64": int(seq_u64),
        "eval_kind": eval_kind,
        "theory_id": theory_id,
        "theory_kind": theory_kind,
        "norm_pow_p": int(norm_pow_p),
        "eval_report_hash": report_hash,
        "work_cost_total": int(work_cost_total),
        "input_rels": rels,
    }


def _run_baseline_ga(
    *,
    state_dir: Path,
    workspace: dict[str, Any],
    py_toolchain: dict[str, Any],
    baseline_cfg: Any,
    lease_path: Path,
    trace_path: Path,
) -> dict[str, Any]:
    rng = random.Random(int(baseline_cfg.seed_u64))
    best_theory_id = ""
    best_key: tuple[int, int, str] | None = None
    seq = 0

    hypos = enumerate_hypotheses()
    for _ in range(int(baseline_cfg.max_dev_evals)):
        hypothesis = hypos[rng.randrange(len(hypos))]
        theory_id = workspace["hypothesis_to_theory_id"][(hypothesis.theory_kind, hypothesis.norm_pow_p)]
        trow = workspace["theories"][theory_id]

        eval_report, sealed = _run_sealed_eval(
            py_toolchain=py_toolchain,
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
        )
        _, _, report_hash, work_cost = _persist_eval_artifacts(
            eval_report=eval_report,
            sealed_receipt=sealed,
            eval_reports_dir=workspace["eval_reports_dir"],
            eval_sealed_dir=workspace["eval_sealed_dir"],
        )
        rmse_q = parse_q32_obj(eval_report["metrics"]["rmse_pos1_q32"])

        if _is_better(rmse_q=rmse_q, work_cost=work_cost, theory_id=theory_id, best=best_key):
            best_key = (int(rmse_q), int(work_cost), theory_id)
            best_theory_id = theory_id

        row = _trace_row(
            state_dir=state_dir,
            seq_u64=seq,
            algo_label="baseline",
            eval_kind="DEV",
            theory_id=theory_id,
            theory_kind=trow["theory_kind"],
            norm_pow_p=trow["norm_pow_p"],
            report_hash=report_hash,
            work_cost_total=work_cost,
            input_paths={
                "dataset_manifest_rel": workspace["manifest_path"],
                "dataset_csv_rel": workspace["csv_path"],
                "dataset_receipt_rel": workspace["dataset_receipt_path"],
                "split_receipt_rel": workspace["split_receipt_path"],
                "theory_ir_rel": trow["ir_path"],
                "fit_receipt_rel": trow["fit_path"],
                "suitepack_rel": workspace["suite_dev_path"],
                "perf_policy_rel": workspace["perf_policy_path"],
                "ir_policy_rel": workspace["ir_policy_path"],
                "lease_rel": None,
            },
        )
        append_trace_row(trace_path, row)
        seq += 1

    if not best_theory_id:
        _fail("INVALID:SCHEMA_FAIL")

    for theory_id in [best_theory_id, workspace["baseline_const_theory_id"], workspace["baseline_hooke_theory_id"]]:
        trow = workspace["theories"][theory_id]
        eval_report, sealed = _run_sealed_eval(
            py_toolchain=py_toolchain,
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
        )
        _, _, report_hash, work_cost = _persist_eval_artifacts(
            eval_report=eval_report,
            sealed_receipt=sealed,
            eval_reports_dir=workspace["eval_reports_dir"],
            eval_sealed_dir=workspace["eval_sealed_dir"],
        )
        row = _trace_row(
            state_dir=state_dir,
            seq_u64=seq,
            algo_label="baseline",
            eval_kind="HELDOUT",
            theory_id=theory_id,
            theory_kind=trow["theory_kind"],
            norm_pow_p=trow["norm_pow_p"],
            report_hash=report_hash,
            work_cost_total=work_cost,
            input_paths={
                "dataset_manifest_rel": workspace["manifest_path"],
                "dataset_csv_rel": workspace["csv_path"],
                "dataset_receipt_rel": workspace["dataset_receipt_path"],
                "split_receipt_rel": workspace["split_receipt_path"],
                "theory_ir_rel": trow["ir_path"],
                "fit_receipt_rel": trow["fit_path"],
                "suitepack_rel": workspace["suite_heldout_path"],
                "perf_policy_rel": workspace["perf_policy_path"],
                "ir_policy_rel": workspace["ir_policy_path"],
                "lease_rel": lease_path,
            },
        )
        append_trace_row(trace_path, row)
        seq += 1

    return {"selected_theory_id": best_theory_id}


def _run_candidate_trace_prior(
    *,
    state_dir: Path,
    workspace: dict[str, Any],
    py_toolchain: dict[str, Any],
    candidate_cfg: CandidateSearchConfig,
    lease_path: Path,
    trace_path: Path,
    plan: dict[str, Any],
) -> dict[str, Any]:
    best_theory_id = ""
    best_key: tuple[int, int, str] | None = None
    seq = 0

    ranked = list(plan.get("ranked") or [])
    if not ranked:
        _fail("INVALID:SEARCH_PLAN_REPLAY_MISMATCH")

    for entry in ranked[: int(candidate_cfg.max_dev_evals)]:
        kind = str(entry.get("theory_kind"))
        p = int(entry.get("norm_pow_p", 0))
        theory_id = workspace["hypothesis_to_theory_id"].get((kind, p))
        if theory_id is None:
            _fail("INVALID:SEARCH_PLAN_REPLAY_MISMATCH")
        trow = workspace["theories"][theory_id]

        eval_report, sealed = _run_sealed_eval(
            py_toolchain=py_toolchain,
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
        )
        _, _, report_hash, work_cost = _persist_eval_artifacts(
            eval_report=eval_report,
            sealed_receipt=sealed,
            eval_reports_dir=workspace["eval_reports_dir"],
            eval_sealed_dir=workspace["eval_sealed_dir"],
        )
        rmse_q = parse_q32_obj(eval_report["metrics"]["rmse_pos1_q32"])

        if _is_better(rmse_q=rmse_q, work_cost=work_cost, theory_id=theory_id, best=best_key):
            best_key = (int(rmse_q), int(work_cost), theory_id)
            best_theory_id = theory_id

        row = _trace_row(
            state_dir=state_dir,
            seq_u64=seq,
            algo_label="candidate",
            eval_kind="DEV",
            theory_id=theory_id,
            theory_kind=trow["theory_kind"],
            norm_pow_p=trow["norm_pow_p"],
            report_hash=report_hash,
            work_cost_total=work_cost,
            input_paths={
                "dataset_manifest_rel": workspace["manifest_path"],
                "dataset_csv_rel": workspace["csv_path"],
                "dataset_receipt_rel": workspace["dataset_receipt_path"],
                "split_receipt_rel": workspace["split_receipt_path"],
                "theory_ir_rel": trow["ir_path"],
                "fit_receipt_rel": trow["fit_path"],
                "suitepack_rel": workspace["suite_dev_path"],
                "perf_policy_rel": workspace["perf_policy_path"],
                "ir_policy_rel": workspace["ir_policy_path"],
                "lease_rel": None,
            },
        )
        append_trace_row(trace_path, row)
        seq += 1

    if not best_theory_id:
        _fail("INVALID:SEARCH_PLAN_REPLAY_MISMATCH")

    for theory_id in [best_theory_id, workspace["baseline_const_theory_id"], workspace["baseline_hooke_theory_id"]]:
        trow = workspace["theories"][theory_id]
        eval_report, sealed = _run_sealed_eval(
            py_toolchain=py_toolchain,
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
        )
        _, _, report_hash, work_cost = _persist_eval_artifacts(
            eval_report=eval_report,
            sealed_receipt=sealed,
            eval_reports_dir=workspace["eval_reports_dir"],
            eval_sealed_dir=workspace["eval_sealed_dir"],
        )
        row = _trace_row(
            state_dir=state_dir,
            seq_u64=seq,
            algo_label="candidate",
            eval_kind="HELDOUT",
            theory_id=theory_id,
            theory_kind=trow["theory_kind"],
            norm_pow_p=trow["norm_pow_p"],
            report_hash=report_hash,
            work_cost_total=work_cost,
            input_paths={
                "dataset_manifest_rel": workspace["manifest_path"],
                "dataset_csv_rel": workspace["csv_path"],
                "dataset_receipt_rel": workspace["dataset_receipt_path"],
                "split_receipt_rel": workspace["split_receipt_path"],
                "theory_ir_rel": trow["ir_path"],
                "fit_receipt_rel": trow["fit_path"],
                "suitepack_rel": workspace["suite_heldout_path"],
                "perf_policy_rel": workspace["perf_policy_path"],
                "ir_policy_rel": workspace["ir_policy_path"],
                "lease_rel": lease_path,
            },
        )
        append_trace_row(trace_path, row)
        seq += 1

    return {"selected_theory_id": best_theory_id}


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


def _run_v13_science(*, dataset_manifest: Path, dataset_csv: Path, out_root: Path, python_exe: str) -> None:
    if out_root.exists():
        shutil.rmtree(out_root)
    control_dir = out_root / "state" / "control"
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "ENABLE_RESEARCH").write_text("enable\n", encoding="utf-8")
    (control_dir / "ENABLE_SAS_SCIENCE").write_text("enable\n", encoding="utf-8")
    write_canon_json(control_dir / "SAS_SCIENCE_LEASE.json", {"lease_id": "v16"})

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
    promo_dir = run_root / "state" / "promotion"
    promos = sorted(promo_dir.glob("sha256_*.sas_science_promotion_bundle_v1.json"))
    if len(promos) != 1:
        _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
    promo = load_canon_json(promos[0])
    if not isinstance(promo, dict):
        _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
    discovery = promo.get("discovery_bundle")
    if not isinstance(discovery, dict):
        _fail("INVALID:DOWNSTREAM_V13_VERIFIER_FAIL")
    return str(discovery.get("theory_id")), str(discovery.get("law_kind"))


def run_sas_metasearch(
    *,
    campaign_pack: Path,
    out_dir: Path,
    campaign_tag: str = "rsi_sas_metasearch_v16_0",
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
        state_dir / "eval_trace",
        state_dir / "science_runs",
        state_dir / "reports",
        state_dir / "promotion",
        state_dir / "ledger",
    ]:
        path.mkdir(parents=True, exist_ok=True)

    pack = load_canon_json(pack_path)
    if not isinstance(pack, dict) or pack.get("schema_version") != "rsi_sas_metasearch_pack_v1":
        _fail("INVALID:SCHEMA_FAIL")

    # Freeze config.
    _copy_json(pack_path, config_dir / "rsi_sas_metasearch_pack_v1.json")
    for key, dst_name in [
        ("policy_rel", "sas_metasearch_policy_v1.json"),
        ("baseline_search_config_rel", "baseline_search_config_v1.json"),
        ("candidate_search_config_rel", "candidate_search_config_v1.json"),
    ]:
        src = _resolve_path(pack_path.parent, str(pack[key]))
        _copy_json(src, config_dir / dst_name)

    for key, dst_name in [
        ("gravity_dataset_manifest_rel", "gravity_dataset_manifest_v1.json"),
        ("hooke_dataset_manifest_rel", "hooke_dataset_manifest_v1.json"),
    ]:
        src = _resolve_path(pack_path.parent, str(pack[key]))
        _copy_json(src, config_dir / "datasets" / dst_name)
    for key, dst_name in [
        ("gravity_dataset_rel", "gravity_dataset.csv"),
        ("hooke_dataset_rel", "hooke_dataset.csv"),
    ]:
        src = _resolve_path(pack_path.parent, str(pack[key]))
        _copy_csv(src, config_dir / "datasets" / dst_name)

    trace_src = _resolve_path(pack_path.parent, str(pack["trace_corpus_rel"]))
    _copy_json(trace_src, config_dir / "trace_corpus" / "science_trace_corpus_suitepack_dev_v1.json")

    # Freeze toolchain manifests, preferring campaign-local copies.
    source_daemon_cfg = _repo_root() / "daemon" / campaign_tag / "config"
    for name in ["toolchain_manifest_py_v1.json", "toolchain_manifest_rust_v1.json"]:
        src = pack_path.parent / name
        if not src.exists():
            src = source_daemon_cfg / name
        if not src.exists():
            _fail("INVALID:TOOLCHAIN_MANIFEST")
        _copy_json(src, config_dir / name)

    policy = load_policy(config_dir / "sas_metasearch_policy_v1.json")
    baseline_cfg = load_baseline_search_config(config_dir / "baseline_search_config_v1.json")
    candidate_cfg = load_candidate_search_config(config_dir / "candidate_search_config_v1.json")
    py_toolchain = load_py_toolchain_manifest(config_dir / "toolchain_manifest_py_v1.json")
    rust_toolchain = load_rust_toolchain_manifest(config_dir / "toolchain_manifest_rust_v1.json")

    # Control flags.
    control = state_dir / "control"
    (control / "ENABLE_RESEARCH").write_text("enable\n", encoding="utf-8")
    (control / "ENABLE_SAS_METASEARCH").write_text("enable\n", encoding="utf-8")
    lease_path = control / "SAS_METASEARCH_LEASE.json"
    write_canon_json(lease_path, {"lease_id": "v16"})

    ledger_path = state_dir / "ledger" / "metasearch_ledger_v1.jsonl"
    tick = 0
    _append_ledger(ledger_path, "METASEARCH_BOOT", {}, tick)
    tick += 1

    # Corpus -> prior.
    corpus = load_suitepack(config_dir / "trace_corpus" / "science_trace_corpus_suitepack_dev_v1.json", min_cases=min_corpus_cases)
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

    # Rust synthesis + build + plan.
    crate = materialize_rust_crate(prior=prior, k_max_dev_evals=candidate_cfg.max_dev_evals)
    scan_rust_sources(crate / "src", forbidden_tokens=list(policy.get("forbidden_rust_tokens") or []))
    binary_path = build_release_binary(crate_dir=crate, rust_toolchain=rust_toolchain)
    binary_hash = file_hash(binary_path)

    tmp_plan = state_dir / "plan" / "metasearch_plan_raw_v1.json"
    plan = run_planner(binary_path=binary_path, prior_path=prior_path, out_plan_path=tmp_plan)
    plan_path, plan_hash = _write_hashed_json(state_dir / "plan", "metasearch_plan_v1.json", plan)
    if tmp_plan.exists():
        tmp_plan.unlink()
    _append_ledger(ledger_path, "METASEARCH_PLAN_READY", {"plan_hash": plan_hash, "binary_hash": binary_hash}, tick)
    tick += 1

    # Search traces.
    workspace = _prepare_eval_workspace(
        state_dir=state_dir,
        config_dir=config_dir,
        dataset_manifest_path=config_dir / "datasets" / "gravity_dataset_manifest_v1.json",
        dataset_csv_path=config_dir / "datasets" / "gravity_dataset.csv",
    )

    baseline_trace = state_dir / "eval_trace" / "baseline.metasearch_eval_trace_v1.jsonl"
    candidate_trace = state_dir / "eval_trace" / "candidate.metasearch_eval_trace_v1.jsonl"

    baseline_result = _run_baseline_ga(
        state_dir=state_dir,
        workspace=workspace,
        py_toolchain=py_toolchain,
        baseline_cfg=baseline_cfg,
        lease_path=lease_path,
        trace_path=baseline_trace,
    )
    candidate_result = _run_candidate_trace_prior(
        state_dir=state_dir,
        workspace=workspace,
        py_toolchain=py_toolchain,
        candidate_cfg=candidate_cfg,
        lease_path=lease_path,
        trace_path=candidate_trace,
        plan=plan,
    )

    c_base = _sum_work_cost(baseline_trace)
    c_cand = _sum_work_cost(candidate_trace)
    gate_pass = c_cand * 2 <= c_base
    compute = {
        "schema_version": "metasearch_compute_report_v1",
        "report_id": "",
        "baseline_eval_trace_hash": trace_file_hash(baseline_trace),
        "candidate_eval_trace_hash": trace_file_hash(candidate_trace),
        "c_base_work_cost_total": int(c_base),
        "c_cand_work_cost_total": int(c_cand),
        "efficiency_gate_pass": bool(gate_pass),
    }
    compute["report_id"] = sha256_prefixed(canon_bytes({k: v for k, v in compute.items() if k != "report_id"}))
    compute_path, compute_hash = _write_hashed_json(state_dir / "reports", "metasearch_compute_report_v1.json", compute)
    _append_ledger(ledger_path, "METASEARCH_COMPUTE_READY", {"compute_hash": compute_hash}, tick)
    tick += 1

    # Full v13 run roots for correctness + foil gate.
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

    cand_theory_id, cand_law_kind = _selected_from_v13_run(candidate_science)
    _, foil_law_kind = _selected_from_v13_run(foil_science)

    # Promotion bundle.
    pack_frozen = load_canon_json(config_dir / "rsi_sas_metasearch_pack_v1.json")
    promotion = {
        "schema_version": "sas_metasearch_promotion_bundle_v1",
        "bundle_id": "",
        "created_utc": _now_utc(),
        "pack_hash": sha256_prefixed(canon_bytes(pack_frozen)),
        "policy_hash": sha256_prefixed(canon_bytes(load_canon_json(config_dir / "sas_metasearch_policy_v1.json"))),
        "baseline_search_config_hash": sha256_prefixed(
            canon_bytes(load_canon_json(config_dir / "baseline_search_config_v1.json"))
        ),
        "candidate_search_config_hash": sha256_prefixed(
            canon_bytes(load_canon_json(config_dir / "candidate_search_config_v1.json"))
        ),
        "trace_corpus_hash": corpus_hash,
        "prior_hash": prior_hash,
        "plan_hash": plan_hash,
        "compute_report_hash": compute_hash,
        "selected_theory_id": cand_theory_id,
        "selected_law_kind": cand_law_kind,
        "acceptance_decision": {
            "pass": bool(
                gate_pass
                and cand_law_kind in ("NEWTON_CENTRAL_V1", "NEWTON_NBODY_V1")
                and foil_law_kind not in ("NEWTON_CENTRAL_V1", "NEWTON_NBODY_V1")
            ),
            "reasons": [
                reason
                for reason, cond in [
                    ("COGNITIVE_EFFICIENCY_GATE_FAIL", not gate_pass),
                    ("LAW_NOT_NEWTONIAN", cand_law_kind not in ("NEWTON_CENTRAL_V1", "NEWTON_NBODY_V1")),
                    ("NEWTON_ALWAYS_OUTPUT", foil_law_kind in ("NEWTON_CENTRAL_V1", "NEWTON_NBODY_V1")),
                ]
                if cond
            ],
        },
    }
    promotion["bundle_id"] = sha256_prefixed(canon_bytes({k: v for k, v in promotion.items() if k != "bundle_id"}))
    promotion_path, promotion_hash = _write_hashed_json(
        state_dir / "promotion",
        "sas_metasearch_promotion_bundle_v1.json",
        promotion,
    )
    _append_ledger(ledger_path, "METASEARCH_PROMOTION_WRITTEN", {"promotion_hash": promotion_hash}, tick)

    return {
        "status": "OK",
        "state_dir": str(state_dir),
        "promotion_bundle": str(promotion_path),
        "plan_hash": plan_hash,
        "compute_report_hash": compute_hash,
        "baseline_selected_theory_id": baseline_result["selected_theory_id"],
        "candidate_selected_theory_id": candidate_result["selected_theory_id"],
        "candidate_law_kind": cand_law_kind,
        "foil_law_kind": foil_law_kind,
    }


__all__ = ["run_sas_metasearch", "MetaSearchRunError"]
