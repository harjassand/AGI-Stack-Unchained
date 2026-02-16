"""Verifier for RSI demon v8 CSI attempts."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from ..v2_1.opt_ontology import build_active_concepts_from_patches, concept_uses_call, evaluate_expr
from .code_patch import apply_patch_to_tree, compute_patch_id, scan_forbidden, tree_entries_v1, tree_hash_from_entries, validate_patch_constraints
from .constants import meta_identities, require_constants


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_json(path: Path) -> dict[str, Any]:
    return load_canon_json(path)


def _load_manifest(state_dir: Path) -> dict[str, Any]:
    path = state_dir / "csi_manifest_v1.json"
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    manifest = _load_json(path)
    head = dict(manifest)
    head.pop("manifest_head_hash", None)
    if manifest.get("manifest_head_hash") != sha256_prefixed(canon_bytes(head)):
        _fail("CANON_HASH_MISMATCH")
    return manifest


def _load_code_patch(state_dir: Path) -> dict[str, Any]:
    path = state_dir / "autonomy" / "csi" / "code_patch.json"
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    patch = _load_json(path)
    expected = compute_patch_id(patch)
    if patch.get("patch_id") != expected:
        _fail("CANON_HASH_MISMATCH")
    if patch.get("schema") != "code_patch_v1":
        _fail("SCHEMA_INVALID")
    return patch


def _load_bench_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    report = _load_json(path)
    head = dict(report)
    head.pop("report_head_hash", None)
    if report.get("report_head_hash") != sha256_prefixed(canon_bytes(head)):
        _fail("CANON_HASH_MISMATCH")
    return report


def _load_test_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    report = _load_json(path)
    head = dict(report)
    head.pop("report_head_hash", None)
    if report.get("report_head_hash") != sha256_prefixed(canon_bytes(head)):
        _fail("CANON_HASH_MISMATCH")
    return report


def _run_bench(tree_dir: Path, suite_path: Path, inputs_path: Path, run_id: str, attempt_id: str, tree_hash: str, out_path: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(tree_dir / "Extension-1" / "agi-orchestrator"),
            str(tree_dir / "CDEL-v2"),
        ]
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [
        sys.executable,
        "-m",
        "cdel.v2_2.csi_bench",
        "--suite",
        str(suite_path),
        "--inputs",
        str(inputs_path),
        "--run_id",
        run_id,
        "--attempt_id",
        attempt_id,
        "--tree_hash",
        tree_hash,
        "--out",
        str(out_path),
    ]
    result = subprocess.run(cmd, env=env, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise CanonError(result.stderr.strip() or result.stdout.strip() or "bench run failed")
    return _load_json(out_path)


def _concept_selection(
    active_set: dict[str, Any],
    patches: list[dict[str, Any]],
) -> tuple[str, str, dict[str, Any]]:
    accepted = active_set.get("accepted_concepts") if isinstance(active_set.get("accepted_concepts"), list) else []
    patch_by_id: dict[str, dict[str, Any]] = {}
    for patch in patches:
        pid = patch.get("patch_id")
        if isinstance(pid, str):
            patch_by_id[pid] = patch

    recursive: list[tuple[str, str, dict[str, Any]]] = []
    for entry in accepted:
        if not isinstance(entry, dict):
            continue
        concept_id = entry.get("concept_id")
        patch_id = entry.get("patch_id")
        if not isinstance(concept_id, str) or not isinstance(patch_id, str):
            continue
        patch = patch_by_id.get(patch_id)
        if not isinstance(patch, dict):
            continue
        concept = patch.get("concept") if isinstance(patch.get("concept"), dict) else None
        if not isinstance(concept, dict):
            continue
        expr = concept.get("expr") if isinstance(concept.get("expr"), dict) else None
        if not isinstance(expr, dict):
            continue
        if concept_uses_call(expr):
            recursive.append((concept_id, patch_id, concept))

    if not recursive:
        _fail("CONCEPT_NOT_RECURSIVE")

    recursive.sort(key=lambda row: row[0])
    return recursive[0]


def _load_recursive_ontology(state_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = state_dir / "autonomy" / "recursive_ontology" / "opt_ontology"
    active_path = root / "opt_ontology_active_set_v1.json"
    if not active_path.exists():
        _fail("MISSING_ARTIFACT")
    active = _load_json(active_path)
    concepts_dir = root / "concepts"
    if not concepts_dir.exists():
        _fail("MISSING_ARTIFACT")
    patches = []
    for path in sorted(concepts_dir.glob("*.json")):
        patches.append(_load_json(path))
    return active, patches


def _feature_map_from_baseline(baseline: dict[str, Any], suite: dict[str, Any], inputs: dict[str, Any]) -> dict[str, int]:
    meter = baseline.get("meter_counts") if isinstance(baseline.get("meter_counts"), dict) else None
    if not isinstance(meter, dict):
        _fail("SCHEMA_INVALID")

    prompts = set()
    inputs_cases = inputs.get("cases") if isinstance(inputs.get("cases"), list) else []
    for case in inputs_cases:
        if not isinstance(case, dict):
            continue
        payload = case.get("payload") if isinstance(case.get("payload"), dict) else None
        if not isinstance(payload, dict):
            continue
        for prompt in payload.get("prompts", []) if isinstance(payload.get("prompts"), list) else []:
            if isinstance(prompt, str):
                prompts.add(prompt)

    u_ctx = len(prompts)
    sha_calls = int(meter.get("sha256_calls_total", 0) or 0)
    sha_bytes = int(meter.get("sha256_bytes_total", 0) or 0)
    work_cost_base = int(baseline.get("work_cost", 0) or 0)

    return {
        "u_ctx": int(u_ctx),
        "sha256_calls_total": int(sha_calls),
        "sha256_bytes_total": int(sha_bytes),
        "canon_calls_total": 0,
        "canon_bytes_total": 0,
        "onto_ctx_hash_compute_calls_total": int(sha_calls),
        "work_cost_base": int(work_cost_base),
    }


def verify(state_dir: Path) -> dict[str, Any]:
    constants = require_constants()
    meta = meta_identities()

    manifest = _load_manifest(state_dir)
    patch = _load_code_patch(state_dir)
    if manifest.get("patch_id") != patch.get("patch_id"):
        _fail("CANON_HASH_MISMATCH")

    attempt_id = manifest.get("attempt_id")
    if not isinstance(attempt_id, str):
        _fail("SCHEMA_INVALID")

    run_root = state_dir.parent.parent
    constitution_hash_path = run_root / "constitution_hash.txt"
    if not constitution_hash_path.exists():
        _fail("MISSING_ARTIFACT")
    constitution_hash = constitution_hash_path.read_text(encoding="utf-8").strip()
    if constitution_hash != meta.get("META_HASH"):
        _fail("META_DRIFT")

    allowed_roots = list(constants.get("CSI_ALLOWED_ROOTS", []))
    immutable_paths = list(constants.get("CSI_IMMUTABLE_PATHS", []))
    validate_patch_constraints(
        patch,
        allowed_roots=allowed_roots,
        immutable_paths=immutable_paths,
        max_files=int(constants.get("CSI_MAX_FILES_TOUCHED", 0) or 0),
        max_patch_bytes=int(constants.get("CSI_MAX_PATCH_BYTES", 0) or 0),
        max_lines_added=int(constants.get("CSI_MAX_LINES_ADDED", 0) or 0),
        max_lines_removed=int(constants.get("CSI_MAX_LINES_REMOVED", 0) or 0),
    )

    base_snapshot = state_dir / "base_snapshot"
    if not base_snapshot.exists():
        base_snapshot = run_root / "active_tree" / "snapshot"
    base_entries = tree_entries_v1(base_snapshot, allowed_roots, immutable_paths)
    base_tree_hash = tree_hash_from_entries(base_entries)
    if patch.get("base_tree_hash") != base_tree_hash:
        _fail("CANON_HASH_MISMATCH")

    updated = apply_patch_to_tree(base_snapshot, patch)
    for relpath, patched_bytes in updated.items():
        base_entries[relpath] = sha256_prefixed(patched_bytes)
        has_import, has_syntax = scan_forbidden(
            patched_bytes.decode("utf-8"),
            forbidden_imports=set(constants.get("CSI_FORBIDDEN_IMPORT_MODULES", [])),
            forbidden_syntax=set(constants.get("CSI_FORBIDDEN_SYNTAX", [])),
        )
        if has_import:
            _fail("FORBIDDEN_IMPORT")
        if has_syntax:
            _fail("FORBIDDEN_SYNTAX")

    after_tree_hash = tree_hash_from_entries(base_entries)
    if patch.get("after_tree_hash") != after_tree_hash:
        _fail("CANON_HASH_MISMATCH")

    candidate_tree = state_dir / "candidate_tree"
    if not candidate_tree.exists():
        _fail("MISSING_ARTIFACT")
    candidate_hash = tree_hash_from_entries(tree_entries_v1(candidate_tree, allowed_roots, immutable_paths))
    if candidate_hash != after_tree_hash:
        _fail("CANON_HASH_MISMATCH")

    baseline_report = _load_bench_report(state_dir / "baseline_bench_report_v1.json")
    patch_report = _load_bench_report(state_dir / "patch_bench_report_v1.json")

    suite_path = candidate_tree / "Extension-1" / "agi-orchestrator" / "orchestrator" / "csi" / "bench_suite_v1.json"
    inputs_path = candidate_tree / "Extension-1" / "agi-orchestrator" / "orchestrator" / "csi" / "bench_inputs_v1.json"
    suite = load_canon_json(suite_path)
    inputs = load_canon_json(inputs_path)

    feature_map = _feature_map_from_baseline(baseline_report, suite, inputs)
    concept_binding = patch.get("concept_binding") if isinstance(patch.get("concept_binding"), dict) else None
    if not isinstance(concept_binding, dict):
        _fail("CONCEPT_MISSING")
    if concept_binding.get("mode") != "recursive_ontology_v2_1":
        _fail("SCHEMA_INVALID")

    active_set, concept_patches = _load_recursive_ontology(state_dir)
    concept_id, concept_patch_id, concept = _concept_selection(active_set, concept_patches)
    if concept_binding.get("selected_concept_id") != concept_id:
        _fail("CONCEPT_MISSING")
    if concept_binding.get("selected_concept_patch_id") != concept_patch_id:
        _fail("CONCEPT_MISSING")

    if concept_binding.get("concept_eval_features") != feature_map:
        _fail("CANON_HASH_MISMATCH")

    active_concepts = build_active_concepts_from_patches(concept_patches)
    expr = concept.get("expr") if isinstance(concept.get("expr"), dict) else None
    if not isinstance(expr, dict):
        _fail("SCHEMA_INVALID")
    concept_output = evaluate_expr(expr, features=feature_map, active_concepts=active_concepts)
    if concept_binding.get("concept_eval_output_int") != concept_output:
        _fail("CANON_HASH_MISMATCH")

    test_report = _load_test_report(state_dir / "patch_test_report_v1.json")
    if int(test_report.get("overall_exit_code", 1)) != 0:
        _fail("CSI_TEST_FAIL")

    required_tests = set(constants.get("CSI_REQUIRED_TESTS", []))
    tests = test_report.get("tests") if isinstance(test_report.get("tests"), list) else []
    executed = set()
    for test in tests:
        if not isinstance(test, dict):
            continue
        argv = test.get("argv") if isinstance(test.get("argv"), list) else []
        argv_str = " ".join(str(x) for x in argv)
        for req in required_tests:
            if req in argv_str:
                executed.add(req)
        summary = test.get("summary") if isinstance(test.get("summary"), dict) else None
        if not isinstance(summary, dict):
            _fail("SCHEMA_INVALID")
        if int(test.get("exit_code", 1)) != 0 or int(summary.get("failed", 1)) != 0:
            _fail("CSI_TEST_FAIL")
    if required_tests and executed != required_tests:
        _fail("CSI_TEST_FAIL")

    # Verify bench determinism by re-running twice on candidate tree.
    tmp_dir = state_dir / "diagnostics" / "bench_verify"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    run1 = _run_bench(candidate_tree, suite_path, inputs_path, manifest.get("run_id", ""), attempt_id, after_tree_hash, tmp_dir / "bench_run1.json")
    run2 = _run_bench(candidate_tree, suite_path, inputs_path, manifest.get("run_id", ""), attempt_id, after_tree_hash, tmp_dir / "bench_run2.json")

    if run1.get("meter_counts") != run2.get("meter_counts") or run1.get("case_output_hashes") != run2.get("case_output_hashes"):
        _fail("NONDETERMINISM")

    # Ensure stored patch report matches deterministic run
    if patch_report.get("meter_counts") != run1.get("meter_counts"):
        _fail("CANON_HASH_MISMATCH")
    if patch_report.get("case_output_hashes") != run1.get("case_output_hashes"):
        _fail("CANON_HASH_MISMATCH")

    # Output hashes must match baseline
    if patch_report.get("case_output_hashes") != baseline_report.get("case_output_hashes"):
        _fail("CSI_OUTPUT_MISMATCH")

    weights = constants.get("CSI_WORK_COST_WEIGHTS_V1", {})
    if not isinstance(weights, dict):
        _fail("SCHEMA_INVALID")

    # Recompute work cost
    from .csi_bench import compute_work_cost

    base_cost = compute_work_cost(baseline_report.get("meter_counts", {}), weights)
    patch_cost = compute_work_cost(patch_report.get("meter_counts", {}), weights)
    if int(baseline_report.get("work_cost", -1)) != base_cost:
        _fail("CANON_HASH_MISMATCH")
    if int(patch_report.get("work_cost", -1)) != patch_cost:
        _fail("CANON_HASH_MISMATCH")

    rho_min = constants.get("RHO_CSI_MIN", {})
    if not isinstance(rho_min, dict):
        _fail("SCHEMA_INVALID")
    min_num = int(rho_min.get("num", 0) or 0)
    min_den = int(rho_min.get("den", 1) or 1)
    if patch_cost == 0:
        _fail("NONDETERMINISM")
    if base_cost * min_den < patch_cost * min_num:
        _fail("CSI_EFFICIENCY_GATE_FAIL")

    receipt = {
        "schema": "rsi_demon_receipt_v8",
        "verdict": "VALID",
        "reasons": [],
        "patch_id": patch.get("patch_id"),
        "concept_id": concept_id,
        "base_tree_hash": base_tree_hash,
        "after_tree_hash": after_tree_hash,
        "work_cost_base": base_cost,
        "work_cost_patch": patch_cost,
        "rho_csi": {"num": base_cost, "den": patch_cost},
    }
    return receipt


def _write_receipt(state_dir: Path, receipt: dict[str, Any]) -> None:
    out = state_dir / "diagnostics" / "rsi_demon_receipt_v8.json"
    write_canon_json(out, receipt)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify RSI demon v8 CSI attempt")
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        receipt = verify(Path(args.state_dir))
        _write_receipt(Path(args.state_dir), receipt)
    except Exception as exc:  # noqa: BLE001
        reason = str(exc) if str(exc) else "unknown"
        receipt = {
            "schema": "rsi_demon_receipt_v8",
            "verdict": "INVALID",
            "reasons": [reason],
            "patch_id": "",
            "concept_id": "",
            "base_tree_hash": "",
            "after_tree_hash": "",
            "work_cost_base": 0,
            "work_cost_patch": 0,
            "rho_csi": {"num": 0, "den": 1},
        }
        try:
            _write_receipt(Path(args.state_dir), receipt)
        except Exception:
            pass
        print(f"INVALID: {reason}")
        return

    print("VALID")


if __name__ == "__main__":
    main()
