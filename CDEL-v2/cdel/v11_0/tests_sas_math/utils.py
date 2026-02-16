from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line
from cdel.v8_0.math_attempts import compute_attempt_id, compute_attempt_receipt_hash
from cdel.v8_0.math_toolchain import compute_manifest_hash, compute_toolchain_id
from cdel.v8_0.sealed_proofcheck import compute_sealed_receipt_hash
from cdel.v11_0.fixed_q32_v1 import Q, parse_q32, q32_from_ratio, q32_obj
from cdel.v11_0.path_canon_v1 import canon_root_v1_for
from cdel.v11_0.sas_math_eval_v1 import compute_eval_report
from cdel.v11_0.sas_math_fingerprint_v1 import compute_fingerprint
from cdel.v11_0.sas_math_ledger import compute_entry_hash
from cdel.v11_0.sas_math_policy_ir_v1 import compute_policy_id


@dataclass
class SASMathState:
    agi_root: Path
    sas_root: Path
    state_dir: Path
    config_dir: Path
    baseline_policy_id: str
    candidate_policy_id: str
    baseline_report_hash: str
    candidate_report_hash_dev: str
    candidate_report_hash_heldout: str
    promotion_path: Path


def _write_root_manifest(state_dir: Path, agi_root_raw: str) -> Path:
    canon = canon_root_v1_for(agi_root_raw, "rsi_sas_math_v11_0")
    manifest = dict(canon)
    manifest.update(
        {
            "schema_version": "sas_root_manifest_v1",
            "canon_time_utc": "2026-02-04T00:00:00Z",
            "agi_root_canon_hash": sha256_prefixed(str(canon["agi_root_canon"]).encode("utf-8")),
            "sas_root_canon_hash": sha256_prefixed(str(canon["sas_root_canon"]).encode("utf-8")),
        }
    )
    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    out_path = state_dir / "health" / f"sha256_{manifest_hash.split(':',1)[1]}.sas_root_manifest_v1.json"
    write_canon_json(out_path, manifest)
    return out_path


def _toolchain_manifest() -> dict[str, Any]:
    manifest = {
        "schema_version": "math_toolchain_manifest_v1",
        "checker_name": "toy_kernel",
        "checker_version": "v1",
        "checker_executable_hash": "sha256:" + "0" * 64,
        "library_name": "toy_library",
        "library_commit": "v1",
        "os": "macos",
        "arch": "arm64",
        "invocation_template": ["/usr/bin/python3", "/tmp/checker.py", "{entrypoint}"],
        "toolchain_id": "",
    }
    manifest["toolchain_id"] = compute_toolchain_id(manifest)
    return manifest


def _write_attempt(
    *,
    state_dir: Path,
    attempt_id_seed: int,
    problem_id: str,
    toolchain: dict[str, Any],
    proof_token: str,
    result: str,
) -> dict[str, Any]:
    # Attempt record
    record = {
        "schema_version": "math_attempt_record_v1",
        "attempt_id": "",
        "problem_id": problem_id,
        "tick": attempt_id_seed,
        "daemon_id": "sha256:" + "1" * 64,
        "superego_request_id": "sha256:" + "2" * 64,
        "objective_class": "BOUNDLESS_RESEARCH",
        "capabilities": ["FS_READ_WORKSPACE", "FS_WRITE_DAEMON_STATE", "SEALEDEXEC", "SUBPROCESS_TOOLCHAIN", "NETWORK_NONE"],
    }
    record["attempt_id"] = compute_attempt_id(record)
    record_hash = sha256_prefixed(canon_bytes(record))
    record_path = state_dir / "math" / "attempts" / "records" / f"sha256_{record_hash.split(':',1)[1]}.math_attempt_record_v1.json"
    write_canon_json(record_path, record)

    # Proof artifact
    statement_hash = sha256_prefixed(b"1 = 1\n")
    proof_obj = {
        "schema_version": "math_proof_v1",
        "attempt_id": record["attempt_id"],
        "problem_id": problem_id,
        "statement_hash": statement_hash,
        "proof": proof_token,
    }
    proof_bytes = canon_bytes(proof_obj)
    proof_hash = sha256_prefixed(proof_bytes)
    proof_path = state_dir / "math" / "attempts" / "proofs" / f"sha256_{proof_hash.split(':',1)[1]}.proof"
    proof_path.write_bytes(proof_bytes)

    # Logs
    stdout = b"PASS\n" if result == "PASS" else b"FAIL\n"
    stderr = b""
    stdout_hash = sha256_prefixed(stdout)
    stderr_hash = sha256_prefixed(stderr)
    logs_dir = state_dir / "math" / "attempts" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / f"sha256_{stdout_hash.split(':',1)[1]}.stdout.log").write_bytes(stdout)
    (logs_dir / f"sha256_{stderr_hash.split(':',1)[1]}.stderr.log").write_bytes(stderr)

    sandbox_manifest = {
        "network": "NONE",
        "time_limit_ms": 1000,
        "memory_limit_mb": 256,
        "env": {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "PYTHONHASHSEED": "0"},
    }
    sandbox_manifest_hash = sha256_prefixed(canon_bytes(sandbox_manifest))

    sealed = {
        "schema_version": "sealed_proof_check_receipt_v1",
        "toolchain_id": toolchain.get("toolchain_id"),
        "problem_id": problem_id,
        "attempt_id": record["attempt_id"],
        "invocation_argv": ["/usr/bin/python3", "checker.py", "proof.txt"],
        "exit_code": 0 if result == "PASS" else 1,
        "stdout_hash": stdout_hash,
        "stderr_hash": stderr_hash,
        "result": result,
        "time_ms": 1,
        "sandbox_manifest_hash": sandbox_manifest_hash,
    }
    sealed_hash = compute_sealed_receipt_hash(sealed)
    sealed_path = state_dir / "math" / "attempts" / "sealed" / f"sha256_{sealed_hash.split(':',1)[1]}.sealed_proof_check_receipt_v1.json"
    write_canon_json(sealed_path, sealed)

    receipt = {
        "schema_version": "math_attempt_receipt_v1",
        "attempt_id": record["attempt_id"],
        "problem_id": problem_id,
        "tick": record["tick"],
        "daemon_id": record["daemon_id"],
        "toolchain_id": toolchain.get("toolchain_id"),
        "toolchain_manifest_hash": compute_manifest_hash(toolchain),
        "sealed_proof_check_receipt_hash": sealed_hash,
        "result": result,
        "proof_artifact_hash": proof_hash,
        "stdout_hash": stdout_hash,
        "stderr_hash": stderr_hash,
        "wall_ms": 1,
    }
    receipt_hash = compute_attempt_receipt_hash(receipt)
    receipt_path = state_dir / "math" / "attempts" / "receipts" / f"sha256_{receipt_hash.split(':',1)[1]}.math_attempt_receipt_v1.json"
    write_canon_json(receipt_path, receipt)

    return receipt


def _write_ledger(state_dir: Path, promotion_path: Path) -> None:
    ledger_path = state_dir / "ledger" / "sas_math_synthesis_ledger_v1.jsonl"
    entries = []
    prev_hash = "GENESIS"
    seq = 0
    for tick, event_type, payload in [
        (0, "SAS_MATH_BOOT", {}),
        (1, "SAS_MATH_ROOT_MANIFEST_WRITTEN", {}),
        (1, "SAS_MATH_ENABLE_PRESENT", {}),
        (2, "SAS_MATH_BASELINE_READY", {}),
        (3, "SAS_MATH_CANDIDATE_PROPOSED", {}),
        (3, "SAS_MATH_FINGERPRINT_DONE", {}),
        (4, "SAS_MATH_EVAL_DEV_DONE", {}),
        (5, "SAS_MATH_SELECTED_FOR_HELDOUT", {}),
        (6, "SAS_MATH_EVAL_HELDOUT_DONE", {}),
        (7, "SAS_MATH_NOVELTY_DONE", {}),
        (8, "SAS_MATH_PROMOTION_WRITTEN", {"promotion_bundle_path": str(promotion_path)}),
        (9, "SAS_MATH_SHUTDOWN", {}),
    ]:
        seq += 1
        entry = {
            "seq": seq,
            "tick": tick,
            "event_type": event_type,
            "event_payload": dict(payload),
            "prev_entry_hash": prev_hash,
            "entry_hash": "",
        }
        entry["entry_hash"] = compute_entry_hash(entry)
        prev_hash = entry["entry_hash"]
        entries.append(entry)

    for entry in entries:
        write_jsonl_line(ledger_path, entry)


def build_state(
    tmp_path: Path,
    *,
    baseline_token: str = "bad",
    candidate_token: str = "refl",
    require_novelty: bool = True,
    min_novelty_q: int | None = None,
    min_utility_delta_q: int = 0,
    min_efficiency_delta_q: int = 0,
    max_utility_regression_q: int = 0,
) -> SASMathState:
    agi_root = tmp_path / "agi_root"
    sas_root = agi_root / "daemon" / "rsi_sas_math_v11_0"
    config_dir = sas_root / "config"
    state_dir = sas_root / "state"
    control_dir = state_dir / "control"
    ledger_dir = state_dir / "ledger"
    for path in [config_dir, control_dir, ledger_dir]:
        path.mkdir(parents=True, exist_ok=True)

    # Enable files + lease placeholder
    for name in ["ENABLE_RESEARCH", "ENABLE_BOUNDLESS_MATH", "ENABLE_SAS_MATH", "ENABLE_MODEL_GENESIS"]:
        (control_dir / name).write_text("enable", encoding="utf-8")
    lease = {
        "schema_version": "sas_math_lease_token_v1",
        "lease_id": "sha256:" + "9" * 64,
        "issued_by": "fixture",
        "valid_from_tick": 0,
        "valid_until_tick": 100,
        "allowed_ops": ["SAS_MATH_DEV_EVAL", "SAS_MATH_HELDOUT_EVAL", "SAS_MATH_PROMOTE"],
        "max_runs": 2,
    }
    write_canon_json(control_dir / "SAS_MATH_LEASE.json", lease)

    # Config pack + allowlist + search config
    toolchain = _toolchain_manifest()
    toolchain_path = config_dir / "math_toolchain_manifest_toy_kernel_v1.json"
    write_canon_json(toolchain_path, toolchain)

    pack = {
        "schema_version": "rsi_sas_math_pack_v1",
        "icore_id": "sha256:" + "a" * 64,
        "meta_hash": "0" * 64,
        "superego_policy_hash": "sha256:" + "b" * 64,
        "lease_token_path": "sas_math_lease_token_v1.json",
        "boundless_math_pack_path_dev": "boundless_math_pack_dev_v1.json",
        "boundless_math_pack_path_heldout": "boundless_math_pack_heldout_v1.json",
        "toolchain_manifest_paths": [toolchain_path.name],
        "baseline_policy_ir_path": "baseline_policy_ir_v1.json",
        "policy_allowlist_path": "sas_math_policy_allowlist_v1.json",
        "search_config_path": "sas_math_search_config_v1.json",
        "thresholds": {
            "min_utility_delta_q32": q32_obj(min_utility_delta_q),
            "min_efficiency_delta_q32": q32_obj(min_efficiency_delta_q),
            "max_utility_regression_q32": q32_obj(max_utility_regression_q),
            "require_novelty": bool(require_novelty),
            "min_novelty_q32": q32_obj(Q if min_novelty_q is None else min_novelty_q),
        },
    }
    write_canon_json(config_dir / "rsi_sas_math_pack_v1.json", pack)

    allowlist = {
        "schema_version": "sas_math_policy_allowlist_v1",
        "allowed_policy_families": ["toy_checker_proof_v1"],
        "allowed_toy_checker_proofs": ["refl", "bad"],
        "allowed_lean_tactics": [],
        "max_attempts_per_problem_max": 1,
    }
    write_canon_json(config_dir / "sas_math_policy_allowlist_v1.json", allowlist)

    search_cfg = {"schema_version": "sas_math_search_config_v1", "candidates": []}
    write_canon_json(config_dir / "sas_math_search_config_v1.json", search_cfg)

    # State layout
    for path in [
        state_dir / "policy" / "candidates",
        state_dir / "policy" / "fingerprints",
        state_dir / "eval" / "reports",
        state_dir / "promotion",
        state_dir / "health",
        state_dir / "math" / "attempts" / "records",
        state_dir / "math" / "attempts" / "receipts",
        state_dir / "math" / "attempts" / "sealed",
        state_dir / "math" / "attempts" / "proofs",
        state_dir / "math" / "attempts" / "logs",
    ]:
        path.mkdir(parents=True, exist_ok=True)

    _write_root_manifest(state_dir, str(agi_root))

    # Policies
    baseline = {
        "schema_version": "sas_math_policy_ir_v1",
        "policy_id": "",
        "policy_family": "toy_checker_proof_v1",
        "toy_checker_proofs": [baseline_token],
        "lean_tactics": [],
        "max_attempts_per_problem": 1,
        "seed": 0,
    }
    baseline["policy_id"] = compute_policy_id(baseline)
    baseline_path = state_dir / "policy" / "candidates" / f"sha256_{baseline['policy_id'].split(':',1)[1]}.sas_math_policy_ir_v1.json"
    write_canon_json(baseline_path, baseline)

    candidate = {
        "schema_version": "sas_math_policy_ir_v1",
        "policy_id": "",
        "policy_family": "toy_checker_proof_v1",
        "toy_checker_proofs": [candidate_token],
        "lean_tactics": [],
        "max_attempts_per_problem": 1,
        "seed": 1,
    }
    candidate["policy_id"] = compute_policy_id(candidate)
    candidate_path = state_dir / "policy" / "candidates" / f"sha256_{candidate['policy_id'].split(':',1)[1]}.sas_math_policy_ir_v1.json"
    write_canon_json(candidate_path, candidate)

    baseline_fp = compute_fingerprint(baseline)
    baseline_fp_hash = sha256_prefixed(canon_bytes(baseline_fp))
    baseline_fp_path = state_dir / "policy" / "fingerprints" / f"sha256_{baseline_fp_hash.split(':',1)[1]}.sas_math_policy_fingerprint_v1.json"
    write_canon_json(baseline_fp_path, baseline_fp)

    candidate_fp = compute_fingerprint(candidate)
    candidate_fp_hash = sha256_prefixed(canon_bytes(candidate_fp))
    candidate_fp_path = state_dir / "policy" / "fingerprints" / f"sha256_{candidate_fp_hash.split(':',1)[1]}.sas_math_policy_fingerprint_v1.json"
    write_canon_json(candidate_fp_path, candidate_fp)

    # Attempt receipts
    problem_id = "sha256:" + "c" * 64
    baseline_receipt = _write_attempt(
        state_dir=state_dir,
        attempt_id_seed=1,
        problem_id=problem_id,
        toolchain=toolchain,
        proof_token=baseline_token,
        result="PASS" if baseline_token == "refl" else "FAIL",
    )
    candidate_receipt = _write_attempt(
        state_dir=state_dir,
        attempt_id_seed=2,
        problem_id=problem_id,
        toolchain=toolchain,
        proof_token=candidate_token,
        result="PASS" if candidate_token == "refl" else "FAIL",
    )

    baseline_report = compute_eval_report(policy_id=baseline["policy_id"], eval_kind="DEV", attempt_receipts=[baseline_receipt])
    baseline_report_hash = sha256_prefixed(canon_bytes(baseline_report))
    baseline_report_path = state_dir / "eval" / "reports" / f"sha256_{baseline_report_hash.split(':',1)[1]}.sas_math_eval_report_v1.json"
    write_canon_json(baseline_report_path, baseline_report)

    candidate_report_dev = compute_eval_report(policy_id=candidate["policy_id"], eval_kind="DEV", attempt_receipts=[candidate_receipt])
    cand_report_hash_dev = sha256_prefixed(canon_bytes(candidate_report_dev))
    cand_report_path_dev = state_dir / "eval" / "reports" / f"sha256_{cand_report_hash_dev.split(':',1)[1]}.sas_math_eval_report_v1.json"
    write_canon_json(cand_report_path_dev, candidate_report_dev)

    candidate_report_heldout = compute_eval_report(policy_id=candidate["policy_id"], eval_kind="HELDOUT", attempt_receipts=[candidate_receipt])
    cand_report_hash_held = sha256_prefixed(canon_bytes(candidate_report_heldout))
    cand_report_path_held = state_dir / "eval" / "reports" / f"sha256_{cand_report_hash_held.split(':',1)[1]}.sas_math_eval_report_v1.json"
    write_canon_json(cand_report_path_held, candidate_report_heldout)

    # Novelty
    novelty_score = Q if candidate_fp_hash != baseline_fp_hash else 0

    # Improvement evidence
    improved_problem_ids = []
    improvement_evidence = []
    if baseline_receipt.get("result") != "PASS" and candidate_receipt.get("result") == "PASS":
        improved_problem_ids = [problem_id]
        improvement_evidence = [
            {
                "problem_id": problem_id,
                "baseline_attempt_receipt_sha256": compute_attempt_receipt_hash(baseline_receipt),
                "candidate_attempt_receipt_sha256": compute_attempt_receipt_hash(candidate_receipt),
                "candidate_sealed_receipt_sha256": candidate_receipt.get("sealed_proof_check_receipt_hash"),
                "candidate_proof_artifact_hash": candidate_receipt.get("proof_artifact_hash"),
            }
        ]

    # Promotion bundle
    min_util = parse_q32(pack["thresholds"]["min_utility_delta_q32"])
    min_eff = parse_q32(pack["thresholds"]["min_efficiency_delta_q32"])
    max_reg = parse_q32(pack["thresholds"]["max_utility_regression_q32"])
    min_nov = parse_q32(pack["thresholds"]["min_novelty_q32"])
    require_nov = bool(pack["thresholds"]["require_novelty"])

    base_util = parse_q32(baseline_report.get("utility_q32"))
    cand_util = parse_q32(candidate_report_heldout.get("utility_q32"))
    base_eff = parse_q32(baseline_report.get("capacity_eff_q32"))
    cand_eff = parse_q32(candidate_report_heldout.get("capacity_eff_q32"))
    delta_u = cand_util - base_util
    delta_e = cand_eff - base_eff

    reasons = []
    if delta_u < -max_reg:
        reasons.append("UTILITY_REGRESSION_EXCEEDS_MAX")
    if not (delta_u >= min_util or delta_e >= min_eff):
        reasons.append("DOMINANCE_NOT_MET")
    if require_nov and novelty_score < min_nov:
        reasons.append("NOVELTY_REQUIRED_NOT_MET")
    passed = len(reasons) == 0

    promo = {
        "schema_version": "sas_math_promotion_bundle_v1",
        "bundle_id": "",
        "created_utc": "2026-02-04T00:00:00Z",
        "acceptance_decision": {"pass": passed, "reasons": reasons},
        "baseline_policy_id": baseline["policy_id"],
        "baseline_fingerprint_hash": baseline_fp_hash,
        "baseline_utility_q32": baseline_report.get("utility_q32"),
        "baseline_capacity_efficiency_q32": baseline_report.get("capacity_eff_q32"),
        "baseline_eval_report_sha256": baseline_report_hash,
        "candidate_policy_id": candidate["policy_id"],
        "candidate_fingerprint_hash": candidate_fp_hash,
        "candidate_utility_q32": candidate_report_heldout.get("utility_q32"),
        "candidate_capacity_efficiency_q32": candidate_report_heldout.get("capacity_eff_q32"),
        "candidate_eval_report_sha256_dev": cand_report_hash_dev,
        "candidate_eval_report_sha256_heldout": cand_report_hash_held,
        "require_novelty": require_nov,
        "min_novelty_q32": pack["thresholds"]["min_novelty_q32"],
        "novelty_score_q32": q32_obj(novelty_score),
        "min_utility_delta_q32": pack["thresholds"]["min_utility_delta_q32"],
        "min_efficiency_delta_q32": pack["thresholds"]["min_efficiency_delta_q32"],
        "max_utility_regression_q32": pack["thresholds"]["max_utility_regression_q32"],
        "improved_problem_ids": improved_problem_ids,
        "improvement_evidence": improvement_evidence,
    }
    promo_hash = sha256_prefixed(canon_bytes({k: v for k, v in promo.items() if k != "bundle_id"}))
    promo["bundle_id"] = promo_hash
    promo_path = state_dir / "promotion" / f"sha256_{promo_hash.split(':',1)[1]}.sas_math_promotion_bundle_v1.json"
    write_canon_json(promo_path, promo)

    _write_ledger(state_dir, promo_path)

    return SASMathState(
        agi_root=agi_root,
        sas_root=sas_root,
        state_dir=state_dir,
        config_dir=config_dir,
        baseline_policy_id=baseline["policy_id"],
        candidate_policy_id=candidate["policy_id"],
        baseline_report_hash=baseline_report_hash,
        candidate_report_hash_dev=cand_report_hash_dev,
        candidate_report_hash_heldout=cand_report_hash_held,
        promotion_path=promo_path,
    )
