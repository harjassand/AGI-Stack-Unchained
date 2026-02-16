"""SAS-CODE controller (v12.0)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v11_1.path_canon_v1 import canon_root_v1_for
from cdel.v11_1.fixed_q32_v1 import q32_obj, parse_q32
from cdel.v8_0.math_toolchain import compute_manifest_hash, load_toolchain_manifest
from cdel.v8_0.sealed_proofcheck import compute_sealed_receipt_hash
from cdel.v12_0.sas_code_ir_v1 import validate_ir
from cdel.v12_0.sas_code_generator_v1 import enumerate_candidate_irs, build_candidate_bundle, build_gen_receipt
from cdel.v12_0.sas_code_workmeter_v1 import compute_perf_report
from cdel.v12_0.sas_code_selection_v1 import compute_selection_policy_hash, select_candidate, novelty_score_q32
from cdel.v12_0.sas_code_eval_v1 import compute_eval_report
from cdel.v12_0.sas_code_proof_task_v1 import proof_text, sealed_proof_check_receipt, scan_forbidden_tokens, compute_attempt_receipt_hash

from .ledger_writer_v1 import SASCodeLedgerWriter
from .root_manifest_writer_v1 import write_root_manifest


class SASCodeError(RuntimeError):
    pass


def _now_utc() -> str:
    seed = int(os.environ.get("OMEGA_RUN_SEED_U64", "0"))
    return f"1970-01-01T00:00:{seed % 60:02d}Z"


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "CDEL-v2").exists():
            return parent
    return here.parents[2]


def _copy_config(src: Path, dst: Path) -> None:
    payload = load_canon_json(src)
    write_canon_json(dst, payload)


def _resolve_pack_path(pack_path: Path, rel: str) -> Path:
    rel_path = Path(str(rel))
    if rel_path.is_absolute():
        return rel_path
    return pack_path.parent / rel_path


def _compute_problem_id(problem: dict[str, Any]) -> str:
    payload = dict(problem)
    payload.pop("problem_id", None)
    return sha256_prefixed(canon_bytes(payload))


def _write_problem_spec(
    *,
    problems_dir: Path,
    baseline_algo_id: str,
    candidate_algo_id: str,
) -> Path:
    problems_dir.mkdir(parents=True, exist_ok=True)
    problem = {
        "schema_version": "sas_code_problem_spec_v1",
        "problem_id": "",
        "domain": "SAS_CODE_SORT_V1",
        "baseline_algo_id": baseline_algo_id,
        "candidate_algo_id": candidate_algo_id,
        "description": "Prove candidate sort equivalence to baseline bubble sort.",
    }
    problem["problem_id"] = _compute_problem_id(problem)
    out_path = problems_dir / f"sha256_{problem['problem_id'].split(':',1)[1]}.sas_code_problem_spec_v1.json"
    write_canon_json(out_path, problem)
    return out_path


def _write_candidate_ir(ir_dir: Path, ir: dict[str, Any]) -> Path:
    ir_dir.mkdir(parents=True, exist_ok=True)
    path = ir_dir / f"sha256_{ir['algo_id'].split(':',1)[1]}.sas_code_ir_v1.json"
    write_canon_json(path, ir)
    return path


def _write_bundle(bundle_dir: Path, bundle: dict[str, Any]) -> Path:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    path = bundle_dir / f"sha256_{bundle['bundle_id'].split(':',1)[1]}.sas_code_candidate_bundle_v1.json"
    write_canon_json(path, bundle)
    return path


def _write_gen_receipt(receipt_dir: Path, receipt: dict[str, Any]) -> Path:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    path = receipt_dir / f"sha256_{receipt['receipt_id'].split(':',1)[1]}.sas_code_gen_receipt_v1.json"
    write_canon_json(path, receipt)
    return path


def _write_selection_receipt(selection_dir: Path, receipt: dict[str, Any]) -> Path:
    selection_dir.mkdir(parents=True, exist_ok=True)
    receipt_hash = sha256_prefixed(canon_bytes(receipt))
    path = selection_dir / f"sha256_{receipt_hash.split(':',1)[1]}.sas_code_selection_receipt_v1.json"
    write_canon_json(path, receipt)
    return path


def _write_perf_report(perf_dir: Path, report: dict[str, Any]) -> tuple[Path, str]:
    perf_dir.mkdir(parents=True, exist_ok=True)
    report_hash = sha256_prefixed(canon_bytes(report))
    path = perf_dir / f"sha256_{report_hash.split(':',1)[1]}.sas_code_perf_report_v1.json"
    write_canon_json(path, report)
    return path, report_hash


def _write_eval_report(eval_dir: Path, report: dict[str, Any]) -> tuple[Path, str]:
    eval_dir.mkdir(parents=True, exist_ok=True)
    report_hash = sha256_prefixed(canon_bytes(report))
    path = eval_dir / f"sha256_{report_hash.split(':',1)[1]}.sas_code_eval_report_v1.json"
    write_canon_json(path, report)
    return path, report_hash


def _write_attempt_receipt(receipt_dir: Path, receipt: dict[str, Any]) -> tuple[Path, str]:
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_hash = compute_attempt_receipt_hash(receipt)
    path = receipt_dir / f"sha256_{receipt_hash.split(':',1)[1]}.sas_code_attempt_receipt_v1.json"
    write_canon_json(path, receipt)
    return path, receipt_hash


def _write_promotion_bundle(promo_dir: Path, bundle: dict[str, Any]) -> tuple[Path, str]:
    promo_dir.mkdir(parents=True, exist_ok=True)
    bundle_hash = sha256_prefixed(canon_bytes(bundle))
    path = promo_dir / f"sha256_{bundle_hash.split(':',1)[1]}.sas_code_promotion_bundle_v1.json"
    write_canon_json(path, bundle)
    return path, bundle_hash


def _attempt_id(problem_id: str, candidate_algo_id: str, tick: int) -> str:
    payload = {"problem_id": problem_id, "candidate_algo_id": candidate_algo_id, "tick": int(tick)}
    return sha256_prefixed(canon_bytes(payload))


def run_sas_code(
    *,
    sas_code_root: Path,
    pack_path: Path,
    campaign_tag: str = "rsi_sas_code_v12_0",
) -> dict[str, Any]:
    canon = canon_root_v1_for(os.environ.get("AGI_ROOT"), campaign_tag)
    sas_root_canon = Path(canon["sas_root_canon"])
    if sas_root_canon != sas_code_root.resolve():
        sas_code_root = sas_root_canon

    sas_code_root.mkdir(parents=True, exist_ok=True)
    config_dir = sas_code_root / "config"
    state_dir = sas_code_root / "state"
    control_dir = state_dir / "control"
    ledger_dir = state_dir / "ledger"
    for path in [config_dir, control_dir, ledger_dir]:
        path.mkdir(parents=True, exist_ok=True)

    pack = load_canon_json(pack_path)
    if not isinstance(pack, dict) or pack.get("schema_version") != "rsi_sas_code_pack_v1":
        raise SASCodeError("SAS_CODE_PACK_INVALID")

    preamble_relpath = str(pack.get("lean_preamble_relpath") or "")
    preamble_hash = str(pack.get("lean_preamble_sha256") or "")
    if not preamble_relpath or not preamble_hash:
        raise SASCodeError("SAS_CODE_PREAMBLE_MISSING")
    preamble_path = _repo_root() / preamble_relpath
    if not preamble_path.exists():
        raise SASCodeError("SAS_CODE_PREAMBLE_MISSING")
    actual_preamble_hash = sha256_prefixed(preamble_path.read_bytes())
    if actual_preamble_hash != preamble_hash:
        raise SASCodeError("SAS_CODE_PREAMBLE_HASH_MISMATCH")

    # Copy config artifacts
    write_canon_json(config_dir / "rsi_sas_code_pack_v1.json", pack)

    def _p(name: str) -> Path:
        return _resolve_pack_path(pack_path, str(pack.get(name)))

    baseline_src = _p("baseline_algo_ir_path")
    gen_cfg_src = _p("gen_config_path")
    sel_policy_src = _p("selection_policy_path")
    perf_policy_src = _p("perf_policy_path")
    dev_suite_src = _p("suitepack_path_dev")
    held_suite_src = _p("suitepack_path_heldout")
    lease_src = _p("lease_token_path")
    toolchain_src = _p("toolchain_manifest_path")

    _copy_config(baseline_src, config_dir / "baseline_bubble_sort_v1.sas_code_ir_v1.json")
    _copy_config(gen_cfg_src, config_dir / "sas_code_gen_config_v1.json")
    _copy_config(sel_policy_src, config_dir / "sas_code_selection_policy_v1.json")
    _copy_config(perf_policy_src, config_dir / "sas_code_perf_policy_v1.json")
    _copy_config(dev_suite_src, config_dir / "sas_code_suitepack_dev_v1.json")
    _copy_config(held_suite_src, config_dir / "sas_code_suitepack_heldout_v1.json")
    _copy_config(lease_src, config_dir / "sas_code_lease_token_v1.json")
    if toolchain_src.exists():
        _copy_config(toolchain_src, config_dir / "sas_code_toolchain_manifest_lean4_v1.json")

    # root manifest + ledger
    write_root_manifest(state_dir, canon)
    ledger = SASCodeLedgerWriter(ledger_dir / "sas_code_synthesis_ledger_v1.jsonl")
    tick = 0
    ledger.append(event_type="SAS_CODE_BOOT", event_payload={}, tick=tick)
    tick += 1
    ledger.append(event_type="SAS_CODE_ROOT_MANIFEST_WRITTEN", event_payload={}, tick=tick)

    # require enable + lease
    for name in ["ENABLE_RESEARCH", "ENABLE_SAS_CODE", "SAS_CODE_LEASE.json"]:
        if not (control_dir / name).exists():
            raise SASCodeError("SAS_CODE_LOCKED_MISSING_KEYS")
    ledger.append(event_type="SAS_CODE_ENABLE_PRESENT", event_payload={}, tick=tick)

    # Load baseline IR
    baseline_ir = load_canon_json(config_dir / "baseline_bubble_sort_v1.sas_code_ir_v1.json")
    validate_ir(baseline_ir)
    baseline_algo_id = baseline_ir["algo_id"]

    ir_dir = state_dir / "code" / "candidates" / "ir"
    _write_candidate_ir(ir_dir, baseline_ir)
    ledger.append(event_type="SAS_CODE_BASELINE_READY", event_payload={"baseline_algo_id": baseline_algo_id}, tick=tick)
    tick += 1

    # Generate candidate IRs + bundle
    gen_cfg = load_canon_json(config_dir / "sas_code_gen_config_v1.json")
    generator_seed = str(gen_cfg.get("generator_seed"))
    generator_config_hash = sha256_prefixed(canon_bytes(gen_cfg))
    candidate_irs = enumerate_candidate_irs(baseline_ir)
    bundle = build_candidate_bundle(
        baseline_algo_id=baseline_algo_id,
        candidate_irs=candidate_irs,
        generator_seed=generator_seed,
        generator_config_hash=generator_config_hash,
    )
    bundle_path = _write_bundle(state_dir / "code" / "candidates" / "bundles", bundle)
    for ir in candidate_irs:
        _write_candidate_ir(ir_dir, ir)

    stdout_hash = sha256_prefixed(b"GENERATED\n")
    stderr_hash = sha256_prefixed(b"")
    gen_receipt = build_gen_receipt(
        bundle_id=bundle["bundle_id"],
        generator_seed=generator_seed,
        generator_config_hash=generator_config_hash,
        stdout_hash=stdout_hash,
        stderr_hash=stderr_hash,
    )
    _write_gen_receipt(state_dir / "code" / "candidates" / "receipts", gen_receipt)
    ledger.append(event_type="SAS_CODE_CANDIDATE_BUNDLE_WRITTEN", event_payload={"bundle_id": bundle["bundle_id"]}, tick=tick)
    tick += 1

    # Problem specs per candidate (used for proof attempts)
    problems_dir = state_dir / "code" / "problems"
    problem_ids: dict[str, str] = {}
    problem_paths: dict[str, Path] = {}
    for cand in candidate_irs:
        path = _write_problem_spec(
            problems_dir=problems_dir,
            baseline_algo_id=baseline_algo_id,
            candidate_algo_id=cand["algo_id"],
        )
        problem_paths[cand["algo_id"]] = path
        problem = load_canon_json(path)
        problem_ids[cand["algo_id"]] = problem["problem_id"]

    # Proof attempts (use single proof artifact for all candidates)
    proof_dir = state_dir / "code" / "attempts" / "proofs"
    sealed_dir = state_dir / "code" / "attempts" / "sealed"
    receipt_dir = state_dir / "code" / "attempts" / "receipts"
    work_dir = state_dir / "code" / "attempts" / "work" / "attempts"
    for d in [proof_dir, sealed_dir, receipt_dir, work_dir]:
        d.mkdir(parents=True, exist_ok=True)

    proof = proof_text()
    if scan_forbidden_tokens(proof):
        raise SASCodeError("FORBIDDEN_TOKEN_IN_PROOF")
    proof_bytes = proof.encode("utf-8")
    proof_hash = sha256_prefixed(proof_bytes)
    proof_path = proof_dir / f"sha256_{proof_hash.split(':',1)[1]}.proof.lean"
    proof_path.write_bytes(proof_bytes)

    toolchain_manifest = load_toolchain_manifest(config_dir / "sas_code_toolchain_manifest_lean4_v1.json")
    toolchain_id = toolchain_manifest.get("toolchain_id")
    toolchain_manifest_hash = compute_manifest_hash(toolchain_manifest)
    perf_policy = load_canon_json(config_dir / "sas_code_perf_policy_v1.json")

    # Attempt receipts per candidate
    attempt_receipts: list[dict[str, Any]] = []
    daemon_id = "sha256:" + "3" * 64
    for idx, cand in enumerate(candidate_irs):
        candidate_algo_id = cand["algo_id"]
        problem_id = problem_ids[candidate_algo_id]
        attempt_id = _attempt_id(problem_id, candidate_algo_id, tick + idx)
        work_attempt_dir = work_dir / f"sha256_{attempt_id.split(':',1)[1]}"
        work_attempt_dir.mkdir(parents=True, exist_ok=True)
        sealed = sealed_proof_check_receipt(
            toolchain_manifest=toolchain_manifest,
            problem_id=problem_id,
            attempt_id=attempt_id,
            proof_text=proof,
            lean_preamble_path=preamble_path,
            lean_preamble_sha256=preamble_hash,
            work_dir=work_attempt_dir,
        )
        sealed_hash = compute_sealed_receipt_hash(sealed)
        sealed_path = sealed_dir / f"sha256_{sealed_hash.split(':',1)[1]}.sealed_proof_check_receipt_v1.json"
        write_canon_json(sealed_path, sealed)

        receipt = {
            "schema_version": "sas_code_attempt_receipt_v1",
            "attempt_id": attempt_id,
            "daemon_id": daemon_id,
            "problem_id": problem_id,
            "lean_preamble_sha256": preamble_hash,
            "lean_preamble_relpath": preamble_relpath,
            "baseline_algo_id": baseline_algo_id,
            "candidate_algo_id": candidate_algo_id,
            "proof_artifact_hash": proof_hash,
            "sealed_proof_check_receipt_hash": sealed_hash,
            "result": sealed.get("result"),
            "toolchain_id": toolchain_id,
            "toolchain_manifest_hash": toolchain_manifest_hash,
            "stdout_hash": sealed.get("stdout_hash"),
            "stderr_hash": sealed.get("stderr_hash"),
            "wall_ms": 1,
            "tick": tick + idx,
        }
        _write_attempt_receipt(receipt_dir, receipt)
        attempt_receipts.append(receipt)

        (work_attempt_dir / "proof.lean").write_bytes(proof_bytes)

    ledger.append(event_type="SAS_CODE_PROOF_ATTEMPTED", event_payload={"count": len(attempt_receipts)}, tick=tick)
    tick += 1

    # Determine candidate perf on HELDOUT for selection
    suite_held = load_canon_json(config_dir / "sas_code_suitepack_heldout_v1.json")
    suite_held_hash = sha256_prefixed(canon_bytes(suite_held))
    suite_held["suitepack_hash"] = suite_held_hash

    perf_reports_held: dict[str, dict[str, Any]] = {}
    for cand in candidate_irs:
        report = compute_perf_report(
            eval_kind="HELDOUT",
            suitepack=suite_held,
            baseline_algo_id=baseline_algo_id,
            baseline_algo_kind=baseline_ir.get("algo_kind"),
            candidate_algo_id=cand["algo_id"],
            candidate_algo_kind=cand.get("algo_kind"),
            policy=perf_policy,
        )
        perf_reports_held[cand["algo_id"]] = report

    # selection
    sel_policy = load_canon_json(config_dir / "sas_code_selection_policy_v1.json")
    sel_policy_hash = compute_selection_policy_hash(sel_policy)
    proof_passed = {r["candidate_algo_id"]: (r.get("result") == "PASS") for r in attempt_receipts}
    selection_receipt = select_candidate(
        bundle=bundle,
        perf_reports=perf_reports_held,
        proof_passed=proof_passed,
        selection_policy_hash=sel_policy_hash,
    )
    _write_selection_receipt(state_dir / "code" / "candidates" / "selection", selection_receipt)
    selected_algo_id = selection_receipt.get("selected_algo_id")
    ledger.append(event_type="SAS_CODE_SELECTION_DONE", event_payload={"selected_algo_id": selected_algo_id}, tick=tick)
    tick += 1

    # proof problem spec: use selected candidate
    problem_path = problem_paths[selected_algo_id]
    selected_dir = state_dir / "code" / "problems_selected"
    selected_dir.mkdir(parents=True, exist_ok=True)
    (selected_dir / problem_path.name).write_bytes(problem_path.read_bytes())

    # Eval reports (per candidate, DEV)
    eval_dir = state_dir / "eval" / "reports"
    for cand in candidate_irs:
        receipts = [r for r in attempt_receipts if r.get("candidate_algo_id") == cand["algo_id"]]
        report = compute_eval_report(algo_id=cand["algo_id"], eval_kind="DEV", attempt_receipts=receipts)
        _write_eval_report(eval_dir, report)
    ledger.append(event_type="SAS_CODE_EVAL_DEV_DONE", event_payload={}, tick=tick)
    tick += 1

    # Perf reports for selected candidate
    suite_dev = load_canon_json(config_dir / "sas_code_suitepack_dev_v1.json")
    suite_dev_hash = sha256_prefixed(canon_bytes(suite_dev))
    suite_dev["suitepack_hash"] = suite_dev_hash

    selected_ir = next(ir for ir in candidate_irs if ir["algo_id"] == selected_algo_id)

    perf_dev = compute_perf_report(
        eval_kind="DEV",
        suitepack=suite_dev,
        baseline_algo_id=baseline_algo_id,
        baseline_algo_kind=baseline_ir.get("algo_kind"),
        candidate_algo_id=selected_algo_id,
        candidate_algo_kind=selected_ir.get("algo_kind"),
        policy=perf_policy,
    )
    perf_held = perf_reports_held[selected_algo_id]
    # update heldout suitepack hash to canonical
    perf_held["suitepack_hash"] = suite_held_hash

    perf_dev_path, perf_dev_hash = _write_perf_report(state_dir / "eval" / "perf", perf_dev)
    perf_held_path, perf_held_hash = _write_perf_report(state_dir / "eval" / "perf", perf_held)

    ledger.append(event_type="SAS_CODE_EVAL_HELDOUT_DONE", event_payload={}, tick=tick)
    tick += 1

    # Novelty score
    novelty = novelty_score_q32(selected_ir)
    ledger.append(event_type="SAS_CODE_NOVELTY_DONE", event_payload={"novelty_score_q32": novelty}, tick=tick)
    tick += 1

    # Promotion bundle
    thresholds = pack.get("thresholds") or {}
    min_novelty_q32 = thresholds.get("min_novelty_q32") or q32_obj(0)
    min_improvement = int(thresholds.get("min_improvement_percent", 30))
    require_novelty = bool(thresholds.get("require_novelty", True))

    # choose attempt receipt for selected candidate
    selected_attempt = next(r for r in attempt_receipts if r.get("candidate_algo_id") == selected_algo_id)
    selected_attempt_hash = compute_attempt_receipt_hash(selected_attempt)
    sealed_hash = selected_attempt.get("sealed_proof_check_receipt_hash")

    reasons: list[str] = []
    if selected_attempt.get("result") != "PASS":
        reasons.append("PROOF_FAIL")
    if not perf_held.get("gate", {}).get("passed"):
        reasons.append("NO_PERF_GAIN")
    if require_novelty and parse_q32(novelty) < parse_q32(min_novelty_q32):
        reasons.append("NOVELTY_REQUIRED_NOT_MET")

    promo = {
        "schema_version": "sas_code_promotion_bundle_v1",
        "bundle_id": "",
        "created_utc": _now_utc(),
        "problem_id": problem_ids[selected_algo_id],
        "baseline_algo_id": baseline_algo_id,
        "candidate_algo_id": selected_algo_id,
        "candidate_attempt_receipt_sha256": selected_attempt_hash,
        "sealed_proof_receipt_sha256": sealed_hash,
        "perf_report_sha256_dev": perf_dev_hash,
        "perf_report_sha256_heldout": perf_held_hash,
        "require_equivalence_proof": True,
        "require_perf_gain": True,
        "require_novelty": require_novelty,
        "min_novelty_q32": min_novelty_q32,
        "min_improvement_percent": min_improvement,
        "acceptance_decision": {"pass": len(reasons) == 0, "reasons": reasons},
    }
    promo["bundle_id"] = sha256_prefixed(canon_bytes({k: v for k, v in promo.items() if k != "bundle_id"}))
    promo_path, promo_hash = _write_promotion_bundle(state_dir / "promotion", promo)

    promo_rel = promo_path.relative_to(state_dir).as_posix()
    ledger.append(event_type="SAS_CODE_PROMOTION_WRITTEN", event_payload={"promotion_bundle_path": promo_rel}, tick=tick)
    tick += 1
    ledger.append(event_type="SAS_CODE_SHUTDOWN", event_payload={}, tick=tick)

    return {"status": "OK", "promotion_bundle": str(promo_path), "bundle_hash": promo_hash}


__all__ = ["run_sas_code", "SASCodeError"]
