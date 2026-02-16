"""Fail-closed verifier for RSI SAS-Kernel v15.1 brain transplant."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tarfile
import warnings
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from .brain.brain_corpus_v1 import load_suitepack
from .brain.brain_equivalence_v1 import canonical_json_hash, compare_decision_files
from .brain.brain_perf_v1 import compute_brain_perf_report

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


class V15_1KernelError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise V15_1KernelError(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema_dir() -> Path:
    return _repo_root() / "Genesis" / "schema" / "v15_1"


def _kernel_crate_dir() -> Path:
    return _repo_root() / "CDEL-v2" / "cdel" / "v15_1" / "rust" / "agi_kernel_rs_v1"


def _kernel_binary() -> Path:
    return _kernel_crate_dir() / "target" / "release" / "agi_kernel_v15_1"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


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
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            schema_id = payload.get("$id")
            if isinstance(schema_id, str):
                store[schema_id] = payload
            store[path.name] = payload
            store[path.resolve().as_uri()] = payload
    if RefResolver is not None:
        resolver = RefResolver.from_schema(schema, store=store)
        Draft202012Validator(schema, resolver=resolver).validate(obj)
    else:
        Draft202012Validator(schema).validate(obj)


def _load_json(path: Path) -> dict[str, Any]:
    obj = load_canon_json(path)
    if not isinstance(obj, dict):
        _fail("INVALID:SCHEMA_FAIL")
    return obj


def _canonical_hash(path: Path) -> str:
    return sha256_prefixed(canon_bytes(load_canon_json(path)))


def _scan_lean_forbidden(path: Path, *, require_non_vacuous: bool) -> None:
    text = path.read_text(encoding="utf-8")
    for token in ["axiom", "sorry", "admit", "unsafe", "partial"]:
        if re.search(rf"\b{re.escape(token)}\b", text):
            _fail("INVALID:LEAN_FORBIDDEN_TOKEN")
    if require_non_vacuous:
        for pattern in [r":\s*True\b", r"\bby\s+trivial\b"]:
            if re.search(pattern, text):
                _fail("INVALID:LEAN_VACUOUS_PROOF")


def _scan_rust_structure(crate_src: Path) -> None:
    if not crate_src.exists():
        _fail("INVALID:RUST_SRC_MISSING")
    for path in sorted(crate_src.rglob("*.rs")):
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(crate_src))
        if re.search(r"\bunsafe\b", text):
            _fail("INVALID:RUST_FORBIDDEN_TOKEN")
        if "std::net" in text or "SystemTime" in text or "Instant" in text:
            _fail("INVALID:RUST_FORBIDDEN_TOKEN")
        if rel != "kernel_sys/mod.rs":
            for token in ["std::fs", "std::process", "std::env"]:
                if token in text:
                    _fail("INVALID:RUST_SYSCALL_SURFACE")


def _manifest_role(path: Path) -> str:
    name = path.name.lower()
    if "lean" in name:
        return "lean"
    if "kernel" in name:
        return "kernel"
    if "rust" in name:
        return "rust"
    if "py" in name:
        return "py"
    return "unknown"


def _toolchain_id_payload(obj: dict[str, Any]) -> dict[str, Any]:
    payload = dict(obj)
    payload.pop("toolchain_id", None)
    return payload


def _validate_toolchain_manifest(path: Path, schema_dir: Path) -> dict[str, Any]:
    role = _manifest_role(path)
    obj = _load_json(path)
    _validate_jsonschema(obj, "toolchain_manifest_v15", schema_dir)

    required = {
        "checker_name",
        "checker_executable",
        "invocation_template",
        "checker_executable_hash",
        "toolchain_id",
    }
    if set(obj.keys()) != required:
        _fail("INVALID:TOOLCHAIN_MANIFEST")

    checker_name = obj["checker_name"]
    checker_executable = obj["checker_executable"]
    invocation = obj["invocation_template"]
    pinned_hash = obj["checker_executable_hash"]
    toolchain_id = obj["toolchain_id"]

    if not isinstance(checker_name, str) or not checker_name:
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    if not isinstance(checker_executable, str) or not checker_executable.startswith("/"):
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    if (
        not isinstance(invocation, list)
        or not invocation
        or not isinstance(invocation[0], str)
        or not invocation[0].startswith("/")
    ):
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    if not isinstance(pinned_hash, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", pinned_hash):
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    if pinned_hash == "sha256:" + ("0" * 64):
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    if not isinstance(toolchain_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", toolchain_id):
        _fail("INVALID:TOOLCHAIN_MANIFEST")

    checker_path = Path(checker_executable)
    invoke_path = Path(invocation[0])
    checker_real = checker_path.resolve()
    invoke_real = invoke_path.resolve()

    if checker_real != invoke_real:
        _fail("INVALID:TOOLCHAIN_EXEC_MISMATCH")
    if not checker_real.exists() or not checker_real.is_file():
        _fail("INVALID:TOOLCHAIN_EXEC_MISSING")

    computed_hash = sha256_prefixed(checker_real.read_bytes())
    if computed_hash != pinned_hash:
        _fail("INVALID:TOOLCHAIN_HASH_MISMATCH")

    basename = checker_real.name.lower()
    if basename in {"true", "sh", "bash", "env"}:
        _fail("INVALID:TOOLCHAIN_EXEC_FORBIDDEN")
    if role == "lean":
        if "lean" not in basename:
            _fail("INVALID:LEAN_TOOLCHAIN_EXEC")
        if basename.startswith("python"):
            _fail("INVALID:LEAN_TOOLCHAIN_EXEC")
    if role == "kernel" and basename != "agi_kernel_v15_1":
        _fail("INVALID:KERNEL_TOOLCHAIN_EXEC")
    if role == "rust" and basename not in {"cargo", "rustup"}:
        _fail("INVALID:RUST_TOOLCHAIN_EXEC")
    if role == "py" and not basename.startswith("python"):
        _fail("INVALID:PY_TOOLCHAIN_EXEC")

    expected_toolchain_id = sha256_prefixed(canon_bytes(_toolchain_id_payload(obj)))
    if toolchain_id != expected_toolchain_id:
        _fail("INVALID:TOOLCHAIN_ID_MISMATCH")

    return {
        "role": role,
        "manifest_path": str(path),
        "checker_name": checker_name,
        "checker_executable": checker_executable,
        "checker_realpath": str(checker_real),
        "invocation_template": invocation,
        "checker_executable_hash": pinned_hash,
        "computed_hash": computed_hash,
        "toolchain_id": toolchain_id,
    }


def _sealed_rebuild_kernel(*, rust_tool: dict[str, Any], kernel_tool: dict[str, Any]) -> str:
    result = subprocess.run(
        list(rust_tool["invocation_template"]),
        cwd=_kernel_crate_dir(),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _fail("INVALID:KERNEL_BUILD_REPLAY")

    binary = _kernel_binary().resolve()
    if not binary.exists() or not binary.is_file():
        _fail("INVALID:KERNEL_BUILD_REPLAY")
    if Path(kernel_tool["checker_realpath"]) != binary:
        _fail("INVALID:KERNEL_MANIFEST_PATH_MISMATCH")

    raw = binary.read_bytes()
    binary_hash = sha256_prefixed(raw)
    if binary_hash != kernel_tool["checker_executable_hash"]:
        _fail("INVALID:KERNEL_HASH_MISMATCH")

    # Wrapper-script rejection.
    if raw.startswith(b"#!"):
        _fail("INVALID:KERNEL_BINARY_NOT_NATIVE")
    try:
        sample = raw[:256].decode("utf-8")
        if sample.isprintable() and "\n" in sample:
            _fail("INVALID:KERNEL_BINARY_NOT_NATIVE")
    except UnicodeDecodeError:
        pass
    return binary_hash


def _sealed_lean_replay(*, lean_tool: dict[str, Any], proof_path: Path, state_dir: Path) -> dict[str, Any]:
    proof_path = proof_path.resolve()
    if not proof_path.exists():
        _fail("INVALID:LEAN_PROOF_MISSING")
    if not _is_relative_to(proof_path, state_dir):
        _fail("INVALID:LEAN_PROOF_PATH")

    preamble_path = proof_path.parent / "SASKernelBrainPreambleV15_1.lean"
    if not preamble_path.exists():
        _fail("INVALID:LEAN_PREAMBLE_MISSING")

    _scan_lean_forbidden(preamble_path, require_non_vacuous=False)
    _scan_lean_forbidden(proof_path, require_non_vacuous=True)

    runs: list[dict[str, Any]] = []
    for target in [preamble_path, proof_path]:
        argv = list(lean_tool["invocation_template"]) + [str(target)]
        result = subprocess.run(
            argv,
            cwd=proof_path.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        runs.append(
            {
                "target": str(target),
                "argv": argv,
                "returncode": int(result.returncode),
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        if result.returncode != 0:
            _fail("INVALID:LEAN_REPLAY")

    return {
        "schema_version": "lean_replay_receipt_v1",
        "proof_rel": str(proof_path.relative_to(state_dir)),
        "preamble_rel": str(preamble_path.relative_to(state_dir)),
        "runs": runs,
    }


def _run_kernel_brain_suite(
    *,
    kernel_tool: dict[str, Any],
    suitepack_path: Path,
    out_dir: Path,
) -> tuple[int, str, str]:
    argv = list(kernel_tool["invocation_template"]) + [
        "brain-suite",
        "--suitepack",
        str(suitepack_path),
        "--out_dir",
        str(out_dir),
    ]
    result = subprocess.run(
        argv,
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _validate_spawn_forbidden(trace_path: Path) -> None:
    if not trace_path.exists():
        return
    for raw in trace_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except Exception:
            _fail("INVALID:TRACE_FORMAT")
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        argv = payload.get("argv")
        if not isinstance(argv, list):
            continue
        joined = " ".join(str(x) for x in argv)
        if re.search(r"python\w*\s+-m\s+orchestrator\.", joined):
            _fail("INVALID:SPAWNED_FORBIDDEN_ORCHESTRATOR")
        if "orchestrator/run.py" in joined or "orchestrator/promote.py" in joined:
            _fail("INVALID:SPAWNED_FORBIDDEN_ORCHESTRATOR")


def _collect_case_metrics(*, suitepack: dict[str, Any], kernel_out_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for case in suitepack["cases"]:  # VAL_ELIGIBLE
        case_id = case["case_id"]
        perf_case_path = kernel_out_dir / "cases" / case_id / "brain_perf_case_v1.json"
        perf = _load_json(perf_case_path)
        required = {
            "schema_version",
            "case_id",
            "rules_evaluated_u64",
            "candidates_scanned_u64",
            "comparisons_u64",
            "bytes_processed_u64",
            "candidate_steps_u64",
        }
        if set(perf.keys()) != required:
            _fail("INVALID:PERF_CASE_SCHEMA")
        if perf.get("schema_version") != "brain_perf_case_v1":
            _fail("INVALID:PERF_CASE_SCHEMA")
        if perf.get("case_id") != case_id:
            _fail("INVALID:PERF_CASE_SCHEMA")
        for key in [
            "rules_evaluated_u64",
            "candidates_scanned_u64",
            "comparisons_u64",
            "bytes_processed_u64",
            "candidate_steps_u64",
        ]:
            value = perf.get(key)
            if not isinstance(value, int) or value < 0:
                _fail("INVALID:PERF_CASE_SCHEMA")
        if int(perf["candidate_steps_u64"]) <= 0:
            _fail("INVALID:PERF_CANDIDATE_ZERO")
        out.append(perf)
    return out


def _enforce_kernel_perf_integrity(*, perf_report: dict[str, Any], expected_cases: int) -> None:
    per_case = perf_report.get("per_case")
    if not isinstance(per_case, list):
        _fail("INVALID:PERF_REPORT_SCHEMA")
    if len(per_case) != expected_cases:
        _fail("INVALID:PERF_REPORT_INCONSISTENT")
    if perf_report.get("gate_pass") and len(per_case) == 0:
        _fail("INVALID:PERF_REPORT_INCONSISTENT")

    candidate_sum = 0
    for row in per_case:
        if not isinstance(row, dict):
            _fail("INVALID:PERF_REPORT_SCHEMA")
        val = row.get("candidate_opcodes")
        if not isinstance(val, int) or val <= 0:
            _fail("INVALID:PERF_CANDIDATE_ZERO")
        candidate_sum += val

    if candidate_sum <= 0:
        _fail("INVALID:PERF_CANDIDATE_ZERO")
    declared_total = perf_report.get("candidate_brain_opcodes_total")
    if not isinstance(declared_total, int) or declared_total != candidate_sum:
        _fail("INVALID:PERF_REPORT_INCONSISTENT")


def _validate_orchestrator_source_bundle(state_dir: Path) -> dict[str, Any]:
    manifest_path = state_dir / "orchestrator_source_bundle_v1.json"
    bundle_path = state_dir / "orchestrator_source_bundle_v1.tar"
    if not manifest_path.exists() or not bundle_path.exists():
        _fail("INVALID:ORCHESTRATOR_BUNDLE_MISSING")

    manifest = _load_json(manifest_path)
    required = {"schema_version", "bundle_rel", "bundle_sha256", "files"}
    if set(manifest.keys()) != required:
        _fail("INVALID:ORCHESTRATOR_BUNDLE_SCHEMA")
    if manifest.get("schema_version") != "orchestrator_source_bundle_v1":
        _fail("INVALID:ORCHESTRATOR_BUNDLE_SCHEMA")
    if not isinstance(manifest.get("bundle_rel"), str):
        _fail("INVALID:ORCHESTRATOR_BUNDLE_SCHEMA")
    if not isinstance(manifest.get("bundle_sha256"), str):
        _fail("INVALID:ORCHESTRATOR_BUNDLE_SCHEMA")
    if (state_dir / manifest["bundle_rel"]).resolve() != bundle_path.resolve():
        _fail("INVALID:ORCHESTRATOR_BUNDLE_SCHEMA")

    bundle_hash = sha256_prefixed(bundle_path.read_bytes())
    if bundle_hash != manifest["bundle_sha256"]:
        _fail("INVALID:ORCHESTRATOR_BUNDLE_HASH")

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        _fail("INVALID:ORCHESTRATOR_BUNDLE_SCHEMA")

    with tarfile.open(bundle_path, "r") as tar:
        names = set(tar.getnames())
        for row in files:
            if not isinstance(row, dict):
                _fail("INVALID:ORCHESTRATOR_BUNDLE_SCHEMA")
            if set(row.keys()) != {"path_rel", "sha256"}:
                _fail("INVALID:ORCHESTRATOR_BUNDLE_SCHEMA")
            rel = row["path_rel"]
            if not isinstance(rel, str) or not rel:
                _fail("INVALID:ORCHESTRATOR_BUNDLE_SCHEMA")
            if rel not in names:
                _fail("INVALID:ORCHESTRATOR_BUNDLE_CONTENT")
            extracted = tar.extractfile(rel)
            if extracted is None:
                _fail("INVALID:ORCHESTRATOR_BUNDLE_CONTENT")
            content_hash = sha256_prefixed(extracted.read())
            if content_hash != row["sha256"]:
                _fail("INVALID:ORCHESTRATOR_BUNDLE_HASH")

    return manifest


def _validate_suite_outputs(
    *,
    suitepack: dict[str, Any],
    suitepack_path: Path,
    kernel_out_dir: Path,
    schema_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    reports_dir = kernel_out_dir / "kernel" / "reports"
    suite_report_path = reports_dir / "brain_suite_report_v1.json"
    branch_report_path = reports_dir / "branch_coverage_report_v1.json"
    perf_report_path = reports_dir / "kernel_brain_perf_report_v1.json"
    trace_path = kernel_out_dir / "kernel" / "trace" / "kernel_trace_v1.jsonl"
    _validate_spawn_forbidden(trace_path)

    suite_report = _load_json(suite_report_path)
    branch_report = _load_json(branch_report_path)
    perf_report = _load_json(perf_report_path)

    _validate_jsonschema(suite_report, "brain_suite_report_v1", schema_dir)
    _validate_jsonschema(branch_report, "branch_coverage_report_v1", schema_dir)
    _validate_jsonschema(perf_report, "kernel_brain_perf_report_v1", schema_dir)

    rows: list[dict[str, Any]] = []
    suite_dir = suitepack_path.parent
    for case in suitepack["cases"]:
        case_id = case["case_id"]
        ref_path = suite_dir / case["decision_ref_rel"]
        kernel_path = kernel_out_dir / "cases" / case_id / "brain_decision_kernel_v1.json"
        if not kernel_path.exists():
            _fail(f"INVALID:BRAIN_DECISION_MISSING:case_id={case_id}")

        ref_obj = _load_json(ref_path)
        kernel_obj = _load_json(kernel_path)
        _validate_jsonschema(ref_obj, "brain_decision_v1", schema_dir)
        _validate_jsonschema(kernel_obj, "brain_decision_v1", schema_dir)

        ok, _reason = compare_decision_files(ref_path, kernel_path)
        if not ok:
            _fail(f"INVALID:BRAIN_DECISION_MISMATCH:case_id={case_id}")

        rows.append(
            {
                "case_id": case_id,
                "ref_hash": canonical_json_hash(ref_path),
                "kernel_hash": canonical_json_hash(kernel_path),
            }
        )

    case_metrics = _collect_case_metrics(suitepack=suitepack, kernel_out_dir=kernel_out_dir)
    _enforce_kernel_perf_integrity(perf_report=perf_report, expected_cases=len(suitepack["cases"]))

    return suite_report, branch_report, perf_report, rows, case_metrics


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        _fail("INVALID:MODE_UNSUPPORTED")

    state_dir = state_dir.resolve()
    repo_root = _repo_root()
    schema_dir = _schema_dir()

    config_dir = state_dir.parent / "config"
    pack_path = config_dir / "rsi_sas_kernel_pack_v15_1.json"
    pack = _load_json(pack_path)
    required_pack = {
        "schema_version",
        "kernel_policy_rel",
        "capability_registry_rel",
        "brain_corpus_dev_rel",
        "brain_corpus_heldout_rel",
        "toolchain_manifest_kernel_rel",
        "toolchain_manifest_py_rel",
        "toolchain_manifest_rust_rel",
        "toolchain_manifest_lean_rel",
    }
    if set(pack.keys()) != required_pack or pack.get("schema_version") != "rsi_sas_kernel_pack_v15_1":
        _fail("INVALID:SCHEMA_FAIL")

    # 1) Frozen config load + schema validation.
    suitepack_path = config_dir / str(pack["brain_corpus_heldout_rel"])
    suitepack = load_suitepack(suitepack_path)
    _validate_jsonschema(suitepack, "brain_corpus_suitepack_v1", schema_dir)

    for case in suitepack["cases"]:
        ctx = _load_json(suitepack_path.parent / case["context_rel"])
        _validate_jsonschema(ctx, "brain_context_v1", schema_dir)
        ref_decision = _load_json(suitepack_path.parent / case["decision_ref_rel"])
        _validate_jsonschema(ref_decision, "brain_decision_v1", schema_dir)

    # 2) Case count hard gate.
    if len(suitepack["cases"]) < 100:
        _fail("INVALID:CASECOUNT_LT_100")

    # 3) Toolchain checks.
    toolchain = {
        "kernel": _validate_toolchain_manifest(config_dir / str(pack["toolchain_manifest_kernel_rel"]), schema_dir),
        "py": _validate_toolchain_manifest(config_dir / str(pack["toolchain_manifest_py_rel"]), schema_dir),
        "rust": _validate_toolchain_manifest(config_dir / str(pack["toolchain_manifest_rust_rel"]), schema_dir),
        "lean": _validate_toolchain_manifest(config_dir / str(pack["toolchain_manifest_lean_rel"]), schema_dir),
    }

    # 4) Structural scans.
    _scan_rust_structure(_kernel_crate_dir() / "src")

    # 5) Sealed rebuild.
    _kernel_hash = _sealed_rebuild_kernel(rust_tool=toolchain["rust"], kernel_tool=toolchain["kernel"])

    # 6) Sealed Lean replay.
    proof_path = state_dir / "attempts" / "kernel.brain.proof.lean"
    lean_receipt = _sealed_lean_replay(
        lean_tool=toolchain["lean"],
        proof_path=proof_path,
        state_dir=state_dir,
    )

    # 7) Require sealed orchestrator source bundle.
    _validate_orchestrator_source_bundle(state_dir)

    # 8) Run kernel suite twice for determinism.
    out1 = repo_root / "runs" / "_v15_1_verify_replay" / "suite_run_1"
    out2 = repo_root / "runs" / "_v15_1_verify_replay" / "suite_run_2"

    rc1, _stdout1, _stderr1 = _run_kernel_brain_suite(
        kernel_tool=toolchain["kernel"],
        suitepack_path=suitepack_path,
        out_dir=out1,
    )
    if rc1 not in (0, 40):
        _fail(f"INVALID:KERNEL_EXIT_CODE:{rc1}")
    if rc1 == 40:
        _fail("INVALID:BRAIN_DECISION_MISMATCH")

    report1, branch1, _kernel_perf1, case_rows1, case_metrics1 = _validate_suite_outputs(
        suitepack=suitepack,
        suitepack_path=suitepack_path,
        kernel_out_dir=out1,
        schema_dir=schema_dir,
    )

    rc2, _stdout2, _stderr2 = _run_kernel_brain_suite(
        kernel_tool=toolchain["kernel"],
        suitepack_path=suitepack_path,
        out_dir=out2,
    )
    if rc2 not in (0, 40):
        _fail(f"INVALID:KERNEL_EXIT_CODE:{rc2}")
    if rc2 == 40:
        _fail("INVALID:BRAIN_DECISION_MISMATCH")

    report2, branch2, _kernel_perf2, case_rows2, case_metrics2 = _validate_suite_outputs(
        suitepack=suitepack,
        suitepack_path=suitepack_path,
        kernel_out_dir=out2,
        schema_dir=schema_dir,
    )

    if _canonical_hash(out1 / "kernel" / "reports" / "brain_suite_report_v1.json") != _canonical_hash(
        out2 / "kernel" / "reports" / "brain_suite_report_v1.json"
    ):
        _fail("INVALID:NONDETERMINISTIC_BRAIN")

    hashes_1 = [row["kernel_hash"] for row in case_rows1]
    hashes_2 = [row["kernel_hash"] for row in case_rows2]
    if hashes_1 != hashes_2:
        _fail("INVALID:NONDETERMINISTIC_BRAIN")

    if report1["ledger_head_hash"] != report2["ledger_head_hash"] or report1["trace_head_hash"] != report2["trace_head_hash"]:
        _fail("INVALID:NONDETERMINISTIC_BRAIN")

    candidate_1 = [int(row["candidate_steps_u64"]) for row in case_metrics1]
    candidate_2 = [int(row["candidate_steps_u64"]) for row in case_metrics2]
    if candidate_1 != candidate_2:
        _fail("INVALID:NONDETERMINISTIC_BRAIN")

    # 9) Branch diversity gate.
    distinct = int(branch1["distinct_branch_signatures"])
    non_trivial = int(branch1["non_trivial_rule_path_cases"])
    if not (distinct >= 100 or non_trivial >= 100):
        _fail("INVALID:INSUFFICIENT_BRANCH_DIVERSITY")
    if branch1 != branch2:
        _fail("INVALID:NONDETERMINISTIC_BRAIN")

    # 10) Perf gate from real kernel counters + Python baseline.
    contexts = []
    for case in suitepack["cases"]:
        contexts.append(_load_json(suitepack_path.parent / case["context_rel"]))

    from cdel.v15_1.brain.brain_decision_v1 import brain_decide_v15_1 as baseline_brain_decide_v15_1

    perf_report = compute_brain_perf_report(
        contexts=contexts,
        baseline_fn=baseline_brain_decide_v15_1,
        candidate_case_metrics=case_metrics1,
    )
    if perf_report["candidate_brain_opcodes_total"] <= 0:
        _fail("INVALID:PERF_CANDIDATE_ZERO")
    if len(perf_report["per_case"]) != len(contexts):
        _fail("INVALID:PERF_REPORT_INCONSISTENT")
    if perf_report["candidate_brain_opcodes_total"] > (perf_report["baseline_brain_opcodes_total"] * 1000):
        _fail("INVALID:BRAIN_PERF_REGRESSION")

    # Persist measured perf report into run state for audit.
    perf_out_path = state_dir / "kernel_brain_perf_report_v1.json"
    write_canon_json(perf_out_path, perf_report)
    _validate_jsonschema(_load_json(perf_out_path), "kernel_brain_perf_report_v1", schema_dir)

    # Persist toolchain + lean replay evidence.
    write_canon_json(
        state_dir / "toolchain_validation_receipt_v1.json",
        {
            "schema_version": "toolchain_validation_receipt_v1",
            "kernel_binary_sha256": _kernel_hash,
            "validated_tools": [
                {
                    "role": tool["role"],
                    "manifest_path": tool["manifest_path"],
                    "checker_realpath": tool["checker_realpath"],
                    "checker_executable_hash": tool["checker_executable_hash"],
                    "computed_hash": tool["computed_hash"],
                }
                for tool in [toolchain["kernel"], toolchain["py"], toolchain["rust"], toolchain["lean"]]
            ],
        },
    )
    write_canon_json(state_dir / "lean_replay_receipt_v1.json", lean_receipt)

    # Copy first suite artifacts into state for deterministic replay evidence.
    state_suite_dir = state_dir / "brain_suite"
    if state_suite_dir.exists():
        shutil.rmtree(state_suite_dir)
    shutil.copytree(out1, state_suite_dir)

    print("VALID")
    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_sas_kernel_v15_1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        verify(Path(args.state_dir), mode=args.mode)
    except V15_1KernelError as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
