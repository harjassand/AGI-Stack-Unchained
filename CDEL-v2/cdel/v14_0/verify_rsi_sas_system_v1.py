"""Verifier for RSI SAS-System v14.0."""

from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import stat
import sys
import tarfile
import warnings
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from ..v8_0.sealed_proofcheck import compute_sealed_receipt_hash
from .sas_system_build_v1 import build_rust_from_ir, materialize_python_extension, regenerate_sources
from .sas_system_equivalence_v1 import run_equivalence
from .sas_system_extract_v1 import extract_reference_ir
from .sas_system_immutability_v1 import immutable_tree_snapshot
from .sas_system_ledger_v1 import load_ledger, validate_chain
from .sas_system_optimize_v1 import summarize_loops_v1
from .sas_system_perf_v1 import ir_step_cost_total
from .sas_system_proof_v1 import scan_forbidden_tokens, sealed_lean_check_receipt, validate_proof_shape

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


class SASSystemError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise SASSystemError(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema_dir() -> Path:
    return _repo_root() / "Genesis" / "schema" / "v14_0"


def _load_json(path: Path) -> Any:
    try:
        return load_canon_json(path)
    except Exception:
        _fail("INVALID:SCHEMA_FAIL")
    return {}


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


def _require_sha256(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        _fail("INVALID:SCHEMA_FAIL")
    return value


def _find_by_hash(dir_path: Path, suffix: str, sha256: str) -> Path:
    path = dir_path / f"sha256_{sha256.split(':',1)[1]}.{suffix}"
    if not path.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    return path


def _hash_name_ok(path: Path, payload: dict[str, Any], suffix: str) -> None:
    h = sha256_prefixed(canon_bytes(payload))
    expected = f"sha256_{h.split(':',1)[1]}.{suffix}"
    if path.name != expected:
        _fail("INVALID:SCHEMA_FAIL")


def _stable_receipt_hash(receipt: dict[str, Any]) -> str:
    stable = {
        "schema_version": receipt.get("schema_version"),
        "toolchain_id": receipt.get("toolchain_id"),
        "problem_id": receipt.get("problem_id"),
        "attempt_id": receipt.get("attempt_id"),
        "exit_code": receipt.get("exit_code"),
        "result": receipt.get("result"),
        "lean_preamble_sha256": receipt.get("lean_preamble_sha256"),
    }
    return compute_sealed_receipt_hash(stable)


def _load_pack(config_dir: Path, schema_dir: Path) -> dict[str, Any]:
    pack_path = config_dir / "rsi_sas_system_pack_v1.json"
    pack = _load_json(pack_path)
    _validate_jsonschema(pack, "rsi_sas_system_pack_v1", schema_dir)
    if pack.get("schema_version") != "rsi_sas_system_pack_v1":
        _fail("INVALID:SCHEMA_FAIL")
    return pack


def _load_suite(path: Path, schema_dir: Path) -> dict[str, Any]:
    suite = _load_json(path)
    _validate_jsonschema(suite, "sas_system_suitepack_v1", schema_dir)
    if suite.get("schema_version") != "sas_system_suitepack_v1":
        _fail("INVALID:SCHEMA_FAIL")
    return suite


def _validate_registry_delta(before: dict[str, Any], after: dict[str, Any]) -> None:
    if before.get("schema") != "sas_system_component_registry_v1" or after.get("schema") != "sas_system_component_registry_v1":
        _fail("INVALID:REGISTRY_FORBIDDEN_EDIT")
    if before.get("spec_version") != "v14_0" or after.get("spec_version") != "v14_0":
        _fail("INVALID:REGISTRY_FORBIDDEN_EDIT")

    if set(before.keys()) != {"schema", "spec_version", "components"}:
        _fail("INVALID:REGISTRY_FORBIDDEN_EDIT")
    if set(after.keys()) != {"schema", "spec_version", "components"}:
        _fail("INVALID:REGISTRY_FORBIDDEN_EDIT")

    comp_before = before.get("components")
    comp_after = after.get("components")
    if not isinstance(comp_before, dict) or not isinstance(comp_after, dict):
        _fail("INVALID:REGISTRY_FORBIDDEN_EDIT")

    if set(comp_before.keys()) != set(comp_after.keys()):
        _fail("INVALID:REGISTRY_FORBIDDEN_EDIT")
    if set(comp_before.keys()) != {"SAS_SCIENCE_WORKMETER_V1"}:
        _fail("INVALID:REGISTRY_UNKNOWN_COMPONENT")

    key = "SAS_SCIENCE_WORKMETER_V1"
    before_obj = comp_before.get(key)
    after_obj = comp_after.get(key)
    if not isinstance(before_obj, dict) or not isinstance(after_obj, dict):
        _fail("INVALID:REGISTRY_FORBIDDEN_EDIT")

    allowed = {"active_backend", "rust_ext"}
    if set(before_obj.keys()) != allowed:
        _fail("INVALID:REGISTRY_FORBIDDEN_EDIT")
    if set(after_obj.keys()) != allowed:
        _fail("INVALID:REGISTRY_FORBIDDEN_EDIT")


def _tier_costs(ir: dict[str, Any], suite: dict[str, Any]) -> dict[str, int]:
    costs = {"S": 0, "M": 0, "L": 0}
    for case in suite.get("cases", []):
        if not isinstance(case, dict):
            _fail("INVALID:SCHEMA_FAIL")
        tier = case.get("tier")
        if tier not in costs:
            _fail("INVALID:SCHEMA_FAIL")
        job = case.get("job")
        if not isinstance(job, dict):
            _fail("INVALID:SCHEMA_FAIL")
        costs[tier] += ir_step_cost_total(ir, job)
    return costs


def _tar_sources(crate_dir: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        paths = [
            crate_dir / "Cargo.toml",
            crate_dir / "Cargo.lock",
            crate_dir / "src" / "lib.rs",
            crate_dir / "src" / "bin" / "workmeter_cli.rs",
        ]
        for path in sorted(paths):
            if not path.exists():
                continue
            info = tarfile.TarInfo(name=str(path.relative_to(crate_dir)))
            data = path.read_bytes()
            info.size = len(data)
            info.mtime = 0
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _prepare_writable_crate_dir(state_dir: Path) -> Path:
    src_crate = _repo_root() / "CDEL-v2" / "cdel" / "v14_0" / "rust" / "cdel_workmeter_rs_v1"
    if not src_crate.exists():
        _fail("INVALID:MISSING_ARTIFACT")
    verify_work = state_dir / "_verify_work" / "cdel_workmeter_rs_v1"
    if verify_work.exists():
        shutil.rmtree(verify_work)
    shutil.copytree(src_crate, verify_work, ignore=shutil.ignore_patterns("target"))
    root_mode = verify_work.stat().st_mode
    verify_work.chmod(root_mode | stat.S_IWUSR | stat.S_IXUSR)
    for path in verify_work.rglob("*"):
        mode = path.stat().st_mode
        if path.is_dir():
            path.chmod(mode | stat.S_IWUSR | stat.S_IXUSR)
        else:
            path.chmod(mode | stat.S_IWUSR)
    return verify_work


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        _fail("INVALID:MODE_UNSUPPORTED")

    state_dir = state_dir.resolve()
    if (state_dir / "state").exists():
        state_dir = state_dir / "state"

    config_dir = state_dir.parent / "config"
    schema_dir = _schema_dir()

    pack = _load_pack(config_dir, schema_dir)
    policy_path = config_dir / pack["policy_path"]
    target_path = config_dir / pack["target_catalog_path"]
    suite_dev_path = config_dir / pack["suitepack_path_dev"]
    suite_held_path = config_dir / pack["suitepack_path_heldout"]
    toolchain_py_path = config_dir / pack["toolchain_manifest_py_path"]
    toolchain_lean_path = config_dir / pack["toolchain_manifest_lean_path"]
    toolchain_rust_path = config_dir / pack["toolchain_manifest_rust_path"]

    policy = _load_json(policy_path)
    target_catalog = _load_json(target_path)
    suite_dev = _load_suite(suite_dev_path, schema_dir)
    suite_held = _load_suite(suite_held_path, schema_dir)
    toolchain_py = _load_json(toolchain_py_path)
    toolchain_lean = _load_json(toolchain_lean_path)
    toolchain_rust = _load_json(toolchain_rust_path)

    _validate_jsonschema(policy, "sas_system_policy_v1", schema_dir)
    _validate_jsonschema(target_catalog, "sas_system_target_catalog_v1", schema_dir)
    _validate_jsonschema(toolchain_py, "sas_system_toolchain_manifest_v1", schema_dir)
    _validate_jsonschema(toolchain_lean, "sas_system_toolchain_manifest_v1", schema_dir)
    _validate_jsonschema(toolchain_rust, "sas_system_toolchain_manifest_v1", schema_dir)

    if target_catalog.get("schema") != "sas_system_target_catalog_v1":
        _fail("INVALID:SCHEMA_FAIL")
    targets = target_catalog.get("targets")
    if not isinstance(targets, list) or len(targets) != 1:
        _fail("INVALID:TARGET_CATALOG_LENGTH_FORBIDDEN")
    if targets[0].get("upgrade_allowed") is not True:
        _fail("INVALID:TARGET_NOT_UPGRADABLE")

    policy_hash = sha256_prefixed(canon_bytes(policy))
    target_hash = sha256_prefixed(canon_bytes(target_catalog))
    suite_dev_hash = sha256_prefixed(canon_bytes(suite_dev))
    suite_held_hash = sha256_prefixed(canon_bytes(suite_held))
    toolchain_py_hash = sha256_prefixed(canon_bytes(toolchain_py))
    toolchain_lean_hash = sha256_prefixed(canon_bytes(toolchain_lean))
    toolchain_rust_hash = sha256_prefixed(canon_bytes(toolchain_rust))

    if pack.get("policy_hash") != policy_hash:
        _fail("INVALID:POLICY_HASH_MISMATCH")
    if pack.get("target_catalog_hash") != target_hash:
        _fail("INVALID:TARGET_CATALOG_HASH_MISMATCH")
    if pack.get("toolchain_manifest_py_hash") != toolchain_py_hash:
        _fail("INVALID:TOOLCHAIN_HASH_MISMATCH")
    if pack.get("toolchain_manifest_lean_hash") != toolchain_lean_hash:
        _fail("INVALID:TOOLCHAIN_HASH_MISMATCH")
    if pack.get("toolchain_manifest_rust_hash") != toolchain_rust_hash:
        _fail("INVALID:TOOLCHAIN_HASH_MISMATCH")

    if policy.get("target_catalog_hash") != target_hash:
        _fail("INVALID:TARGET_CATALOG_HASH_MISMATCH")

    ref_hash = _require_sha256(policy.get("ref_impl_sha256"))
    ref_impl_path = _repo_root() / "CDEL-v2" / "cdel" / "v13_0" / "sas_science_workmeter_v1.py"
    if sha256_prefixed(ref_impl_path.read_bytes()) != ref_hash:
        _fail("INVALID:REF_HASH_MISMATCH")

    promo_dir = state_dir / "promotion"
    promo_paths = sorted(promo_dir.glob("sha256_*.sas_system_promotion_bundle_v1.json"))
    if len(promo_paths) != 1:
        _fail("INVALID:MISSING_ARTIFACT")
    promo_path = promo_paths[0]
    promo = _load_json(promo_path)
    _validate_jsonschema(promo, "sas_system_promotion_bundle_v1", schema_dir)
    _hash_name_ok(promo_path, promo, "sas_system_promotion_bundle_v1.json")

    decision = promo.get("acceptance_decision")
    if not isinstance(decision, dict) or decision.get("pass") is not True:
        _fail("INVALID:ACCEPTANCE_FAIL")

    if promo.get("pack_hash") != sha256_prefixed(canon_bytes(pack)):
        _fail("INVALID:PACK_HASH_MISMATCH")
    if promo.get("policy_hash") != policy_hash:
        _fail("INVALID:POLICY_HASH_MISMATCH")
    if promo.get("target_catalog_hash") != target_hash:
        _fail("INVALID:TARGET_CATALOG_HASH_MISMATCH")
    if promo.get("suitepack_dev_hash") != suite_dev_hash:
        _fail("INVALID:SUITEPACK_HASH_MISMATCH")
    if promo.get("suitepack_heldout_hash") != suite_held_hash:
        _fail("INVALID:SUITEPACK_HASH_MISMATCH")

    artifact_dir = state_dir / "artifacts"

    immutable_hash = _require_sha256(promo.get("immutable_tree_snapshot_hash"))
    immutable_path = _find_by_hash(artifact_dir, "sas_system_immutable_tree_snapshot_v1.json", immutable_hash)
    immutable_obj = _load_json(immutable_path)
    _validate_jsonschema(immutable_obj, "sas_system_immutable_tree_snapshot_v1", schema_dir)
    if sha256_prefixed(canon_bytes(immutable_tree_snapshot(_repo_root()))) != immutable_hash:
        _fail("INVALID:IMMUTABLE_TREE_MODIFIED")

    reg_before_hash = _require_sha256(promo.get("component_registry_before_hash"))
    reg_after_hash = _require_sha256(promo.get("component_registry_after_hash"))
    reg_before_path = _find_by_hash(promo_dir, "sas_system_component_registry_v1.json", reg_before_hash)
    reg_after_path = _find_by_hash(promo_dir, "sas_system_component_registry_v1.json", reg_after_hash)
    reg_before = _load_json(reg_before_path)
    reg_after = _load_json(reg_after_path)
    _validate_jsonschema(reg_before, "sas_system_component_registry_v1", schema_dir)
    _validate_jsonschema(reg_after, "sas_system_component_registry_v1", schema_dir)
    _validate_registry_delta(reg_before, reg_after)

    ref_ir = extract_reference_ir(ref_impl_path, expected_sha256=ref_hash)
    ref_ir_hash = sha256_prefixed(canon_bytes(ref_ir))
    if promo.get("reference_ir_sha256") != ref_ir_hash:
        _fail("INVALID:IR_HASH_MISMATCH")

    cand_ir = summarize_loops_v1(ref_ir)
    cand_ir_hash = sha256_prefixed(canon_bytes(cand_ir))

    _ = _find_by_hash(artifact_dir, "sas_system_ir_v1.json", ref_ir_hash)
    _ = _find_by_hash(artifact_dir, "sas_system_ir_v1.json", cand_ir_hash)

    cand_hashes = promo.get("candidate_bundle_hashes")
    if not isinstance(cand_hashes, list) or len(cand_hashes) != 2:
        _fail("INVALID:CANDIDATE_COUNT")

    attempts_dir = state_dir / "attempts"
    candidates: list[dict[str, Any]] = []
    for c_hash in cand_hashes:
        c_hash = _require_sha256(c_hash)
        path = _find_by_hash(attempts_dir, "sas_system_candidate_bundle_v1.json", c_hash)
        cand = _load_json(path)
        _validate_jsonschema(cand, "sas_system_candidate_bundle_v1", schema_dir)
        _hash_name_ok(path, cand, "sas_system_candidate_bundle_v1.json")
        candidates.append(cand)

    ids = {c.get("candidate_id") for c in candidates}
    if ids != {"DIRECT_PORT_RS_V1", "LOOP_SUMMARY_RS_V1"}:
        _fail("INVALID:CANDIDATE_COUNT")

    for cand in candidates:
        if cand.get("reference_ir_sha256") != ref_ir_hash:
            _fail("INVALID:IR_HASH_MISMATCH")
        if cand.get("candidate_id") == "DIRECT_PORT_RS_V1" and cand.get("candidate_ir_sha256") != ref_ir_hash:
            _fail("INVALID:IR_HASH_MISMATCH")
        if cand.get("candidate_id") == "LOOP_SUMMARY_RS_V1" and cand.get("candidate_ir_sha256") != cand_ir_hash:
            _fail("INVALID:IR_HASH_MISMATCH")

    cand_b = next(c for c in candidates if c.get("candidate_id") == "LOOP_SUMMARY_RS_V1")

    proof_hash = _require_sha256(cand_b.get("proof_sha256"))
    proof_path = _find_by_hash(attempts_dir / "proofs", "workmeter.proof.lean", proof_hash)
    proof_text = proof_path.read_text(encoding="utf-8")

    hits = scan_forbidden_tokens(proof_text)
    if hits:
        _fail(f"INVALID:LEAN_FORBIDDEN_TOKEN:{hits[0]}")
    if not validate_proof_shape(proof_text):
        _fail("INVALID:PROOF_SHAPE_INVALID")

    sealed_receipt = sealed_lean_check_receipt(
        toolchain_manifest=toolchain_lean,
        problem_id="sas_system_workmeter",
        attempt_id="cand_b",
        proof_text=proof_text,
        lean_preamble_path=_repo_root() / "CDEL-v2" / "cdel" / "v14_0" / "lean" / "SASSystemPreambleV14.lean",
    )
    if sealed_receipt.get("result") != "PASS" or int(sealed_receipt.get("exit_code", 1)) != 0:
        _fail("INVALID:SEALED_LEAN_CHECK_MISMATCH")
    sealed_hash = _stable_receipt_hash(sealed_receipt)
    if cand_b.get("sealed_proof_receipt_hash") != sealed_hash:
        _fail("INVALID:SEALED_LEAN_CHECK_MISMATCH")
    if promo.get("sealed_proof_receipt_hash") != sealed_hash:
        _fail("INVALID:SEALED_LEAN_CHECK_MISMATCH")

    crate_dir = _prepare_writable_crate_dir(state_dir)
    source_tar_hash = cand_b.get("rust_source_tar_sha256")
    if isinstance(source_tar_hash, str):
        source_tar_hash = _require_sha256(source_tar_hash)
        tar_path = _find_by_hash(attempts_dir, "rust_source.tar", source_tar_hash)
        if sha256_prefixed(tar_path.read_bytes()) != source_tar_hash:
            _fail("INVALID:RUST_SOURCE_NOT_REPRODUCIBLE")
        regenerate_sources(cand_ir, crate_dir)
        if sha256_prefixed(_tar_sources(crate_dir)) != source_tar_hash:
            _fail("INVALID:RUST_SOURCE_NOT_REPRODUCIBLE")

    build_receipt = build_rust_from_ir(ir=cand_ir, crate_dir=crate_dir, toolchain_manifest=toolchain_rust)
    if build_receipt.get("result") != "PASS" or int(build_receipt.get("exit_code", 1)) != 0:
        _fail("INVALID:SEALED_BUILD_RECEIPT_MISMATCH")
    build_hash = _stable_receipt_hash(build_receipt)
    if cand_b.get("sealed_build_receipt_hash") != build_hash:
        _fail("INVALID:SEALED_BUILD_RECEIPT_MISMATCH")
    if promo.get("sealed_build_receipt_hash") != build_hash:
        _fail("INVALID:SEALED_BUILD_RECEIPT_MISMATCH")

    verify_artifacts_dir = state_dir / "_verify_work" / "artifacts"
    verify_rust_module = materialize_python_extension(crate_dir=crate_dir, out_dir=verify_artifacts_dir)

    rust_module = cand_b.get("rust_module")
    if not isinstance(rust_module, str):
        _fail("INVALID:RUST_BACKEND_LOAD_FAIL")
    comp_after = reg_after.get("components", {}).get("SAS_SCIENCE_WORKMETER_V1", {})
    rust_ext = comp_after.get("rust_ext") if isinstance(comp_after, dict) else None
    if not isinstance(rust_ext, dict):
        _fail("INVALID:RUST_BACKEND_LOAD_FAIL")

    run_equivalence(suitepack=suite_dev, rust_module=str(verify_rust_module), fail_fast=True)
    run_equivalence(suitepack=suite_held, rust_module=str(verify_rust_module), fail_fast=True)

    ref_cost_total = sum(ir_step_cost_total(ref_ir, case["job"]) for case in suite_held.get("cases", []))
    cand_cost_total = sum(ir_step_cost_total(cand_ir, case["job"]) for case in suite_held.get("cases", []))
    threshold = int(policy.get("perf_gate_speedup_x10", 10))
    if cand_cost_total * threshold > ref_cost_total:
        _fail("INVALID:PERF_IR_GATE_FAIL")

    ref_tiers = _tier_costs(ref_ir, suite_held)
    cand_tiers = _tier_costs(cand_ir, suite_held)

    s_ref, s_den = ref_tiers["S"], max(cand_tiers["S"], 1)
    m_ref, m_den = ref_tiers["M"], max(cand_tiers["M"], 1)
    l_ref, l_den = ref_tiers["L"], max(cand_tiers["L"], 1)
    if m_ref * s_den < s_ref * m_den:
        _fail("INVALID:PERF_SCALING_SANITY_FAIL")
    if l_ref * m_den < m_ref * l_den:
        _fail("INVALID:PERF_SCALING_SANITY_FAIL")

    eq_hash = _require_sha256(promo.get("equivalence_report_hash"))
    perf_hash = _require_sha256(promo.get("perf_report_hash"))
    profile_hash = _require_sha256(promo.get("profile_report_hash"))

    eq_path = _find_by_hash(artifact_dir, "sas_system_equivalence_report_v1.json", eq_hash)
    perf_path = _find_by_hash(artifact_dir, "sas_system_perf_report_v1.json", perf_hash)
    profile_path = _find_by_hash(artifact_dir, "sas_system_profile_report_v1.json", profile_hash)

    eq_report = _load_json(eq_path)
    perf_report = _load_json(perf_path)
    profile_report = _load_json(profile_path)

    _validate_jsonschema(eq_report, "sas_system_equivalence_report_v1", schema_dir)
    _validate_jsonschema(perf_report, "sas_system_perf_report_v1", schema_dir)
    _validate_jsonschema(profile_report, "sas_system_profile_report_v1", schema_dir)

    if eq_report.get("all_pass") is not True:
        _fail("INVALID:OUTPUT_MISMATCH:REPORT")
    case_results = eq_report.get("case_results")
    if not isinstance(case_results, list) or not case_results or not all(isinstance(x, dict) and x.get("pass") is True for x in case_results):
        _fail("INVALID:OUTPUT_MISMATCH:REPORT")

    if int(perf_report.get("ref_cost_total", -1)) != int(ref_cost_total):
        _fail("INVALID:PERF_IR_GATE_FAIL")
    if int(perf_report.get("cand_cost_total", -1)) != int(cand_cost_total):
        _fail("INVALID:PERF_IR_GATE_FAIL")

    if profile_report.get("target_id") != "SAS_SCIENCE_WORKMETER_V1":
        _fail("INVALID:SELECTION_INVALID")

    sel_hash = _require_sha256(promo.get("selection_receipt_hash"))
    sel_path = _find_by_hash(state_dir / "selection", "sas_system_selection_receipt_v1.json", sel_hash)
    sel = _load_json(sel_path)
    _validate_jsonschema(sel, "sas_system_selection_receipt_v1", schema_dir)
    if sel.get("selected_candidate_id") != "LOOP_SUMMARY_RS_V1":
        _fail("INVALID:SELECTION_INVALID")
    if sel.get("target_id") != "SAS_SCIENCE_WORKMETER_V1":
        _fail("INVALID:SELECTION_INVALID")
    if sel.get("profile_report_hash") != profile_hash:
        _fail("INVALID:SELECTION_INVALID")

    ledger_path = state_dir / "ledger" / "sas_system_ledger_event_v1.jsonl"
    if ledger_path.exists():
        entries = load_ledger(ledger_path)
        validate_chain(entries)

    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_sas_system_v1")
    parser.add_argument("--state_dir", required=True)
    parser.add_argument("--mode", default="full")
    args = parser.parse_args()
    try:
        result = verify(Path(args.state_dir), mode=args.mode)
        sys.stdout.write(result)
    except SASSystemError as exc:
        sys.stdout.write(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
