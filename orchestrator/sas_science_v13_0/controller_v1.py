"""SAS-Science controller (v13.0)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v13_0.sas_science_dataset_v1 import (
    load_manifest,
    load_dataset,
    compute_dataset_receipt,
    compute_split_receipt,
)
from cdel.v13_0.sas_science_ir_v1 import compute_theory_id, compute_complexity, validate_ir
from cdel.v13_0.sas_science_generator_v1 import enumerate_candidate_irs, build_candidate_bundle, build_gen_receipt
from cdel.v13_0.sas_science_fit_v1 import fit_theory
from cdel.v13_0.sas_science_eval_v1 import compute_report_hash
from cdel.v13_0.sas_science_selection_v1 import select_candidate, build_selection_receipt
from cdel.v13_0.sas_science_canon_v1 import canonicalize_law
from cdel.v13_0.sas_science_math_v1 import parse_q32_obj

from .ledger_writer_v1 import SASScienceLedgerWriter
from .root_manifest_writer_v1 import write_root_manifest


class SASScienceError(RuntimeError):
    pass


def _now_utc() -> str:
    # Deterministic timestamp to keep content-addressed artifacts stable.
    return "1970-01-01T00:00:00Z"


def _copy_config(src: Path, dst: Path) -> None:
    payload = load_canon_json(src)
    write_canon_json(dst, payload)


def _resolve_pack_path(pack_path: Path, rel: str) -> Path:
    rel_path = Path(str(rel))
    if rel_path.is_absolute():
        return rel_path
    return pack_path.parent / rel_path


def _canon_for_run(run_root: Path) -> dict[str, Any]:
    agi_root_raw = os.environ.get("AGI_ROOT", "")
    agi_root_stripped = agi_root_raw.strip()
    agi_root_canon = ""
    if agi_root_stripped:
        try:
            agi_root_canon = str(Path(agi_root_stripped).expanduser().resolve(strict=True)).rstrip("/")
        except Exception:
            agi_root_canon = agi_root_stripped
    return {
        "agi_root_raw": agi_root_raw,
        "agi_root_stripped": agi_root_stripped,
        "agi_root_canon": agi_root_canon,
        "was_trimmed": agi_root_raw != agi_root_stripped,
        "sas_root_canon": str(run_root.resolve()),
        "canon_method": "CANON_ROOT_V1_OVERRIDE",
    }


def _find_cdel_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "CDEL-v2"
        if candidate.exists():
            return candidate
    return here.parents[2] / "CDEL-v2"


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


def _write_ir(ir_dir: Path, ir: dict[str, Any]) -> Path:
    ir_dir.mkdir(parents=True, exist_ok=True)
    path = ir_dir / f"sha256_{ir['theory_id'].split(':',1)[1]}.sas_science_theory_ir_v1.json"
    write_canon_json(path, ir)
    return path


def _write_receipt(dir_path: Path, receipt: dict[str, Any], suffix: str) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    receipt_hash = sha256_prefixed(canon_bytes(receipt))
    path = dir_path / f"sha256_{receipt_hash.split(':',1)[1]}.{suffix}"
    write_canon_json(path, receipt)
    return path


def _run_sealed_eval(
    *,
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
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        out_eval = tmpdir / "eval.json"
        out_sealed = tmpdir / "sealed.json"
        cmd = [
            "python3",
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
        env = dict(os.environ)
        cdel_root = _find_cdel_root()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(cdel_root) + (os.pathsep + existing if existing else "")
        subprocess.check_call(cmd, env=env)
        eval_report = load_canon_json(out_eval)
        sealed = load_canon_json(out_sealed)
        return eval_report, sealed


def run_sas_science(
    *,
    dataset_csv: Path,
    dataset_manifest: Path,
    campaign_pack: Path,
    state_dir: Path,
    campaign_tag: str = "rsi_sas_science_v13_0",
    max_theories: int | None = None,
) -> dict[str, Any]:
    run_root = state_dir.resolve()
    config_dir = run_root / "config"
    state_path = run_root / "state"

    # core dirs
    control_dir = state_path / "control"
    ledger_dir = state_path / "ledger"
    data_dir = state_path / "data"
    theory_dir = state_path / "theory" / "ir"
    bundle_dir = state_path / "candidates" / "bundles"
    gen_receipts_dir = state_path / "candidates" / "receipts"
    fit_dir = state_path / "fit" / "receipts"
    eval_dir = state_path / "eval" / "reports"
    sealed_dir = state_path / "eval" / "sealed"
    selection_dir = state_path / "selection"
    promotion_dir = state_path / "promotion"
    dumps_dir = run_root / "dumps"

    for d in [config_dir, control_dir, ledger_dir, data_dir, theory_dir, bundle_dir, gen_receipts_dir, fit_dir, eval_dir, sealed_dir, selection_dir, promotion_dir, dumps_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Load pack
    pack = load_canon_json(campaign_pack)
    if not isinstance(pack, dict) or pack.get("schema_version") != "rsi_sas_science_pack_v1":
        raise SASScienceError("SAS_SCIENCE_PACK_INVALID")

    # Copy config artifacts
    write_canon_json(config_dir / "rsi_sas_science_pack_v1.json", pack)
    def _p(name: str) -> Path:
        return _resolve_pack_path(campaign_pack, str(pack.get(name)))

    perf_policy_path = _p("perf_policy_path")
    ir_policy_path = _p("ir_policy_path")
    suite_dev_path = _p("suitepack_path_dev")
    suite_held_path = _p("suitepack_path_heldout")
    baseline_const_path = _p("baseline_const_path")
    baseline_hooke_path = _p("baseline_hooke_path")

    _copy_config(perf_policy_path, config_dir / "sas_science_perf_policy_v1.json")
    _copy_config(ir_policy_path, config_dir / "sas_science_ir_policy_v1.json")
    _copy_config(suite_dev_path, config_dir / "sas_science_suitepack_dev_v1.json")
    _copy_config(suite_held_path, config_dir / "sas_science_suitepack_heldout_v1.json")
    _copy_config(baseline_const_path, config_dir / "baseline_constant_velocity_v1.sas_science_theory_ir_v1.json")
    _copy_config(baseline_hooke_path, config_dir / "baseline_hooke_central_v1.sas_science_theory_ir_v1.json")

    # Require enable flags + lease
    for name in ["ENABLE_RESEARCH", "ENABLE_SAS_SCIENCE", "SAS_SCIENCE_LEASE.json"]:
        if not (control_dir / name).exists():
            raise SASScienceError("SAS_SCIENCE_LOCKED_MISSING_KEYS")

    # Root manifest
    canon = _canon_for_run(run_root)
    write_root_manifest(state_path, canon)

    ledger = SASScienceLedgerWriter(ledger_dir / "sas_science_synthesis_ledger_v1.jsonl")
    tick = 0
    ledger.append(event_type="SAS_SCIENCE_BOOT", event_payload={}, tick=tick)
    tick += 1
    ledger.append(event_type="SAS_SCIENCE_ROOT_MANIFEST_WRITTEN", event_payload={}, tick=tick)

    # Dataset ingest
    manifest = load_manifest(dataset_manifest)
    csv_bytes = dataset_csv.read_bytes()

    data_dir_manifest = data_dir / "manifest"
    data_dir_csv = data_dir / "csv"
    data_dir_receipts = data_dir / "receipts"
    data_dir_manifest.mkdir(parents=True, exist_ok=True)
    data_dir_csv.mkdir(parents=True, exist_ok=True)
    data_dir_receipts.mkdir(parents=True, exist_ok=True)

    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    manifest_path = data_dir_manifest / f"sha256_{manifest_hash.split(':',1)[1]}.sas_science_dataset_manifest_v1.json"
    write_canon_json(manifest_path, manifest)

    csv_hash = sha256_prefixed(csv_bytes)
    csv_path = data_dir_csv / f"sha256_{csv_hash.split(':',1)[1]}.dataset.csv"
    csv_path.write_bytes(csv_bytes)

    dataset_obj = load_dataset(csv_path, manifest)
    dataset_receipt = compute_dataset_receipt(manifest=manifest, csv_bytes=csv_bytes, row_count=len(dataset_obj.times_q32))
    dataset_receipt_path = data_dir_receipts / f"sha256_{dataset_receipt['dataset_id'].split(':',1)[1]}.sas_science_dataset_receipt_v1.json"
    write_canon_json(dataset_receipt_path, dataset_receipt)

    split_receipt = compute_split_receipt(
        manifest=manifest,
        dataset_id=dataset_receipt["dataset_id"],
        row_count=dataset_receipt["row_count"],
    )
    split_receipt_path = data_dir_receipts / f"sha256_{split_receipt['split_id'].split(':',1)[1]}.sas_science_split_receipt_v1.json"
    write_canon_json(split_receipt_path, split_receipt)

    ledger.append(event_type="SAS_SCIENCE_DATASET_RECEIPT", event_payload={"dataset_id": dataset_receipt["dataset_id"]}, tick=tick)
    tick += 1
    ledger.append(event_type="SAS_SCIENCE_SPLIT_RECEIPT", event_payload={"split_id": split_receipt["split_id"]}, tick=tick)
    tick += 1

    # Baseline IRs
    baseline_const_template = load_canon_json(config_dir / "baseline_constant_velocity_v1.sas_science_theory_ir_v1.json")
    baseline_hooke_template = load_canon_json(config_dir / "baseline_hooke_central_v1.sas_science_theory_ir_v1.json")
    baseline_const_ir = _instantiate_baseline(baseline_const_template, manifest, central=True)
    baseline_hooke_ir = _instantiate_baseline(baseline_hooke_template, manifest, central=True)
    validate_ir(baseline_const_ir, manifest=manifest, ir_policy=load_canon_json(config_dir / "sas_science_ir_policy_v1.json"))
    validate_ir(baseline_hooke_ir, manifest=manifest, ir_policy=load_canon_json(config_dir / "sas_science_ir_policy_v1.json"))

    _write_ir(theory_dir, baseline_const_ir)
    _write_ir(theory_dir, baseline_hooke_ir)

    ledger.append(
        event_type="SAS_SCIENCE_BASELINES_READY",
        event_payload={"baseline_ids": [baseline_const_ir["theory_id"], baseline_hooke_ir["theory_id"]]},
        tick=tick,
    )
    tick += 1

    # Candidates
    candidate_irs = enumerate_candidate_irs(manifest)
    if max_theories is not None:
        if int(max_theories) < 1 or int(max_theories) > 100000:
            raise SASScienceError("INVALID:V13_MAX_THEORIES")
        candidate_irs = candidate_irs[: int(max_theories)]
        if not candidate_irs:
            raise SASScienceError("INVALID:V13_MAX_THEORIES")
    for ir in candidate_irs:
        _write_ir(theory_dir, ir)

    gen_seed = sha256_prefixed(b"sas_science_generator_v1")
    gen_cfg_hash = sha256_prefixed(b"sas_science_generator_v1")
    bundle = build_candidate_bundle(candidate_irs=candidate_irs, generator_seed=gen_seed, generator_config_hash=gen_cfg_hash)
    bundle_path = bundle_dir / f"sha256_{bundle['bundle_id'].split(':',1)[1]}.sas_science_candidate_bundle_v1.json"
    write_canon_json(bundle_path, bundle)
    gen_receipt = build_gen_receipt(
        bundle_id=bundle["bundle_id"],
        generator_seed=gen_seed,
        generator_config_hash=gen_cfg_hash,
        stdout_hash=sha256_prefixed(b""),
        stderr_hash=sha256_prefixed(b""),
    )
    gen_receipt_path = gen_receipts_dir / f"sha256_{gen_receipt['receipt_id'].split(':',1)[1]}.sas_science_gen_receipt_v1.json"
    write_canon_json(gen_receipt_path, gen_receipt)

    ledger.append(event_type="SAS_SCIENCE_CANDIDATE_BUNDLE_WRITTEN", event_payload={"bundle_id": bundle["bundle_id"]}, tick=tick)
    tick += 1

    # Fit
    ir_policy = load_canon_json(config_dir / "sas_science_ir_policy_v1.json")
    all_irs = [baseline_const_ir, baseline_hooke_ir] + candidate_irs
    fit_receipts: dict[str, dict[str, Any]] = {}
    for ir in all_irs:
        fit = fit_theory(dataset=dataset_obj, ir=ir, split_receipt=split_receipt, ir_policy=ir_policy)
        fit_path = fit_dir / f"sha256_{fit['receipt_id'].split(':',1)[1]}.sas_science_fit_receipt_v1.json"
        write_canon_json(fit_path, fit)
        fit_receipts[ir["theory_id"]] = fit

    ledger.append(event_type="SAS_SCIENCE_FIT_DONE", event_payload={"count": len(all_irs)}, tick=tick)
    tick += 1

    # Eval (sealed)
    perf_policy_path = config_dir / "sas_science_perf_policy_v1.json"
    ir_policy_path = config_dir / "sas_science_ir_policy_v1.json"
    suite_dev = config_dir / "sas_science_suitepack_dev_v1.json"
    suite_held = config_dir / "sas_science_suitepack_heldout_v1.json"
    lease_path = control_dir / "SAS_SCIENCE_LEASE.json"

    eval_reports: dict[tuple[str, str], dict[str, Any]] = {}
    eval_hashes: dict[tuple[str, str], str] = {}
    sealed_hashes: dict[tuple[str, str], str] = {}

    for ir in all_irs:
        ir_path = theory_dir / f"sha256_{ir['theory_id'].split(':',1)[1]}.sas_science_theory_ir_v1.json"
        fit_path = fit_dir / f"sha256_{fit_receipts[ir['theory_id']]['receipt_id'].split(':',1)[1]}.sas_science_fit_receipt_v1.json"
        for eval_kind, suite in [("DEV", suite_dev), ("HELDOUT", suite_held)]:
            eval_report, sealed = _run_sealed_eval(
                dataset_manifest=manifest_path,
                dataset_csv=csv_path,
                dataset_receipt=dataset_receipt_path,
                split_receipt=split_receipt_path,
                theory_ir=ir_path,
                fit_receipt=fit_path,
                suitepack=suite,
                perf_policy=perf_policy_path,
                ir_policy=ir_policy_path,
                eval_kind=eval_kind,
                lease=lease_path if eval_kind == "HELDOUT" else None,
            )
            report_hash = compute_report_hash(eval_report)
            report_path = eval_dir / f"sha256_{report_hash.split(':',1)[1]}.sas_science_eval_report_v1.json"
            write_canon_json(report_path, eval_report)
            sealed_hash = sha256_prefixed(canon_bytes(sealed))
            sealed_path = sealed_dir / f"sha256_{sealed_hash.split(':',1)[1]}.sealed_science_eval_receipt_v1.json"
            write_canon_json(sealed_path, sealed)
            eval_reports[(ir["theory_id"], eval_kind)] = eval_report
            eval_hashes[(ir["theory_id"], eval_kind)] = report_hash
            sealed_hashes[(ir["theory_id"], eval_kind)] = sealed_hash

    ledger.append(event_type="SAS_SCIENCE_EVAL_DEV_DONE", event_payload={}, tick=tick)
    tick += 1
    ledger.append(event_type="SAS_SCIENCE_EVAL_HELDOUT_DONE", event_payload={}, tick=tick)
    tick += 1

    # Selection + gates
    candidate_ids = [ir["theory_id"] for ir in candidate_irs]
    held_reports = {cid: eval_reports[(cid, "HELDOUT")] for cid in candidate_ids}
    selected_id, mdl_q = select_candidate(
        candidate_ids=candidate_ids,
        eval_reports=held_reports,
        irs={ir["theory_id"]: ir for ir in all_irs},
        lambda_q32_obj=load_canon_json(config_dir / "sas_science_perf_policy_v1.json").get("mdl_lambda_q32"),
    )

    def _metric(report: dict[str, Any], key: str) -> int:
        return parse_q32_obj(report.get("metrics", {}).get(key))

    def _work(report: dict[str, Any]) -> int:
        return int(report.get("workmeter", {}).get("work_cost_total", 0))

    base_reports_held = [eval_reports[(baseline_const_ir["theory_id"], "HELDOUT")], eval_reports[(baseline_hooke_ir["theory_id"], "HELDOUT")]]
    base_mse = min(_metric(r, "mse_accel_q32") for r in base_reports_held)
    base_rmse = min(_metric(r, "rmse_pos1_q32") for r in base_reports_held)
    base_roll64 = min(_metric(r, "rmse_roll_64_q32") for r in base_reports_held)
    base_roll128 = min(_metric(r, "rmse_roll_128_q32") for r in base_reports_held)
    base_roll256 = min(_metric(r, "rmse_roll_256_q32") for r in base_reports_held)
    base_work = max(_work(r) for r in base_reports_held)

    cand_report = eval_reports[(selected_id, "HELDOUT")]
    cand_mse = _metric(cand_report, "mse_accel_q32")
    cand_rmse = _metric(cand_report, "rmse_pos1_q32")
    cand_roll64 = _metric(cand_report, "rmse_roll_64_q32")
    cand_roll128 = _metric(cand_report, "rmse_roll_128_q32")
    cand_roll256 = _metric(cand_report, "rmse_roll_256_q32")
    cand_work = _work(cand_report)

    reasons: list[str] = []
    if cand_mse * 100 > base_mse * 5:
        reasons.append("PERF_MSE_ACCEL")
    if cand_rmse * 100 > base_rmse * 10:
        reasons.append("PERF_RMSE_POS1")
    if not (cand_roll64 <= cand_roll128 <= cand_roll256 * 2):
        reasons.append("PERF_ROLLOUT")
    if cand_work * 100 > base_work * 500:
        reasons.append("WORK_BUDGET")

    selection_pass = len(reasons) == 0

    selection_receipt = build_selection_receipt(
        selected_id=selected_id,
        candidate_ids=candidate_ids,
        mdl_total_q=mdl_q,
        selection_pass=selection_pass,
        reasons=reasons,
    )
    selection_path = selection_dir / f"sha256_{selection_receipt['receipt_id'].split(':',1)[1]}.sas_science_selection_receipt_v1.json"
    write_canon_json(selection_path, selection_receipt)

    ledger.append(event_type="SAS_SCIENCE_SELECTION_DONE", event_payload={"selected_theory_id": selected_id}, tick=tick)
    tick += 1

    # Promotion bundle
    ir_policy_loaded = load_canon_json(config_dir / "sas_science_ir_policy_v1.json")
    canon = canonicalize_law(ir={ir["theory_id"]: ir for ir in all_irs}[selected_id], fit_receipt=fit_receipts[selected_id], ir_policy=ir_policy_loaded)

    discovery_bundle = {
        "law_kind": canon.get("law_kind"),
        "theory_id": selected_id,
        "params": canon.get("params"),
        "heldout_metrics": {
            "mse_accel_q32": cand_report["metrics"]["mse_accel_q32"],
            "rmse_pos1_q32": cand_report["metrics"]["rmse_pos1_q32"],
            "rmse_roll_64_q32": cand_report["metrics"]["rmse_roll_64_q32"],
            "rmse_roll_128_q32": cand_report["metrics"]["rmse_roll_128_q32"],
            "rmse_roll_256_q32": cand_report["metrics"]["rmse_roll_256_q32"],
            "work_cost_total": cand_report["workmeter"]["work_cost_total"],
        },
    }

    perf_policy_hash = sha256_prefixed(canon_bytes(load_canon_json(config_dir / "sas_science_perf_policy_v1.json")))
    ir_policy_hash = sha256_prefixed(canon_bytes(load_canon_json(config_dir / "sas_science_ir_policy_v1.json")))
    suite_dev_hash = sha256_prefixed(canon_bytes(load_canon_json(config_dir / "sas_science_suitepack_dev_v1.json")))
    suite_held_hash = sha256_prefixed(canon_bytes(load_canon_json(config_dir / "sas_science_suitepack_heldout_v1.json")))
    pack_hash = sha256_prefixed(canon_bytes(load_canon_json(config_dir / "rsi_sas_science_pack_v1.json")))

    baseline_refs = []
    for ir in [baseline_const_ir, baseline_hooke_ir]:
        tid = ir["theory_id"]
        baseline_refs.append(
            {
                "theory_id": tid,
                "fit_receipt_hash": fit_receipts[tid]["receipt_id"],
                "eval_report_dev_hash": eval_hashes[(tid, "DEV")],
                "eval_report_heldout_hash": eval_hashes[(tid, "HELDOUT")],
                "sealed_eval_dev_hash": sealed_hashes[(tid, "DEV")],
                "sealed_eval_heldout_hash": sealed_hashes[(tid, "HELDOUT")],
            }
        )

    candidate_refs = []
    for ir in candidate_irs:
        tid = ir["theory_id"]
        candidate_refs.append(
            {
                "theory_id": tid,
                "fit_receipt_hash": fit_receipts[tid]["receipt_id"],
                "eval_report_dev_hash": eval_hashes[(tid, "DEV")],
                "eval_report_heldout_hash": eval_hashes[(tid, "HELDOUT")],
                "sealed_eval_dev_hash": sealed_hashes[(tid, "DEV")],
                "sealed_eval_heldout_hash": sealed_hashes[(tid, "HELDOUT")],
            }
        )

    audit_rel = Path("dumps") / "rsi_sas_science_v13_0_audit_evidence.md"
    audit_path = run_root / audit_rel
    _write_audit_evidence(audit_path, run_root, discovery_bundle, dataset_receipt, split_receipt)

    promo = {
        "schema_version": "sas_science_promotion_bundle_v1",
        "bundle_id": "",
        "created_utc": _now_utc(),
        "pack_hash": pack_hash,
        "perf_policy_hash": perf_policy_hash,
        "ir_policy_hash": ir_policy_hash,
        "suitepack_dev_hash": suite_dev_hash,
        "suitepack_heldout_hash": suite_held_hash,
        "dataset_receipt_hash": dataset_receipt["dataset_id"],
        "split_receipt_hash": split_receipt["split_id"],
        "baseline_evals": baseline_refs,
        "candidate_evals": candidate_refs,
        "selection_receipt_hash": selection_receipt["receipt_id"],
        "discovery_bundle": discovery_bundle,
        "acceptance_decision": {"pass": selection_pass and discovery_bundle["law_kind"] in ("NEWTON_NBODY_V1", "NEWTON_CENTRAL_V1"), "reasons": reasons},
        "audit_evidence_path": str(audit_rel),
    }
    promo["bundle_id"] = sha256_prefixed(canon_bytes({k: v for k, v in promo.items() if k != "bundle_id"}))
    promo_path = promotion_dir / f"sha256_{promo['bundle_id'].split(':',1)[1]}.sas_science_promotion_bundle_v1.json"
    write_canon_json(promo_path, promo)

    ledger.append(event_type="SAS_SCIENCE_PROMOTION_WRITTEN", event_payload={"promotion_bundle_path": str(promo_path)}, tick=tick)
    tick += 1
    ledger.append(event_type="SAS_SCIENCE_SHUTDOWN", event_payload={}, tick=tick)

    return {
        "state_dir": str(state_path),
        "promotion_bundle": str(promo_path),
        "selected_theory_id": selected_id,
        "law_kind": discovery_bundle["law_kind"],
    }


def _write_audit_evidence(path: Path, run_root: Path, discovery_bundle: dict[str, Any], dataset_receipt: dict[str, Any], split_receipt: dict[str, Any]) -> None:
    lines = [
        "# rsi_sas_science_v13_0 Audit Evidence",
        "",
        f"Generated: {_now_utc()}",
        "",
        f"Run root: {run_root}",
        "",
        "---",
        "",
        "## Dataset Receipt",
        "",
        "```json",
        json_dumps(dataset_receipt),
        "```",
        "",
        "## Split Receipt",
        "",
        "```json",
        json_dumps(split_receipt),
        "```",
        "",
        "## Discovery Bundle",
        "",
        "```json",
        json_dumps(discovery_bundle),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def json_dumps(payload: dict[str, Any]) -> str:
    import json
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


__all__ = ["run_sas_science", "SASScienceError"]
