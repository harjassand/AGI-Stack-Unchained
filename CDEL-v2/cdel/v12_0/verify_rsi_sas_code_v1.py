"""Verifier for RSI SAS-CODE v12.0."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from ..v11_1.path_canon_v1 import canon_root_v1_for, PathCanonError
from ..v11_1.fixed_q32_v1 import parse_q32, Q32Error
from ..v8_0.math_toolchain import compute_manifest_hash, load_toolchain_manifest
from ..v8_0.sealed_proofcheck import compute_sealed_receipt_hash, load_sealed_receipt
from .sas_code_ir_v1 import validate_ir
from .sas_code_workmeter_v1 import compute_perf_report, execute_algorithm, is_perm, is_sorted
from .sas_code_proof_task_v1 import (
    check_required_symbols,
    nontriviality_issues,
    scan_preamble_tamper,
    scan_forbidden_tokens,
    scan_semantic_tamper,
    sealed_proof_check_receipt,
)
from .sas_code_selection_v1 import novelty_score_q32
from .sas_code_ledger import SAS_CODE_EVENT_TYPES, load_ledger, validate_chain

try:
    from jsonschema import Draft202012Validator
except Exception:  # pragma: no cover - optional dependency
    Draft202012Validator = None


class SASCodeError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise SASCodeError(reason)


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
    schema_path = schema_dir / f"{schema_name}.jsonschema"
    if not schema_path.exists():
        _fail("INVALID:SCHEMA_FAIL")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(obj)


def _require_sha256(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        _fail("INVALID:SCHEMA_FAIL")
    return value


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]

PREAMBLE_FORBIDDEN_TOKENS = [
    "List.mergeSort",
    "List.sort",
    "Array.qsort",
    "Init.Data.List.Sort",
    "by decide",
]
PREAMBLE_FORBIDDEN_REGEX = re.compile(r"Std\.[A-Za-z0-9_]*Sort")


def _strip_lean_comments(text: str) -> str:
    text = re.sub(r"/-.*?-/", "", text, flags=re.S)
    text = re.sub(r"--.*", "", text)
    return text


def _scan_preamble_forbidden(text: str) -> str | None:
    stripped = _strip_lean_comments(text)
    for token in PREAMBLE_FORBIDDEN_TOKENS:
        if token in stripped:
            return token
    match = PREAMBLE_FORBIDDEN_REGEX.search(stripped)
    if match:
        return match.group(0)
    return None


def _extract_def_block(text: str, name: str) -> str | None:
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.strip().startswith(f"def {name}"):
            start = idx
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped.startswith("def ") or stripped.startswith("theorem ") or stripped.startswith("lemma "):
            end = j
            break
    return "\n".join(lines[start:end])


def _verify_preamble_semantics(text: str) -> None:
    stripped = _strip_lean_comments(text)
    required = [
        "def bubblePass",
        "def bubbleIter",
        "def bubbleSort",
        "def split",
        "def merge",
        "def mergeSort",
        "def sort_ref",
        "def sort_cand",
    ]
    for token in required:
        if token not in stripped:
            _fail("INVALID:PREAMBLE_SEMANTICS_TAMPER")
    bubble_block = _extract_def_block(stripped, "bubbleSort")
    if bubble_block is None or "bubbleIter" not in bubble_block:
        _fail("INVALID:PREAMBLE_SEMANTICS_TAMPER")
    bubble_iter_block = _extract_def_block(stripped, "bubbleIter")
    if bubble_iter_block is None or "bubblePass" not in bubble_iter_block:
        _fail("INVALID:PREAMBLE_SEMANTICS_TAMPER")
    if bubble_iter_block is not None and "mergeSort" in bubble_iter_block:
        _fail("INVALID:PREAMBLE_SEMANTICS_TAMPER")
    merge_block = _extract_def_block(stripped, "mergeSort")
    if merge_block is None or "split" not in merge_block or "merge" not in merge_block:
        _fail("INVALID:PREAMBLE_SEMANTICS_TAMPER")
    sort_ref_block = _extract_def_block(stripped, "sort_ref")
    if sort_ref_block is None or "bubbleSort" not in sort_ref_block:
        _fail("INVALID:PREAMBLE_SEMANTICS_TAMPER")
    sort_cand_block = _extract_def_block(stripped, "sort_cand")
    if sort_cand_block is None or "mergeSort" not in sort_cand_block:
        _fail("INVALID:PREAMBLE_SEMANTICS_TAMPER")


def _verify_root_manifest(state_dir: Path) -> None:
    health_dir = state_dir / "health"
    manifests = list(health_dir.glob("sha256_*.sas_root_manifest_v1.json"))
    if not manifests:
        _fail("INVALID:MISSING_ARTIFACT")
    manifest_path = manifests[0]
    manifest = _load_json(manifest_path)
    _require_schema(manifest, "sas_root_manifest_v1")
    try:
        expected = canon_root_v1_for(str(manifest.get("agi_root_raw", "")), "rsi_sas_code_v12_0")
    except PathCanonError as exc:
        if str(exc) == "CANON_PATH_WHITESPACE":
            _fail("INVALID:CANON_PATH_WHITESPACE")
        _fail("INVALID:SCHEMA_FAIL")
    for key in ["agi_root_raw", "agi_root_stripped", "agi_root_canon", "was_trimmed", "sas_root_canon", "canon_method"]:
        if manifest.get(key) != expected.get(key):
            _fail("INVALID:HASH_MISMATCH")
    agi_root_canon = str(expected.get("agi_root_canon"))
    sas_root_canon = str(expected.get("sas_root_canon"))
    if str(state_dir.parent.resolve()) != sas_root_canon:
        _fail("INVALID:HASH_MISMATCH")
    if manifest.get("agi_root_canon_hash") != sha256_prefixed(agi_root_canon.encode("utf-8")):
        _fail("INVALID:HASH_MISMATCH")
    if manifest.get("sas_root_canon_hash") != sha256_prefixed(sas_root_canon.encode("utf-8")):
        _fail("INVALID:HASH_MISMATCH")
    manifest_hash = sha256_prefixed(canon_bytes(manifest))
    if not manifest_path.name.startswith(f"sha256_{manifest_hash.split(':',1)[1]}"):
        _fail("INVALID:HASH_MISMATCH")


def _require_enable_files(state_dir: Path) -> None:
    control = state_dir / "control"
    if not (control / "ENABLE_RESEARCH").exists():
        _fail("INVALID:MISSING_ENABLE")
    if not (control / "ENABLE_SAS_CODE").exists():
        _fail("INVALID:MISSING_ENABLE")
    if not (control / "SAS_CODE_LEASE.json").exists():
        _fail("INVALID:MISSING_ENABLE")


def _load_suitepack(config_dir: Path, name: str, schema_dir: Path) -> dict[str, Any]:
    path = config_dir / name
    if not path.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    suite = _load_json(path)
    _require_schema(suite, "sas_code_suitepack_v1")
    _validate_jsonschema(suite, "sas_code_suitepack_v1", schema_dir) if (schema_dir / "sas_code_suitepack_v1.jsonschema").exists() else None
    suite_hash = sha256_prefixed(canon_bytes(suite))
    suite["suitepack_hash"] = suite_hash
    return suite


def _load_ir(state_dir: Path, algo_id: str, schema_dir: Path) -> dict[str, Any]:
    ir_path = state_dir / "code" / "candidates" / "ir" / f"sha256_{algo_id.split(':',1)[1]}.sas_code_ir_v1.json"
    if not ir_path.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    ir = _load_json(ir_path)
    _require_schema(ir, "sas_code_ir_v1")
    _validate_jsonschema(ir, "sas_code_ir_v1", schema_dir)
    validate_ir(ir)
    if not ir_path.name.startswith(f"sha256_{algo_id.split(':',1)[1]}"):
        _fail("INVALID:HASH_MISMATCH")
    return ir


def _load_perf_report(state_dir: Path, report_hash: str, schema_dir: Path) -> dict[str, Any]:
    perf_dir = state_dir / "eval" / "perf"
    path = perf_dir / f"sha256_{report_hash.split(':',1)[1]}.sas_code_perf_report_v1.json"
    if not path.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    report = _load_json(path)
    _require_schema(report, "sas_code_perf_report_v1")
    _validate_jsonschema(report, "sas_code_perf_report_v1", schema_dir)
    expected_hash = sha256_prefixed(canon_bytes(report))
    if expected_hash != report_hash:
        _fail("INVALID:HASH_MISMATCH")
    return report


def _load_attempt_receipt(state_dir: Path, receipt_hash: str, schema_dir: Path) -> dict[str, Any]:
    receipts_dir = state_dir / "code" / "attempts" / "receipts"
    path = receipts_dir / f"sha256_{receipt_hash.split(':',1)[1]}.sas_code_attempt_receipt_v1.json"
    if not path.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    receipt = _load_json(path)
    _require_schema(receipt, "sas_code_attempt_receipt_v1")
    _validate_jsonschema(receipt, "sas_code_attempt_receipt_v1", schema_dir)
    expected_hash = sha256_prefixed(canon_bytes(receipt))
    if expected_hash != receipt_hash:
        _fail("INVALID:HASH_MISMATCH")
    return receipt


def _load_pack_config(state_dir: Path) -> dict[str, Any]:
    config_dir = state_dir.parent / "config"
    pack_path = config_dir / "rsi_sas_code_pack_v1.json"
    if not pack_path.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    pack = _load_json(pack_path)
    if not isinstance(pack, dict) or pack.get("schema_version") != "rsi_sas_code_pack_v1":
        _fail("INVALID:SCHEMA_FAIL")
    return pack


def _verify_toolchain_manifest(pack: dict[str, Any], config_dir: Path) -> tuple[dict[str, Any], str]:
    relpath = pack.get("toolchain_manifest_relpath")
    expected_hash = pack.get("toolchain_manifest_hash")
    if not isinstance(relpath, str) or not relpath:
        _fail("INVALID:SCHEMA_FAIL")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_hash):
        _fail("INVALID:SCHEMA_FAIL")
    toolchain_path = config_dir / relpath
    if not toolchain_path.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    toolchain_manifest = load_toolchain_manifest(toolchain_path)
    toolchain_manifest_hash = compute_manifest_hash(toolchain_manifest)
    if toolchain_manifest_hash != expected_hash:
        _fail("INVALID:TOOLCHAIN_MANIFEST_HASH_MISMATCH")
    invocation_template = toolchain_manifest.get("invocation_template")
    if (
        not isinstance(invocation_template, list)
        or len(invocation_template) != 2
        or not all(isinstance(item, str) for item in invocation_template)
    ):
        _fail("INVALID:TOOLCHAIN_MANIFEST_INVALID")
    if invocation_template[1] != "{entrypoint}":
        _fail("INVALID:TOOLCHAIN_MANIFEST_INVALID")
    tool_path = Path(invocation_template[0])
    if not tool_path.is_absolute() or tool_path.name != "lean":
        _fail("INVALID:TOOLCHAIN_MANIFEST_INVALID")
    return toolchain_manifest, toolchain_manifest_hash


def _verify_perf_policy(pack: dict[str, Any], config_dir: Path) -> dict[str, Any]:
    relpath = pack.get("perf_policy_relpath")
    expected_hash = pack.get("perf_policy_hash")
    if not isinstance(relpath, str) or not relpath:
        _fail("INVALID:SCHEMA_FAIL")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_hash):
        _fail("INVALID:SCHEMA_FAIL")
    perf_policy_path = config_dir / relpath
    if not perf_policy_path.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    perf_policy = _load_json(perf_policy_path)
    if not isinstance(perf_policy, dict) or perf_policy.get("schema_version") != "sas_code_perf_policy_v1":
        _fail("INVALID:SCHEMA_FAIL")
    actual_hash = sha256_prefixed(canon_bytes(perf_policy))
    if actual_hash != expected_hash:
        _fail("INVALID:PERF_POLICY_HASH_MISMATCH")

    def _require_policy_int(field: str, expected: int) -> None:
        value = perf_policy.get(field)
        if not isinstance(value, int) or value != expected:
            _fail(f"INVALID:PERF_POLICY_FORBIDDEN_VALUE:{field}")

    def _require_policy_bool(field: str, expected: bool) -> None:
        value = perf_policy.get(field)
        if not isinstance(value, bool) or value is not expected:
            _fail(f"INVALID:PERF_POLICY_FORBIDDEN_VALUE:{field}")

    _require_policy_int("min_improvement_percent", 30)
    _require_policy_bool("require_scaling_sanity", True)
    _require_policy_int("insertion_shift_penalty_multiplier", 0)
    return perf_policy


def _verify_preamble(pack: dict[str, Any]) -> tuple[str, str]:
    relpath = pack.get("lean_preamble_relpath")
    expected_hash = pack.get("lean_preamble_sha256")
    if not isinstance(relpath, str) or not relpath:
        _fail("INVALID:SCHEMA_FAIL")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_hash):
        _fail("INVALID:SCHEMA_FAIL")
    preamble_path = _repo_root() / relpath
    if not preamble_path.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    actual_hash = sha256_prefixed(preamble_path.read_bytes())
    if actual_hash != expected_hash:
        _fail("INVALID:PREAMBLE_HASH_MISMATCH")
    preamble_text = preamble_path.read_text(encoding="utf-8")
    if scan_preamble_tamper(preamble_text):
        _fail("INVALID:PREAMBLE_SEMANTICS_TAMPER")
    forbidden = _scan_preamble_forbidden(preamble_text)
    if forbidden:
        _fail(f"INVALID:PREAMBLE_FORBIDDEN_TOKEN:{forbidden}")
    _verify_preamble_semantics(preamble_text)
    return relpath, expected_hash


def _verify_proof_artifact(state_dir: Path, proof_hash: str) -> str:
    proofs_dir = state_dir / "code" / "attempts" / "proofs"
    proof_path = proofs_dir / f"sha256_{proof_hash.split(':',1)[1]}.proof.lean"
    if not proof_path.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    proof_bytes = proof_path.read_bytes()
    if sha256_prefixed(proof_bytes) != proof_hash:
        _fail("INVALID:HASH_MISMATCH")
    return proof_bytes.decode("utf-8")


def _verify_sealed_receipt(state_dir: Path, receipt_hash: str) -> dict[str, Any]:
    sealed_dir = state_dir / "code" / "attempts" / "sealed"
    path = sealed_dir / f"sha256_{receipt_hash.split(':',1)[1]}.sealed_proof_check_receipt_v1.json"
    if not path.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    receipt = load_sealed_receipt(path)
    expected = compute_sealed_receipt_hash(receipt)
    if expected != receipt_hash:
        _fail("INVALID:HASH_MISMATCH")
    return receipt


def _verify_semantics_tamper(text: str) -> None:
    hits = scan_semantic_tamper(text)
    if hits:
        _fail("INVALID:PROOF_SEMANTICS_TAMPER")


def _verify_forbidden_tokens(text: str) -> None:
    hits = scan_forbidden_tokens(text)
    if hits:
        _fail("INVALID:FORBIDDEN_TOKEN")


def _verify_required_symbols(text: str) -> None:
    missing = check_required_symbols(text)
    if missing:
        _fail("INVALID:PROOF_REJECTED")


def _verify_nontrivial_proof(text: str) -> None:
    issues = nontriviality_issues(text)
    if issues:
        _fail("INVALID:PROOF_REJECTED")


def _verify_algorithm_correctness(
    *,
    suitepack: dict[str, Any],
    baseline_algo_kind: str,
    candidate_algo_kind: str,
) -> None:
    cases = suitepack.get("cases") or []
    for case in cases:
        xs = case.get("xs") or []
        if not isinstance(xs, list):
            continue
        base_out, _ = execute_algorithm(baseline_algo_kind, xs)
        cand_out, _ = execute_algorithm(candidate_algo_kind, xs)
        if not is_sorted(base_out):
            _fail("INVALID:NOT_SORTED")
        if not is_perm(xs, base_out):
            _fail("INVALID:NOT_PERMUTATION")
        if base_out != cand_out:
            _fail("INVALID:OUTPUT_MISMATCH")


def _verify_selection(state_dir: Path, schema_dir: Path, candidate_algo_id: str) -> None:
    selection_dir = state_dir / "code" / "candidates" / "selection"
    receipts = list(selection_dir.glob("sha256_*.sas_code_selection_receipt_v1.json"))
    if not receipts:
        _fail("INVALID:MISSING_ARTIFACT")
    receipt = _load_json(receipts[0])
    _require_schema(receipt, "sas_code_selection_receipt_v1")
    _validate_jsonschema(receipt, "sas_code_selection_receipt_v1", schema_dir)
    if receipt.get("selected_algo_id") != candidate_algo_id:
        _fail("INVALID:HASH_MISMATCH")


def _verify_ledger(state_dir: Path) -> None:
    ledger_path = state_dir / "ledger" / "sas_code_synthesis_ledger_v1.jsonl"
    if not ledger_path.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    entries = load_ledger(ledger_path)
    validate_chain(entries, allowed_events=SAS_CODE_EVENT_TYPES)


def verify(state_dir: Path, *, mode: str = "full") -> None:
    del mode
    schema_dir = _repo_root() / "Genesis" / "schema" / "v12_0"
    _verify_root_manifest(state_dir)
    _require_enable_files(state_dir)
    _verify_ledger(state_dir)
    config_dir = state_dir.parent / "config"
    pack = _load_pack_config(state_dir)
    preamble_relpath, preamble_hash = _verify_preamble(pack)
    toolchain_manifest, toolchain_manifest_hash = _verify_toolchain_manifest(pack, config_dir)

    promo_dir = state_dir / "promotion"
    promo_paths = list(promo_dir.glob("sha256_*.sas_code_promotion_bundle_v1.json"))
    if not promo_paths:
        _fail("INVALID:MISSING_ARTIFACT")
    promo_path = promo_paths[0]
    promo = _load_json(promo_path)
    _require_schema(promo, "sas_code_promotion_bundle_v1")
    _validate_jsonschema(promo, "sas_code_promotion_bundle_v1", schema_dir)
    promo_hash = sha256_prefixed(canon_bytes(promo))
    if not promo_path.name.startswith(f"sha256_{promo_hash.split(':',1)[1]}"):
        _fail("INVALID:HASH_MISMATCH")

    baseline_algo_id = _require_sha256(promo.get("baseline_algo_id"))
    candidate_algo_id = _require_sha256(promo.get("candidate_algo_id"))
    problem_id = _require_sha256(promo.get("problem_id"))

    baseline_ir = _load_ir(state_dir, baseline_algo_id, schema_dir)
    cand_ir = _load_ir(state_dir, candidate_algo_id, schema_dir)

    # Structural novelty gate
    tags = cand_ir.get("tags") or []
    if cand_ir.get("algo_kind") == "BUBBLE_SORT_V1" or "divide_and_conquer" not in tags or "recursion" not in tags:
        _fail("INVALID:NOVELTY_FAIL")

    # Problem spec
    problem_dir = state_dir / "code" / "problems"
    prob_path = problem_dir / f"sha256_{problem_id.split(':',1)[1]}.sas_code_problem_spec_v1.json"
    if not prob_path.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    problem = _load_json(prob_path)
    _require_schema(problem, "sas_code_problem_spec_v1")
    _validate_jsonschema(problem, "sas_code_problem_spec_v1", schema_dir)
    if problem.get("baseline_algo_id") != baseline_algo_id or problem.get("candidate_algo_id") != candidate_algo_id:
        _fail("INVALID:HASH_MISMATCH")

    # Proof artifacts
    attempt_hash = _require_sha256(promo.get("candidate_attempt_receipt_sha256"))
    attempt = _load_attempt_receipt(state_dir, attempt_hash, schema_dir)
    if attempt.get("lean_preamble_sha256") != preamble_hash or attempt.get("lean_preamble_relpath") != preamble_relpath:
        _fail("INVALID:PREAMBLE_HASH_MISMATCH")
    if attempt.get("toolchain_id") != toolchain_manifest.get("toolchain_id"):
        _fail("INVALID:HASH_MISMATCH")
    if attempt.get("toolchain_manifest_hash") != toolchain_manifest_hash:
        _fail("INVALID:HASH_MISMATCH")
    proof_hash = _require_sha256(attempt.get("proof_artifact_hash"))
    sealed_hash = _require_sha256(attempt.get("sealed_proof_check_receipt_hash"))
    proof_text = _verify_proof_artifact(state_dir, proof_hash)
    _verify_semantics_tamper(proof_text)
    _verify_forbidden_tokens(proof_text)
    _verify_required_symbols(proof_text)
    _verify_nontrivial_proof(proof_text)
    sealed = _verify_sealed_receipt(state_dir, sealed_hash)
    if sealed.get("lean_preamble_sha256") not in (None, preamble_hash):
        _fail("INVALID:PREAMBLE_HASH_MISMATCH")
    if sealed.get("result") != "PASS" or attempt.get("result") != "PASS":
        _fail("INVALID:PROOF_REJECTED")

    # Re-run sealed proof check with Lean
    attempt_id = str(sealed.get("attempt_id"))
    work_dir = state_dir / "code" / "attempts" / "work" / "attempts" / f"sha256:{attempt_id.split(':',1)[1]}"
    expected_sealed = sealed_proof_check_receipt(
        toolchain_manifest=toolchain_manifest,
        problem_id=problem_id,
        attempt_id=attempt_id,
        proof_text=proof_text,
        lean_preamble_path=_repo_root() / preamble_relpath,
        lean_preamble_sha256=preamble_hash,
        work_dir=work_dir,
    )
    for key in ["exit_code", "stdout_hash", "stderr_hash"]:
        if expected_sealed.get(key) != sealed.get(key):
            _fail("INVALID:PROOF_REJECTED")

    # Perf reports + recompute
    config_dir = state_dir.parent / "config"
    suite_dev = _load_suitepack(config_dir, "sas_code_suitepack_dev_v1.json", schema_dir)
    suite_held = _load_suitepack(config_dir, "sas_code_suitepack_heldout_v1.json", schema_dir)

    _verify_algorithm_correctness(
        suitepack=suite_dev,
        baseline_algo_kind=baseline_ir.get("algo_kind"),
        candidate_algo_kind=cand_ir.get("algo_kind"),
    )
    _verify_algorithm_correctness(
        suitepack=suite_held,
        baseline_algo_kind=baseline_ir.get("algo_kind"),
        candidate_algo_kind=cand_ir.get("algo_kind"),
    )

    perf_dev_hash = _require_sha256(promo.get("perf_report_sha256_dev"))
    perf_held_hash = _require_sha256(promo.get("perf_report_sha256_heldout"))
    perf_dev = _load_perf_report(state_dir, perf_dev_hash, schema_dir)
    perf_held = _load_perf_report(state_dir, perf_held_hash, schema_dir)
    perf_policy = _verify_perf_policy(pack, config_dir)

    recomputed_dev = compute_perf_report(
        eval_kind="DEV",
        suitepack=suite_dev,
        baseline_algo_id=baseline_algo_id,
        baseline_algo_kind=baseline_ir.get("algo_kind"),
        candidate_algo_id=candidate_algo_id,
        candidate_algo_kind=cand_ir.get("algo_kind"),
        policy=perf_policy,
    )
    recomputed_held = compute_perf_report(
        eval_kind="HELDOUT",
        suitepack=suite_held,
        baseline_algo_id=baseline_algo_id,
        baseline_algo_kind="BUBBLE_SORT_V1",
        candidate_algo_id=candidate_algo_id,
        candidate_algo_kind=cand_ir.get("algo_kind"),
        policy=perf_policy,
    )

    # Match recomputed against stored
    if sha256_prefixed(canon_bytes(recomputed_dev)) != perf_dev_hash:
        _fail("INVALID:HASH_MISMATCH")
    if sha256_prefixed(canon_bytes(recomputed_held)) != perf_held_hash:
        _fail("INVALID:HASH_MISMATCH")

    if not perf_held.get("gate", {}).get("passed"):
        _fail("INVALID:NO_PERF_GAIN")

    # Novelty gate vs promotion bundle
    try:
        min_novelty = parse_q32(promo.get("min_novelty_q32"))
    except Q32Error:
        _fail("INVALID:SCHEMA_FAIL")
    novelty = parse_q32(novelty_score_q32(cand_ir))
    if promo.get("require_novelty") and novelty < min_novelty:
        _fail("INVALID:NOVELTY_FAIL")

    # selection receipt consistency
    _verify_selection(state_dir, schema_dir, candidate_algo_id)

    # Ensure eval reports exist
    eval_dir = state_dir / "eval" / "reports"
    if not list(eval_dir.glob("sha256_*.sas_code_eval_report_v1.json")):
        _fail("INVALID:MISSING_ARTIFACT")


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_sas_code_v1")
    parser.add_argument("--sas_code_state_dir", required=True)
    parser.add_argument("--mode", default="full")
    args = parser.parse_args()
    try:
        verify(Path(args.sas_code_state_dir), mode=args.mode)
    except Exception as exc:  # noqa: BLE001
        print(f"INVALID:{exc}")
        raise SystemExit(1)
    print("VALID")


if __name__ == "__main__":
    main()
