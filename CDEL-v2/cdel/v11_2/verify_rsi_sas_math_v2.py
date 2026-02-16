"""Verifier for RSI SAS-MATH v11.2."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from ..v8_0.math_attempts import compute_attempt_receipt_hash, load_attempt_receipt
from ..v8_0.math_toolchain import compute_manifest_hash, load_toolchain_manifest
from ..v8_0.sealed_proofcheck import compute_sealed_receipt_hash, load_sealed_receipt
from ..v11_1.fixed_q32_v1 import Q, Q32Error, parse_q32
from ..v11_1.path_canon_v1 import canon_root_v1_for
from ..v11_1.sas_math_eval_v1 import compute_eval_report
from ..v11_1.sas_math_fingerprint_v1 import compute_fingerprint
from ..v11_1.sas_math_ledger import SAS_MATH_EVENT_TYPES, load_ledger, validate_chain
from ..v11_1.sas_math_policy_ir_v1 import compute_policy_id
from .sas_conjecture_ir_v2 import (
    ALL_OPS,
    compute_conjecture_id,
    compute_fingerprint as compute_conjecture_fingerprint,
    compute_metrics,
    render_statement,
    validate_conjecture_ir,
)
from .sas_conjecture_seed_v2 import compute_conjecture_seed
from .sas_conjecture_selection_v2 import compute_score, select_conjecture
from .sas_conjecture_triviality_v2 import novelty_gate_pass


class SASMathError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise SASMathError(reason)


def _load_json(path: Path) -> Any:
    try:
        return load_canon_json(path)
    except CanonError as exc:
        msg = str(exc)
        if "floats are not allowed" in msg:
            _fail("NON_Q32_VALUE")
        raise


def _require_schema(obj: Any, schema_version: str) -> dict[str, Any]:
    if not isinstance(obj, dict) or obj.get("schema_version") != schema_version:
        _fail("SCHEMA_INVALID")
    return obj


def _parse_q32(obj: Any) -> int:
    try:
        return parse_q32(obj)
    except Q32Error:
        _fail("NON_Q32_VALUE")
    return 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_constants() -> dict[str, Any]:
    path = _repo_root() / "meta-core" / "meta_constitution" / "v11_2" / "constants_v1.json"
    const = _load_json(path)
    _require_schema(const, "constants_v1")
    return const


def _verify_root_manifest(state_dir: Path) -> None:
    health_dir = state_dir / "health"
    manifests = list(health_dir.glob("sha256_*.sas_root_manifest_v1.json"))
    if not manifests:
        _fail("ROOT_CANON_MISMATCH")
    manifest_path = manifests[0]
    manifest = _load_json(manifest_path)
    _require_schema(manifest, "sas_root_manifest_v1")
    expected = canon_root_v1_for(str(manifest.get("agi_root_raw", "")), "rsi_sas_math_v11_2")
    for key in ["agi_root_raw", "agi_root_stripped", "agi_root_canon", "was_trimmed", "sas_root_canon", "canon_method"]:
        if manifest.get(key) != expected.get(key):
            _fail("ROOT_CANON_MISMATCH")
    agi_root_canon = str(expected.get("agi_root_canon"))
    sas_root_canon = str(expected.get("sas_root_canon"))
    if str(state_dir.parent.resolve()) != sas_root_canon:
        _fail("ROOT_CANON_MISMATCH")
    if manifest.get("agi_root_canon_hash") != sha256_prefixed(agi_root_canon.encode("utf-8")):
        _fail("ROOT_CANON_MISMATCH")
    if manifest.get("sas_root_canon_hash") != sha256_prefixed(sas_root_canon.encode("utf-8")):
        _fail("ROOT_CANON_MISMATCH")
    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    if not manifest_path.name.startswith(f"sha256_{manifest_hash.split(':',1)[1]}"):
        _fail("ROOT_CANON_MISMATCH")


def _require_enable_files(state_dir: Path) -> None:
    control = state_dir / "control"
    if not (control / "ENABLE_RESEARCH").exists():
        _fail("MISSING_ENABLE_RESEARCH")
    if not (control / "ENABLE_BOUNDLESS_MATH").exists():
        _fail("MISSING_ENABLE_BOUNDLESS_MATH")
    if not (control / "ENABLE_SAS_MATH").exists():
        _fail("MISSING_ENABLE_SAS_MATH")
    if not (control / "ENABLE_MODEL_GENESIS").exists():
        _fail("MISSING_ENABLE_MODEL_GENESIS")
    if not (control / "SAS_MATH_LEASE.json").exists():
        _fail("MISSING_ARTIFACT")


def _load_toolchains(config_dir: Path, pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    toolchains: dict[str, dict[str, Any]] = {}
    for rel in pack.get("toolchain_manifest_paths") or []:
        path = config_dir / str(rel)
        manifest = load_toolchain_manifest(path)
        toolchains[manifest.get("toolchain_id")] = manifest
    return toolchains


def _load_attempt_receipt_by_hash(state_dir: Path, receipt_hash: str) -> dict[str, Any]:
    receipts_dir = state_dir / "math" / "attempts" / "receipts"
    path = receipts_dir / f"sha256_{receipt_hash.split(':',1)[1]}.math_attempt_receipt_v1.json"
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    receipt = load_attempt_receipt(path)
    expected = compute_attempt_receipt_hash(receipt)
    if expected != receipt_hash:
        _fail("CANON_HASH_MISMATCH")
    return receipt


def _validate_attempt_receipt(state_dir: Path, receipt: dict[str, Any], toolchains: dict[str, dict[str, Any]]) -> None:
    toolchain_id = receipt.get("toolchain_id")
    toolchain_manifest_hash = receipt.get("toolchain_manifest_hash")
    if toolchain_id not in toolchains:
        _fail("BOUNDLESS_MATH_TOOLCHAIN_DRIFT")
    manifest = toolchains[toolchain_id]
    if compute_manifest_hash(manifest) != toolchain_manifest_hash:
        _fail("BOUNDLESS_MATH_TOOLCHAIN_DRIFT")

    sealed_hash = receipt.get("sealed_proof_check_receipt_hash")
    if not isinstance(sealed_hash, str):
        _fail("SCHEMA_INVALID")
    sealed_dir = state_dir / "math" / "attempts" / "sealed"
    sealed_path = sealed_dir / f"sha256_{sealed_hash.split(':',1)[1]}.sealed_proof_check_receipt_v1.json"
    if not sealed_path.exists():
        _fail("MISSING_ARTIFACT")
    sealed = load_sealed_receipt(sealed_path)
    expected_sealed = compute_sealed_receipt_hash(sealed)
    if expected_sealed != sealed_hash:
        _fail("MISSING_ARTIFACT")
    if sealed.get("result") != receipt.get("result"):
        _fail("MISSING_ARTIFACT")

    logs_dir = state_dir / "math" / "attempts" / "logs"
    stdout_hash = sealed.get("stdout_hash")
    stderr_hash = sealed.get("stderr_hash")
    if not isinstance(stdout_hash, str) or not isinstance(stderr_hash, str):
        _fail("SCHEMA_INVALID")
    stdout_path = logs_dir / f"sha256_{stdout_hash.split(':',1)[1]}.stdout.log"
    stderr_path = logs_dir / f"sha256_{stderr_hash.split(':',1)[1]}.stderr.log"
    if not stdout_path.exists() or not stderr_path.exists():
        _fail("MISSING_ARTIFACT")
    if sha256_prefixed(stdout_path.read_bytes()) != stdout_hash:
        _fail("MISSING_ARTIFACT")
    if sha256_prefixed(stderr_path.read_bytes()) != stderr_hash:
        _fail("MISSING_ARTIFACT")

    proof_hash = receipt.get("proof_artifact_hash")
    if isinstance(proof_hash, str):
        proofs_dir = state_dir / "math" / "attempts" / "proofs"
        proof_path = proofs_dir / f"sha256_{proof_hash.split(':',1)[1]}.proof"
        if not proof_path.exists():
            proof_path = proofs_dir / f"sha256_{proof_hash.split(':',1)[1]}.proof.lean"
        if not proof_path.exists():
            _fail("MISSING_ARTIFACT")
        if sha256_prefixed(proof_path.read_bytes()) != proof_hash:
            _fail("MISSING_ARTIFACT")

    record_dir = state_dir / "math" / "attempts" / "records"
    if record_dir.exists():
        attempt_id = receipt.get("attempt_id")
        found = False
        for path in record_dir.glob("sha256_*.math_attempt_record_v1.json"):
            record = _load_json(path)
            if record.get("attempt_id") == attempt_id:
                found = True
                caps = record.get("capabilities") or []
                if "NETWORK_NONE" not in caps:
                    _fail("NETWORK_FORBIDDEN")
                break
        if not found:
            _fail("MISSING_ARTIFACT")


def _enforce_allowlist(policy_ir: dict[str, Any], allowlist: dict[str, Any]) -> None:
    families = allowlist.get("allowed_policy_families") or []
    if policy_ir.get("policy_family") not in families:
        _fail("ALLOWLIST_VIOLATION")
    max_cap = allowlist.get("max_attempts_per_problem_max")
    if isinstance(max_cap, int) and int(policy_ir.get("max_attempts_per_problem", 0)) > max_cap:
        _fail("ALLOWLIST_VIOLATION")
    toy_allowed = set(str(x) for x in (allowlist.get("allowed_toy_checker_proofs") or []))
    lean_allowed = set(str(x) for x in (allowlist.get("allowed_lean_tactics") or []))
    for token in policy_ir.get("toy_checker_proofs") or []:
        if str(token) not in toy_allowed:
            _fail("ALLOWLIST_VIOLATION")
    for tac in policy_ir.get("lean_tactics") or []:
        if str(tac) not in lean_allowed:
            _fail("ALLOWLIST_VIOLATION")


def verify(state_dir: Path, *, mode: str) -> dict[str, Any]:
    config_dir = state_dir.parent / "config"

    _verify_root_manifest(state_dir)
    _require_enable_files(state_dir)

    # Ledger
    ledger_path = state_dir / "ledger" / "sas_math_synthesis_ledger_v1.jsonl"
    entries = load_ledger(ledger_path)
    if not entries:
        _fail("MISSING_ARTIFACT")
    validate_chain(entries, allowed_events=SAS_MATH_EVENT_TYPES)
    expected_order = [
        "SAS_MATH_BOOT",
        "SAS_MATH_ROOT_MANIFEST_WRITTEN",
        "SAS_MATH_ENABLE_PRESENT",
        "SAS_MATH_CONJECTURE_GEN_DONE",
        "SAS_MATH_CONJECTURE_SELECTED",
        "SAS_MATH_BASELINE_READY",
        "SAS_MATH_CANDIDATE_PROPOSED",
        "SAS_MATH_FINGERPRINT_DONE",
        "SAS_MATH_EVAL_DEV_DONE",
        "SAS_MATH_SELECTED_FOR_HELDOUT",
        "SAS_MATH_EVAL_HELDOUT_DONE",
        "SAS_MATH_NOVELTY_DONE",
        "SAS_MATH_PROMOTION_WRITTEN",
        "SAS_MATH_SHUTDOWN",
    ]
    idx = 0
    for entry in entries:
        if idx < len(expected_order) and entry.get("event_type") == expected_order[idx]:
            idx += 1
    if idx < len(expected_order):
        _fail("LEDGER_EVENT_MISSING")

    # Load pack + allowlist
    pack = _load_json(config_dir / "rsi_sas_math_pack_v1.json")
    _require_schema(pack, "rsi_sas_math_pack_v1")
    allowlist = _load_json(config_dir / "sas_math_policy_allowlist_v1.json")
    _require_schema(allowlist, "sas_math_policy_allowlist_v1")

    toolchains = _load_toolchains(config_dir, pack)
    if not toolchains:
        _fail("MISSING_ARTIFACT")

    constants = _load_constants()

    # Conjecture bundle + receipts
    conj_dir = state_dir / "conjectures"
    bundle_paths = list((conj_dir / "bundles").glob("sha256_*.sas_conjecture_bundle_v2.json"))
    if not bundle_paths:
        _fail("CONJECTURE_BUNDLE_MISSING")
    bundle = _load_json(bundle_paths[0])
    _require_schema(bundle, "sas_conjecture_bundle_v2")
    bundle_payload = dict(bundle)
    bundle_payload.pop("bundle_id", None)
    bundle_hash = sha256_prefixed(canon_bytes(bundle_payload))
    if bundle.get("bundle_id") != bundle_hash:
        _fail("CANON_HASH_MISMATCH")
    if not bundle_paths[0].name.startswith(f"sha256_{bundle_hash.split(':',1)[1]}"):
        _fail("CANON_HASH_MISMATCH")

    receipt_paths = list((conj_dir / "receipts").glob("sha256_*.sas_conjecture_gen_receipt_v2.json"))
    if not receipt_paths:
        _fail("CONJECTURE_GEN_RECEIPT_MISSING")
    gen_receipt = _load_json(receipt_paths[0])
    _require_schema(gen_receipt, "sas_conjecture_gen_receipt_v2")
    receipt_payload = dict(gen_receipt)
    receipt_payload.pop("receipt_id", None)
    receipt_hash = sha256_prefixed(canon_bytes(receipt_payload))
    if gen_receipt.get("receipt_id") != receipt_hash:
        _fail("CANON_HASH_MISMATCH")

    gen_cfg = _load_json(config_dir / "sas_conjecture_gen_config_v2.json")
    sel_policy = _load_json(config_dir / "sas_conjecture_selection_policy_v2.json")
    gen_cfg_hash = sha256_prefixed(canon_bytes(gen_cfg))
    sel_policy_hash = sha256_prefixed(canon_bytes(sel_policy))

    if constants.get("sas_math.conjecture_gen_config_hash") != gen_cfg_hash:
        _fail("CONJECTURE_GEN_CONFIG_DRIFT")
    if constants.get("sas_math.selection_policy_hash") != sel_policy_hash:
        _fail("CONJECTURE_SELECTION_POLICY_MISMATCH")

    allowed_ops = constants.get("sas_math.allowed_ops")
    if isinstance(allowed_ops, list):
        if sorted(str(x) for x in allowed_ops) != sorted(ALL_OPS):
            _fail("SCHEMA_INVALID")

    triviality_methods = constants.get("sas_math.triviality_methods")
    if isinstance(triviality_methods, list):
        if [str(x) for x in triviality_methods] != ["rfl", "simp_core", "simp_algebra", "one_lemma"]:
            _fail("SCHEMA_INVALID")

    pack_hash = sha256_prefixed(canon_bytes(pack))
    expected_seed = compute_conjecture_seed(pack_hash=pack_hash, attempt_index=0)
    if gen_receipt.get("generator_seed") != expected_seed:
        _fail("CONJECTURE_GEN_SEED_MISMATCH")
    if gen_receipt.get("bundle_hash") != bundle_hash:
        _fail("CONJECTURE_BUNDLE_MISSING")
    if gen_receipt.get("generator_config_hash") != gen_cfg_hash:
        _fail("CONJECTURE_GEN_CONFIG_DRIFT")
    if gen_receipt.get("generator_version") != "sas_conjecture_gen_v2":
        _fail("SCHEMA_INVALID")

    toolchain_hashes = {compute_manifest_hash(m) for m in toolchains.values()}
    if gen_receipt.get("toolchain_hash") not in toolchain_hashes:
        _fail("CONJECTURE_GEN_TOOLCHAIN_DRIFT")
    pinned_toolchains = constants.get("sas_math.toolchain_manifest_hashes")
    if isinstance(pinned_toolchains, list) and pinned_toolchains:
        pinned = {str(x) for x in pinned_toolchains}
        if str(gen_receipt.get("toolchain_hash")) not in pinned:
            _fail("CONJECTURE_GEN_TOOLCHAIN_DRIFT")
    if bool(gen_receipt.get("network_used")):
        _fail("CONJECTURE_GEN_NETWORK_USED")

    # Validate conjectures
    conj_by_id: dict[str, dict[str, Any]] = {}
    for item in bundle.get("conjectures") or []:
        conj_id = item.get("conjecture_id")
        if not isinstance(conj_id, str):
            _fail("CONJECTURE_ID_MISMATCH")
        ir_path = conj_dir / "ir" / f"sha256_{conj_id.split(':',1)[1]}.sas_conjecture_ir_v2.json"
        if not ir_path.exists():
            _fail("CONJECTURE_ID_MISMATCH")
        ir = _load_json(ir_path)
        validate_conjecture_ir(ir)
        if compute_conjecture_id(ir) != conj_id:
            _fail("CONJECTURE_ID_MISMATCH")
        fingerprint = compute_conjecture_fingerprint(ir)
        if item.get("fingerprint_hash") != fingerprint.get("fingerprint_hash"):
            _fail("CONJECTURE_FINGERPRINT_MISMATCH")

        metrics = compute_metrics(ir)
        if item.get("metrics") != metrics:
            _fail("CONJECTURE_METRICS_MISMATCH")

        statement_text = render_statement(ir).strip() + "\n"
        statement_hash = sha256_prefixed(statement_text.encode("utf-8"))
        if item.get("statement_hash") != statement_hash:
            _fail("CONJECTURE_STATEMENT_HASH_MISMATCH")
        statement_path = state_dir / "math" / "problems" / f"sha256_{statement_hash.split(':',1)[1]}.statement.txt"
        if not statement_path.exists():
            _fail("CONJECTURE_STATEMENT_HASH_MISMATCH")
        if sha256_prefixed(statement_path.read_bytes()) != statement_hash:
            _fail("CONJECTURE_STATEMENT_HASH_MISMATCH")

        # Triviality checks
        checks = item.get("triviality_checks") or []
        rejection_reason = str(item.get("rejection_reason") or "")
        status = str(item.get("status") or "")

        if rejection_reason in {"SYNTAX_TAUTOLOGY", "PATTERN_TRIVIAL"}:
            if status != "TRIVIAL_REJECTED":
                _fail("CONJECTURE_TRIVIALITY_CHECK_MISSING")
        else:
            if not isinstance(checks, list) or len(checks) != 4:
                _fail("CONJECTURE_TRIVIALITY_CHECK_MISSING")
            seen_methods = {c.get("method") for c in checks if isinstance(c, dict)}
            if seen_methods != {"rfl", "simp_core", "simp_algebra", "one_lemma"}:
                _fail("CONJECTURE_TRIVIALITY_CHECK_MISSING")
            any_pass = False
            for check in checks:
                if not isinstance(check, dict):
                    _fail("CONJECTURE_TRIVIALITY_CHECK_MISSING")
                sealed_hash = check.get("sealed_receipt_sha256")
                if not isinstance(sealed_hash, str):
                    _fail("CONJECTURE_TRIVIALITY_CHECK_MISSING")
                sealed_path = conj_dir / "sealed" / f"sha256_{sealed_hash.split(':',1)[1]}.sealed_proof_check_receipt_v1.json"
                if not sealed_path.exists():
                    _fail("CONJECTURE_TRIVIALITY_CHECK_MISSING")
                sealed = load_sealed_receipt(sealed_path)
                if compute_sealed_receipt_hash(sealed) != sealed_hash:
                    _fail("CONJECTURE_TRIVIALITY_CHECK_MISSING")
                if sealed.get("result") != check.get("result"):
                    _fail("CONJECTURE_TRIVIALITY_CHECK_MISSING")
                if sealed.get("result") == "PASS":
                    any_pass = True

                stdout_hash = sealed.get("stdout_hash")
                stderr_hash = sealed.get("stderr_hash")
                if isinstance(stdout_hash, str) and isinstance(stderr_hash, str):
                    stdout_path = conj_dir / "logs" / f"sha256_{stdout_hash.split(':',1)[1]}.stdout.log"
                    stderr_path = conj_dir / "logs" / f"sha256_{stderr_hash.split(':',1)[1]}.stderr.log"
                    if not stdout_path.exists() or not stderr_path.exists():
                        _fail("CONJECTURE_TRIVIALITY_CHECK_MISSING")

                sandbox_hash = sealed.get("sandbox_manifest_hash")
                if isinstance(sandbox_hash, str):
                    sandbox_path = conj_dir / "sandbox" / f"sha256_{sandbox_hash.split(':',1)[1]}.sandbox_manifest_v1.json"
                    if not sandbox_path.exists():
                        _fail("CONJECTURE_TRIVIALITY_CHECK_MISSING")
                    sandbox = _load_json(sandbox_path)
                    if sandbox.get("network") != "NONE":
                        _fail("CONJECTURE_GEN_NETWORK_USED")

            if any_pass:
                if status != "TRIVIAL_REJECTED" or rejection_reason != "TRIVIAL_SOLVED":
                    _fail("CONJECTURE_TRIVIALITY_CHECK_MISSING")
            else:
                op_counts = metrics.get("op_counts") or {}
                novelty_ok = novelty_gate_pass(op_counts)
                if novelty_ok:
                    if status != "ACCEPTED" or rejection_reason != "":
                        _fail("CONJECTURE_TRIVIALITY_CHECK_MISSING")
                else:
                    if status != "TRIVIAL_REJECTED" or rejection_reason != "NOVELTY_GATE_FAIL":
                        _fail("CONJECTURE_TRIVIALITY_CHECK_MISSING")

        conj_by_id[conj_id] = item

    # Selection receipt
    sel_paths = list((conj_dir / "selection").glob("sha256_*.sas_conjecture_selection_receipt_v2.json"))
    if not sel_paths:
        _fail("CONJECTURE_SELECTION_RECEIPT_MISSING")
    selection = _load_json(sel_paths[0])
    _require_schema(selection, "sas_conjecture_selection_receipt_v2")
    sel_payload = dict(selection)
    sel_payload.pop("receipt_id", None)
    sel_hash = sha256_prefixed(canon_bytes(sel_payload))
    if selection.get("receipt_id") != sel_hash:
        _fail("CANON_HASH_MISMATCH")
    if selection.get("selection_policy_hash") != sel_policy_hash:
        _fail("CONJECTURE_SELECTION_POLICY_MISMATCH")

    selected_id = selection.get("selected_conjecture_id")
    if selected_id not in conj_by_id:
        _fail("CONJECTURE_NOT_IN_BUNDLE")
    selected = conj_by_id[selected_id]
    if selected.get("status") == "TRIVIAL_REJECTED":
        _fail("CONJECTURE_TRIVIALITY_REJECTED_BUT_SELECTED")

    expected_selected = select_conjecture(list(conj_by_id.values()))
    if expected_selected.get("conjecture_id") != selected_id:
        _fail("CONJECTURE_SELECTION_METRICS_MISMATCH")

    metrics = selected.get("metrics") or {}
    sel_metrics = selection.get("selection_metrics") or {}
    if sel_metrics.get("node_count") != metrics.get("node_count"):
        _fail("CONJECTURE_SELECTION_METRICS_MISMATCH")
    if sel_metrics.get("binder_count") != metrics.get("binder_count"):
        _fail("CONJECTURE_SELECTION_METRICS_MISMATCH")
    if sel_metrics.get("depth") != metrics.get("depth"):
        _fail("CONJECTURE_SELECTION_METRICS_MISMATCH")
    if sel_metrics.get("op_counts") != metrics.get("op_counts"):
        _fail("CONJECTURE_SELECTION_METRICS_MISMATCH")
    if sel_metrics.get("score") != compute_score(metrics):
        _fail("CONJECTURE_SELECTION_METRICS_MISMATCH")

    # Policies + fingerprints
    policy_dir = state_dir / "policy" / "candidates"
    fingerprint_dir = state_dir / "policy" / "fingerprints"
    if not policy_dir.exists():
        _fail("MISSING_ARTIFACT")
    for path in policy_dir.glob("sha256_*.sas_math_policy_ir_v1.json"):
        policy_ir = _load_json(path)
        _require_schema(policy_ir, "sas_math_policy_ir_v1")
        policy_id = compute_policy_id(policy_ir)
        if policy_ir.get("policy_id") != policy_id:
            _fail("POLICY_ID_MISMATCH")
        _enforce_allowlist(policy_ir, allowlist)
        fingerprint = compute_fingerprint(policy_ir)
        fingerprint_hash = sha256_prefixed(canon_bytes(fingerprint))
        fp_path = fingerprint_dir / f"sha256_{fingerprint_hash.split(':',1)[1]}.sas_math_policy_fingerprint_v1.json"
        if not fp_path.exists():
            _fail("MISSING_ARTIFACT")
        fp_loaded = _load_json(fp_path)
        _require_schema(fp_loaded, "sas_math_policy_fingerprint_v1")
        if fp_loaded.get("fingerprint_hash") != fingerprint.get("fingerprint_hash"):
            _fail("FINGERPRINT_HASH_MISMATCH")

    # Eval reports
    eval_reports_dir = state_dir / "eval" / "reports"
    eval_reports: dict[str, dict[str, Any]] = {}
    for path in eval_reports_dir.glob("sha256_*.sas_math_eval_report_v1.json"):
        report = _load_json(path)
        _require_schema(report, "sas_math_eval_report_v1")
        eval_reports[path.name] = report
        attempt_hashes = report.get("attempt_receipt_hashes") or []
        receipts = [_load_attempt_receipt_by_hash(state_dir, h) for h in attempt_hashes]
        for receipt in receipts:
            _validate_attempt_receipt(state_dir, receipt, toolchains)
        recomputed = compute_eval_report(
            policy_id=str(report.get("policy_id")),
            eval_kind=str(report.get("eval_kind")),
            attempt_receipts=receipts,
        )
        if int(recomputed.get("attempt_count")) != int(report.get("attempt_count")):
            _fail("EVAL_RECOMPUTE_MISMATCH")
        if int(recomputed.get("pass_count")) != int(report.get("pass_count")):
            _fail("EVAL_RECOMPUTE_MISMATCH")
        if int(recomputed.get("total_wall_ms")) != int(report.get("total_wall_ms")):
            _fail("EVAL_RECOMPUTE_MISMATCH")
        if _parse_q32(recomputed.get("utility_q32")) != _parse_q32(report.get("utility_q32")):
            _fail("EVAL_RECOMPUTE_MISMATCH")
        if _parse_q32(recomputed.get("capacity_eff_q32")) != _parse_q32(report.get("capacity_eff_q32")):
            _fail("EVAL_RECOMPUTE_MISMATCH")

    # Promotion bundle
    promo_dir = state_dir / "promotion"
    promo_paths = list(promo_dir.glob("sha256_*.sas_math_promotion_bundle_v1.json"))
    if not promo_paths:
        _fail("MISSING_ARTIFACT")
    promo = _load_json(promo_paths[0])
    _require_schema(promo, "sas_math_promotion_bundle_v1")
    payload = dict(promo)
    payload.pop("bundle_id", None)
    promo_hash = sha256_prefixed(canon_bytes(payload))
    if promo.get("bundle_id") != promo_hash:
        _fail("CANON_HASH_MISMATCH")
    if not promo_paths[0].name.startswith(f"sha256_{promo_hash.split(':',1)[1]}"):
        _fail("CANON_HASH_MISMATCH")

    # Check Q32 gates
    min_util = _parse_q32(promo.get("min_utility_delta_q32"))
    min_eff = _parse_q32(promo.get("min_efficiency_delta_q32"))
    max_reg = _parse_q32(promo.get("max_utility_regression_q32"))
    min_nov = _parse_q32(promo.get("min_novelty_q32"))
    base_util = _parse_q32(promo.get("baseline_utility_q32"))
    cand_util = _parse_q32(promo.get("candidate_utility_q32"))
    base_eff = _parse_q32(promo.get("baseline_capacity_efficiency_q32"))
    cand_eff = _parse_q32(promo.get("candidate_capacity_efficiency_q32"))
    novelty_q = _parse_q32(promo.get("novelty_score_q32"))

    # Recompute novelty (binary)
    if promo.get("baseline_fingerprint_hash") == promo.get("candidate_fingerprint_hash"):
        expected_novelty = 0
    else:
        expected_novelty = Q
    if novelty_q != expected_novelty:
        _fail("NOVELTY_SCORE_MISMATCH")
    if bool(promo.get("require_novelty")) and novelty_q < min_nov:
        _fail("NOVELTY_REQUIRED_NOT_MET")

    # Recompute dominance decision
    delta_u = cand_util - base_util
    delta_e = cand_eff - base_eff
    reasons: list[str] = []
    if delta_u < -max_reg:
        reasons.append("UTILITY_REGRESSION_EXCEEDS_MAX")
    if not (delta_u >= min_util or delta_e >= min_eff):
        reasons.append("DOMINANCE_NOT_MET")
    if bool(promo.get("require_novelty")) and novelty_q < min_nov:
        reasons.append("NOVELTY_REQUIRED_NOT_MET")
    expected_pass = len(reasons) == 0
    decision = promo.get("acceptance_decision") or {}
    if bool(decision.get("pass")) != expected_pass:
        _fail("DOMINANCE_RECOMPUTE_MISMATCH")

    # Improvement evidence
    baseline_report_hash = promo.get("baseline_eval_report_sha256")
    cand_report_hash = promo.get("candidate_eval_report_sha256_heldout")
    if not isinstance(baseline_report_hash, str) or not isinstance(cand_report_hash, str):
        _fail("SCHEMA_INVALID")
    baseline_report_path = eval_reports_dir / f"sha256_{baseline_report_hash.split(':',1)[1]}.sas_math_eval_report_v1.json"
    cand_report_path = eval_reports_dir / f"sha256_{cand_report_hash.split(':',1)[1]}.sas_math_eval_report_v1.json"
    if not baseline_report_path.exists() or not cand_report_path.exists():
        _fail("MISSING_ARTIFACT")
    baseline_report = _load_json(baseline_report_path)
    cand_report = _load_json(cand_report_path)

    baseline_receipts = [_load_attempt_receipt_by_hash(state_dir, h) for h in baseline_report.get("attempt_receipt_hashes") or []]
    candidate_receipts = [_load_attempt_receipt_by_hash(state_dir, h) for h in cand_report.get("attempt_receipt_hashes") or []]

    base_pass: dict[str, bool] = {}
    base_receipt_for: dict[str, dict[str, Any]] = {}
    for rec in baseline_receipts:
        pid = rec.get("problem_id")
        if not isinstance(pid, str):
            continue
        base_receipt_for.setdefault(pid, rec)
        if rec.get("result") == "PASS":
            base_pass[pid] = True

    cand_pass: dict[str, bool] = {}
    cand_receipt_for: dict[str, dict[str, Any]] = {}
    for rec in candidate_receipts:
        pid = rec.get("problem_id")
        if not isinstance(pid, str):
            continue
        cand_receipt_for.setdefault(pid, rec)
        if rec.get("result") == "PASS":
            cand_pass[pid] = True
            cand_receipt_for[pid] = rec

    improved = sorted(pid for pid in cand_pass.keys() if not base_pass.get(pid))
    if not improved:
        _fail("NO_IMPROVEMENT")

    if sorted(promo.get("improved_problem_ids") or []) != improved:
        _fail("IMPROVEMENT_MISMATCH")

    evidence = promo.get("improvement_evidence") or []
    if not isinstance(evidence, list) or len(evidence) < 1:
        _fail("IMPROVEMENT_MISMATCH")
    evidence_by_problem = {e.get("problem_id"): e for e in evidence if isinstance(e, dict)}
    for pid in improved:
        if pid not in evidence_by_problem:
            _fail("IMPROVEMENT_MISMATCH")
        base_rec = base_receipt_for.get(pid)
        cand_rec = cand_receipt_for.get(pid)
        if base_rec is None or cand_rec is None:
            _fail("IMPROVEMENT_MISMATCH")
        base_hash = compute_attempt_receipt_hash(base_rec)
        cand_hash = compute_attempt_receipt_hash(cand_rec)
        ev = evidence_by_problem[pid]
        if ev.get("baseline_attempt_receipt_sha256") != base_hash:
            _fail("IMPROVEMENT_MISMATCH")
        if ev.get("candidate_attempt_receipt_sha256") != cand_hash:
            _fail("IMPROVEMENT_MISMATCH")
        if ev.get("candidate_sealed_receipt_sha256") != cand_rec.get("sealed_proof_check_receipt_hash"):
            _fail("IMPROVEMENT_MISMATCH")
        if ev.get("candidate_proof_artifact_hash") != cand_rec.get("proof_artifact_hash"):
            _fail("IMPROVEMENT_MISMATCH")

    return {"status": "VALID"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify RSI SAS-MATH v11.2")
    parser.add_argument("--sas_math_state_dir", required=True)
    parser.add_argument("--mode", default="prefix", choices=["prefix", "full"])
    args = parser.parse_args()
    try:
        verify(Path(args.sas_math_state_dir), mode=args.mode)
        print("VALID")
    except CanonError as exc:
        print(f"INVALID: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
