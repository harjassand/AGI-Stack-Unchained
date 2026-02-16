"""SAS-MATH controller (v11.0)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v11_0.fixed_q32_v1 import Q, parse_q32, q32_obj
from cdel.v11_0.path_canon_v1 import canon_root_v1_for
from cdel.v11_0.sas_math_eval_v1 import compute_eval_report
from cdel.v11_0.sas_math_fingerprint_v1 import compute_fingerprint
from cdel.v11_0.sas_math_policy_ir_v1 import compute_policy_id
from cdel.v8_0.math_attempts import compute_attempt_receipt_hash

from .ledger_writer_v1 import SASMathLedgerWriter
from .lease_v1 import load_lease, validate_lease
from .policy_allowlist_v1 import enforce_allowlist
from .policy_enumerator_v1 import enumerate_policies
from .promotion_writer_v1 import write_promotion_bundle
from .root_manifest_writer_v1 import write_root_manifest
from .sealed_math_attempt_client_v1 import run_attempt


class SASMathError(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _copy_config(src: Path, dst: Path) -> None:
    payload = load_canon_json(src)
    write_canon_json(dst, payload)


def _load_meta_ids() -> tuple[str, str, str]:
    root = _repo_root()
    lock = load_canon_json(root / "meta-core" / "meta_constitution" / "v11_0" / "immutable_core_lock_v1.json")
    icore_id = str(lock.get("core_id"))
    meta_hash = (root / "meta-core" / "meta_constitution" / "v11_0" / "META_HASH").read_text(encoding="utf-8").strip()
    superego_hash = sha256_prefixed((root / "meta-core" / "meta_constitution" / "v11_0" / "superego_policy_v5.json").read_bytes())
    return icore_id, meta_hash, superego_hash


def _resolve_pack_path(pack_path: Path, rel: str) -> Path:
    rel_path = Path(str(rel))
    if rel_path.is_absolute():
        return rel_path
    return pack_path.parent / rel_path


def _load_boundless_pack(pack_path: Path) -> dict[str, Any]:
    pack = load_canon_json(pack_path)
    if not isinstance(pack, dict) or pack.get("schema_version") != "rsi_boundless_math_pack_v1":
        raise SASMathError("BOUNDLESS_PACK_INVALID")
    return pack


def _problems_dir(pack_path: Path, pack: dict[str, Any]) -> Path:
    path = Path(str(pack.get("problems_dir")))
    if path.is_absolute():
        return path
    return pack_path.parent / path


def _list_problem_specs(problems_dir: Path) -> list[Path]:
    return sorted(problems_dir.glob("*.math_problem_spec_v1.json"))


def _copy_problem_artifacts(problems_dir: Path, state_problems_dir: Path) -> None:
    state_problems_dir.mkdir(parents=True, exist_ok=True)
    for path in problems_dir.glob("*.math_problem_spec_v1.json"):
        dst = state_problems_dir / path.name
        if not dst.exists():
            dst.write_bytes(path.read_bytes())
    for path in problems_dir.glob("sha256_*.statement.txt"):
        dst = state_problems_dir / path.name
        if not dst.exists():
            dst.write_bytes(path.read_bytes())


def _eval_policy(
    *,
    policy_ir_path: Path,
    policy_ir: dict[str, Any],
    pack_path: Path,
    pack: dict[str, Any],
    toolchain_path: Path,
    state_dir: Path,
    eval_kind: str,
    tick_start: int,
    daemon_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    problems_dir = _problems_dir(pack_path, pack)
    state_problems_dir = state_dir / "math" / "problems"
    _copy_problem_artifacts(problems_dir, state_problems_dir)

    attempt_receipts: list[dict[str, Any]] = []
    tick = tick_start
    max_attempts = int(policy_ir.get("max_attempts_per_problem", 1))
    toy_tokens = list(policy_ir.get("toy_checker_proofs") or [])
    lean_tactics = list(policy_ir.get("lean_tactics") or [])

    accept_only_on_pass = bool((pack.get("acceptance") or {}).get("accept_only_on_pass", True))

    for problem_path in _list_problem_specs(state_problems_dir):
        problem_spec = load_canon_json(problem_path)
        problem_id = str(problem_spec.get("problem_id"))

        attempts_done = 0
        # Determine attempt order
        if policy_ir.get("policy_family") == "toy_checker_proof_v1":
            attempt_list = [str(x) for x in toy_tokens]
            tactic_list = []
        elif policy_ir.get("policy_family") == "lean_tactic_v1":
            attempt_list = []
            tactic_list = [str(x) for x in lean_tactics]
        else:
            attempt_list = [str(x) for x in toy_tokens]
            tactic_list = [str(x) for x in lean_tactics]

        for token in attempt_list:
            if attempts_done >= max_attempts:
                break
            superego_request_id = sha256_prefixed(
                canon_bytes({"policy_id": policy_ir.get("policy_id"), "problem_id": problem_id, "attempt": attempts_done, "kind": eval_kind})
            )
            receipt, _receipt_hash = run_attempt(
                problem_spec_path=problem_path,
                problems_dir=state_problems_dir,
                policy_ir_path=policy_ir_path,
                toolchain_manifest_path=toolchain_path,
                state_dir=state_dir,
                tick=tick,
                daemon_id=daemon_id,
                superego_request_id=superego_request_id,
                proof_token=token,
            )
            attempt_receipts.append(receipt)
            attempts_done += 1
            tick += 1
            if accept_only_on_pass and receipt.get("result") == "PASS":
                break

        for tactic in tactic_list:
            if attempts_done >= max_attempts:
                break
            superego_request_id = sha256_prefixed(
                canon_bytes({"policy_id": policy_ir.get("policy_id"), "problem_id": problem_id, "attempt": attempts_done, "kind": eval_kind})
            )
            receipt, _receipt_hash = run_attempt(
                problem_spec_path=problem_path,
                problems_dir=state_problems_dir,
                policy_ir_path=policy_ir_path,
                toolchain_manifest_path=toolchain_path,
                state_dir=state_dir,
                tick=tick,
                daemon_id=daemon_id,
                superego_request_id=superego_request_id,
                lean_tactic=tactic,
            )
            attempt_receipts.append(receipt)
            attempts_done += 1
            tick += 1
            if accept_only_on_pass and receipt.get("result") == "PASS":
                break

    report = compute_eval_report(policy_id=policy_ir.get("policy_id"), eval_kind=eval_kind, attempt_receipts=attempt_receipts)
    return report, attempt_receipts, tick


def run_sas_math(*, sas_math_root: Path, pack_path: Path) -> dict[str, Any]:
    canon = canon_root_v1_for(os.environ.get("AGI_ROOT"), "rsi_sas_math_v11_0")
    sas_root_canon = Path(canon["sas_root_canon"])
    if sas_root_canon != sas_math_root.resolve():
        sas_math_root = sas_root_canon

    sas_math_root.mkdir(parents=True, exist_ok=True)
    config_dir = sas_math_root / "config"
    state_dir = sas_math_root / "state"
    control_dir = state_dir / "control"
    ledger_dir = state_dir / "ledger"
    for path in [config_dir, control_dir, ledger_dir]:
        path.mkdir(parents=True, exist_ok=True)

    pack = load_canon_json(pack_path)
    if not isinstance(pack, dict) or pack.get("schema_version") != "rsi_sas_math_pack_v1":
        raise SASMathError("SAS_MATH_PACK_INVALID")

    # Copy config artifacts
    write_canon_json(config_dir / "rsi_sas_math_pack_v1.json", pack)
    pack_dir = pack_path.parent

    def _p(name: str) -> Path:
        return _resolve_pack_path(pack_path, str(pack.get(name)))

    allowlist_src = _p("policy_allowlist_path")
    search_src = _p("search_config_path")
    baseline_src = _p("baseline_policy_ir_path")
    lease_src = _p("lease_token_path")
    dev_pack_src = _p("boundless_math_pack_path_dev")
    held_pack_src = _p("boundless_math_pack_path_heldout")

    _copy_config(allowlist_src, config_dir / "sas_math_policy_allowlist_v1.json")
    _copy_config(search_src, config_dir / "sas_math_search_config_v1.json")
    _copy_config(baseline_src, config_dir / "baseline_policy_ir_v1.json")
    _copy_config(lease_src, config_dir / "sas_math_lease_token_v1.json")
    _copy_config(dev_pack_src, config_dir / "boundless_math_pack_dev_v1.json")
    _copy_config(held_pack_src, config_dir / "boundless_math_pack_heldout_v1.json")

    # Toolchains
    toolchain_paths = []
    for rel in pack.get("toolchain_manifest_paths") or []:
        src = _resolve_pack_path(pack_path, str(rel))
        dst = config_dir / Path(str(rel)).name
        _copy_config(src, dst)
        toolchain_paths.append(dst)

    # State layout
    (state_dir / "policy" / "candidates").mkdir(parents=True, exist_ok=True)
    (state_dir / "policy" / "fingerprints").mkdir(parents=True, exist_ok=True)
    (state_dir / "eval" / "reports").mkdir(parents=True, exist_ok=True)
    (state_dir / "promotion").mkdir(parents=True, exist_ok=True)
    (state_dir / "math" / "attempts" / "records").mkdir(parents=True, exist_ok=True)
    (state_dir / "math" / "attempts" / "receipts").mkdir(parents=True, exist_ok=True)
    (state_dir / "math" / "attempts" / "sealed").mkdir(parents=True, exist_ok=True)
    (state_dir / "math" / "attempts" / "proofs").mkdir(parents=True, exist_ok=True)
    (state_dir / "math" / "attempts" / "logs").mkdir(parents=True, exist_ok=True)
    (state_dir / "math" / "work" / "attempts").mkdir(parents=True, exist_ok=True)
    (state_dir / "math" / "problems").mkdir(parents=True, exist_ok=True)

    # Root manifest early + ledger boot
    ledger = SASMathLedgerWriter(ledger_dir / "sas_math_synthesis_ledger_v1.jsonl")
    ledger.append(event_type="SAS_MATH_BOOT", event_payload={}, tick=0)
    root_manifest_path = write_root_manifest(state_dir, canon)
    ledger.append(
        event_type="SAS_MATH_ROOT_MANIFEST_WRITTEN",
        event_payload={"root_manifest_hash": sha256_prefixed(canon_bytes(load_canon_json(root_manifest_path)))} ,
        tick=1,
    )

    # Enable gate + lease
    enable_files = [
        "ENABLE_RESEARCH",
        "ENABLE_BOUNDLESS_MATH",
        "ENABLE_SAS_MATH",
        "ENABLE_MODEL_GENESIS",
        "SAS_MATH_LEASE.json",
    ]
    for name in enable_files:
        if not (control_dir / name).exists():
            raise SASMathError("SAS_MATH_LOCKED_MISSING_KEYS")
    lease = load_lease(control_dir / "SAS_MATH_LEASE.json")
    validate_lease(lease, tick=1)
    ledger.append(event_type="SAS_MATH_ENABLE_PRESENT", event_payload={"lease_id": lease.get("lease_id")}, tick=1)

    allowlist = load_canon_json(config_dir / "sas_math_policy_allowlist_v1.json")
    search_cfg = load_canon_json(config_dir / "sas_math_search_config_v1.json")
    baseline_ir = load_canon_json(config_dir / "baseline_policy_ir_v1.json")

    # Baseline policy
    baseline_ir["policy_id"] = compute_policy_id(baseline_ir)
    enforce_allowlist(baseline_ir, allowlist)
    baseline_path = state_dir / "policy" / "candidates" / f"sha256_{baseline_ir['policy_id'].split(':',1)[1]}.sas_math_policy_ir_v1.json"
    write_canon_json(baseline_path, baseline_ir)
    baseline_fp = compute_fingerprint(baseline_ir)
    baseline_fp_hash = sha256_prefixed(canon_bytes(baseline_fp))
    baseline_fp_path = state_dir / "policy" / "fingerprints" / f"sha256_{baseline_fp_hash.split(':',1)[1]}.sas_math_policy_fingerprint_v1.json"
    write_canon_json(baseline_fp_path, baseline_fp)

    # Toolchain selection (toy checker preferred)
    toolchain_path = toolchain_paths[0]
    for path in toolchain_paths:
        manifest = load_canon_json(path)
        if manifest.get("checker_name") == "toy_kernel":
            toolchain_path = path
            break

    # Baseline DEV eval
    dev_pack = _load_boundless_pack(config_dir / "boundless_math_pack_dev_v1.json")
    dev_pack_path = config_dir / "boundless_math_pack_dev_v1.json"
    daemon_id = sha256_prefixed(canon_bytes(pack))
    tick = 2
    baseline_report, baseline_receipts, tick = _eval_policy(
        policy_ir_path=baseline_path,
        policy_ir=baseline_ir,
        pack_path=dev_pack_path,
        pack=dev_pack,
        toolchain_path=toolchain_path,
        state_dir=state_dir,
        eval_kind="DEV",
        tick_start=tick,
        daemon_id=daemon_id,
    )
    baseline_report_hash = sha256_prefixed(canon_bytes(baseline_report))
    baseline_report_path = state_dir / "eval" / "reports" / f"sha256_{baseline_report_hash.split(':',1)[1]}.sas_math_eval_report_v1.json"
    write_canon_json(baseline_report_path, baseline_report)
    ledger.append(event_type="SAS_MATH_BASELINE_READY", event_payload={"baseline_policy_id": baseline_ir["policy_id"]}, tick=tick)

    # Enumerate candidates
    candidates = enumerate_policies(search_cfg)
    if not candidates:
        raise SASMathError("NO_CANDIDATES")

    dev_results: list[dict[str, Any]] = []
    for idx, policy_ir in enumerate(candidates, start=1):
        policy_ir["policy_id"] = compute_policy_id(policy_ir)
        enforce_allowlist(policy_ir, allowlist)
        policy_path = state_dir / "policy" / "candidates" / f"sha256_{policy_ir['policy_id'].split(':',1)[1]}.sas_math_policy_ir_v1.json"
        write_canon_json(policy_path, policy_ir)
        ledger.append(event_type="SAS_MATH_CANDIDATE_PROPOSED", event_payload={"policy_id": policy_ir["policy_id"]}, tick=tick + idx)

        fingerprint = compute_fingerprint(policy_ir)
        fingerprint_hash = sha256_prefixed(canon_bytes(fingerprint))
        fingerprint_path = state_dir / "policy" / "fingerprints" / f"sha256_{fingerprint_hash.split(':',1)[1]}.sas_math_policy_fingerprint_v1.json"
        write_canon_json(fingerprint_path, fingerprint)
        ledger.append(event_type="SAS_MATH_FINGERPRINT_DONE", event_payload={"policy_id": policy_ir["policy_id"], "fingerprint_hash": fingerprint_hash}, tick=tick + idx)

        report, receipts, tick = _eval_policy(
            policy_ir_path=policy_path,
            policy_ir=policy_ir,
            pack_path=dev_pack_path,
            pack=dev_pack,
            toolchain_path=toolchain_path,
            state_dir=state_dir,
            eval_kind="DEV",
            tick_start=tick + 1,
            daemon_id=daemon_id,
        )
        report_hash = sha256_prefixed(canon_bytes(report))
        report_path = state_dir / "eval" / "reports" / f"sha256_{report_hash.split(':',1)[1]}.sas_math_eval_report_v1.json"
        write_canon_json(report_path, report)
        ledger.append(
            event_type="SAS_MATH_EVAL_DEV_DONE",
            event_payload={
                "policy_id": policy_ir["policy_id"],
                "utility_q32": report.get("utility_q32"),
                "capacity_eff_q32": report.get("capacity_eff_q32"),
            },
            tick=tick,
        )
        dev_results.append({"policy": policy_ir, "report": report, "report_hash": report_hash})

    # Select top candidate by utility, efficiency, policy_id
    def _score(item: dict[str, Any]) -> tuple[int, int, str]:
        util = parse_q32(item["report"].get("utility_q32"))
        eff = parse_q32(item["report"].get("capacity_eff_q32"))
        # Descending utility/efficiency, ascending policy_id for determinism.
        return (-util, -eff, item["policy"]["policy_id"])

    best = sorted(dev_results, key=_score)[0]
    candidate_policy = best["policy"]
    candidate_report_dev = best["report"]
    candidate_report_hash_dev = best["report_hash"]

    # Heldout eval
    held_pack = _load_boundless_pack(config_dir / "boundless_math_pack_heldout_v1.json")
    held_pack_path = config_dir / "boundless_math_pack_heldout_v1.json"
    ledger.append(event_type="SAS_MATH_SELECTED_FOR_HELDOUT", event_payload={"policy_id": candidate_policy["policy_id"]}, tick=tick + 1)
    candidate_report_held, candidate_receipts_held, tick = _eval_policy(
        policy_ir_path=state_dir / "policy" / "candidates" / f"sha256_{candidate_policy['policy_id'].split(':',1)[1]}.sas_math_policy_ir_v1.json",
        policy_ir=candidate_policy,
        pack_path=held_pack_path,
        pack=held_pack,
        toolchain_path=toolchain_path,
        state_dir=state_dir,
        eval_kind="HELDOUT",
        tick_start=tick + 1,
        daemon_id=daemon_id,
    )
    candidate_report_hash_held = sha256_prefixed(canon_bytes(candidate_report_held))
    candidate_report_path_held = state_dir / "eval" / "reports" / f"sha256_{candidate_report_hash_held.split(':',1)[1]}.sas_math_eval_report_v1.json"
    write_canon_json(candidate_report_path_held, candidate_report_held)
    ledger.append(
        event_type="SAS_MATH_EVAL_HELDOUT_DONE",
        event_payload={
            "policy_id": candidate_policy["policy_id"],
            "utility_q32": candidate_report_held.get("utility_q32"),
            "capacity_eff_q32": candidate_report_held.get("capacity_eff_q32"),
        },
        tick=tick,
    )

    # Novelty (binary)
    candidate_fp = compute_fingerprint(candidate_policy)
    candidate_fp_hash = sha256_prefixed(canon_bytes(candidate_fp))
    novelty_score_q32 = q32_obj(Q if candidate_fp_hash != baseline_fp_hash else 0)
    ledger.append(event_type="SAS_MATH_NOVELTY_DONE", event_payload={"novelty_score_q32": novelty_score_q32}, tick=tick + 1)

    # Improvements
    base_by_problem: dict[str, dict[str, Any]] = {}
    base_pass: dict[str, bool] = {}
    for rec in baseline_receipts:
        pid = rec.get("problem_id")
        if isinstance(pid, str):
            base_by_problem.setdefault(pid, rec)
            if rec.get("result") == "PASS":
                base_pass[pid] = True
    cand_by_problem: dict[str, dict[str, Any]] = {}
    cand_pass: dict[str, bool] = {}
    for rec in candidate_receipts_held:
        pid = rec.get("problem_id")
        if isinstance(pid, str):
            cand_by_problem.setdefault(pid, rec)
            if rec.get("result") == "PASS":
                cand_pass[pid] = True
                cand_by_problem[pid] = rec
    improved_problem_ids = sorted(pid for pid in cand_pass.keys() if not base_pass.get(pid))
    improvement_evidence: list[dict[str, Any]] = []
    for pid in improved_problem_ids:
        base_rec = base_by_problem.get(pid)
        cand_rec = cand_by_problem.get(pid)
        if base_rec is None or cand_rec is None:
            continue
        improvement_evidence.append(
            {
                "problem_id": pid,
                "baseline_attempt_receipt_sha256": compute_attempt_receipt_hash(base_rec),
                "candidate_attempt_receipt_sha256": compute_attempt_receipt_hash(cand_rec),
                "candidate_sealed_receipt_sha256": cand_rec.get("sealed_proof_check_receipt_hash"),
                "candidate_proof_artifact_hash": cand_rec.get("proof_artifact_hash"),
            }
        )

    # Promotion bundle
    thresholds = pack.get("thresholds") or {}
    promo_path = write_promotion_bundle(
        promo_dir=state_dir / "promotion",
        baseline_policy_id=baseline_ir["policy_id"],
        baseline_fingerprint_hash=baseline_fp_hash,
        baseline_eval_report_hash=baseline_report_hash,
        baseline_utility_q32=baseline_report.get("utility_q32"),
        baseline_capacity_eff_q32=baseline_report.get("capacity_eff_q32"),
        candidate_policy_id=candidate_policy["policy_id"],
        candidate_fingerprint_hash=candidate_fp_hash,
        candidate_eval_report_hash_dev=candidate_report_hash_dev,
        candidate_eval_report_hash_heldout=candidate_report_hash_held,
        candidate_utility_q32=candidate_report_held.get("utility_q32"),
        candidate_capacity_eff_q32=candidate_report_held.get("capacity_eff_q32"),
        thresholds=thresholds,
        novelty_score_q32=novelty_score_q32,
        improved_problem_ids=improved_problem_ids,
        improvement_evidence=improvement_evidence,
    )
    ledger.append(
        event_type="SAS_MATH_PROMOTION_WRITTEN",
        event_payload={"promotion_bundle_path": str(promo_path)},
        tick=tick + 2,
    )

    ledger.append(event_type="SAS_MATH_SHUTDOWN", event_payload={}, tick=tick + 3)
    return {"status": "OK", "promotion_bundle": str(promo_path)}


__all__ = ["run_sas_math", "SASMathError"]
