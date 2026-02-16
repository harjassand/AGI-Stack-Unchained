"""Fail-closed verifier for RSI SAS-Kernel v15.0."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from .kernel_equivalence_v1 import build_equiv_report, canonical_hash_json
from .kernel_ledger_v1 import load_ledger, validate_ledger_chain
from .kernel_perf_v1 import compute_control_opcode_gate
from .kernel_pinning_v1 import (
    ensure_native_kernel_binary,
    load_toolchain_manifest,
    verify_kernel_binary_hash,
)
from .kernel_run_spec_v1 import load_run_spec
from .kernel_snapshot_v1 import load_snapshot
from .kernel_trace_v1 import load_trace, validate_trace_chain

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


class SASKernelError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise SASKernelError(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema_dir() -> Path:
    return _repo_root() / "Genesis" / "schema" / "v15_0"


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


def _load_json(path: Path) -> dict[str, Any]:
    obj = load_canon_json(path)
    if not isinstance(obj, dict):
        _fail("INVALID:SCHEMA_FAIL")
    return obj


def _sha256_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _stable_run_receipt_hash(obj: dict[str, Any]) -> str:
    payload = dict(obj)
    payload.pop("generated_utc", None)
    payload.pop("run_id", None)
    payload.pop("receipt_hash", None)
    return sha256_prefixed(canon_bytes(payload))


def _scan_lean_forbidden(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for token in ["axiom", "sorry", "admit", "unsafe", "partial"]:
        if re.search(rf"\b{re.escape(token)}\b", text):
            _fail("INVALID:LEAN_FORBIDDEN_TOKEN")


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


def _scan_python_shims(repo_root: Path) -> None:
    candidates = [
        repo_root / "Extension-1" / "agi-orchestrator" / "orchestrator" / "run_campaign_v1.py",
        repo_root / "Extension-1" / "agi-orchestrator" / "orchestrator" / "kernel_dispatch_v1.py",
    ]
    for path in candidates:
        if not path.exists():
            _fail("INVALID:PY_SHIM_MISSING")
        text = path.read_text(encoding="utf-8")
        forbidden = [
            "orchestrator.run",
            "orchestrator.promote",
            "orchestrator.rsi_swarm",
            "orchestrator.rsi_omega",
        ]
        for token in forbidden:
            if token in text:
                _fail("INVALID:SPAWNED_FORBIDDEN_ORCHESTRATOR")
    if "kernel_dispatch_v1" not in (candidates[0]).read_text(encoding="utf-8"):
        _fail("INVALID:PY_SHIM_DISPATCH")


def _validate_toolchain_manifests(config_dir: Path, pack: dict[str, Any], schema_dir: Path) -> dict[str, dict[str, Any]]:
    toolchains = {
        "kernel": config_dir / str(pack["toolchain_manifest_kernel_rel"]),
        "py": config_dir / str(pack["toolchain_manifest_py_rel"]),
        "rust": config_dir / str(pack["toolchain_manifest_rust_rel"]),
        "lean": config_dir / str(pack["toolchain_manifest_lean_rel"]),
    }
    loaded: dict[str, dict[str, Any]] = {}
    for kind, path in toolchains.items():
        obj = _load_json(path)
        _validate_jsonschema(obj, "toolchain_manifest_v15", schema_dir)
        load_toolchain_manifest(path)
        loaded[kind] = obj
    return loaded


def _validate_case_outputs(repo_root: Path, case: dict[str, Any], schema_dir: Path) -> tuple[str, str]:
    case_out = repo_root / case["case_out_dir_rel"]
    kernel_root = case_out / "kernel"

    snapshot_path = kernel_root / "snapshot" / "immutable_tree_snapshot_v1.json"
    promotion_path = case_out / "promotion" / "kernel_promotion_bundle_v1.json"
    trace_path = kernel_root / "trace" / "kernel_trace_v1.jsonl"
    ledger_path = kernel_root / "ledger" / "kernel_ledger_v1.jsonl"
    receipt_path = kernel_root / "receipts" / "kernel_run_receipt_v1.json"

    for path in [snapshot_path, promotion_path, trace_path, ledger_path, receipt_path]:
        if not path.exists():
            _fail("INVALID:MISSING_ARTIFACT")

    snapshot = _load_json(snapshot_path)
    _validate_jsonschema(snapshot, "immutable_tree_snapshot_v1", schema_dir)
    promotion = _load_json(promotion_path)
    _validate_jsonschema(promotion, "kernel_activation_receipt_v1", schema_dir) if promotion.get("schema_version") == "kernel_activation_receipt_v1" else None

    trace = load_trace(trace_path)
    ledger = load_ledger(ledger_path)
    validate_trace_chain(trace)
    validate_ledger_chain(ledger)

    for event in trace:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        argv = payload.get("argv")
        if isinstance(argv, list):
            joined = " ".join(str(x) for x in argv)
            if re.search(r"python\w*\s+-m\s+orchestrator\.", joined):
                _fail("INVALID:SPAWNED_FORBIDDEN_ORCHESTRATOR")
            if "orchestrator/run.py" in joined or "orchestrator/promote.py" in joined:
                _fail("INVALID:SPAWNED_FORBIDDEN_ORCHESTRATOR")

    ref_snapshot_path = repo_root / case["reference_snapshot_rel"]
    ref_promotion_path = repo_root / case["reference_promotion_bundle_rel"]
    if not ref_snapshot_path.exists() or not ref_promotion_path.exists():
        _fail("INVALID:REFERENCE_MISSING")

    ref_snapshot = _load_json(ref_snapshot_path)
    _validate_jsonschema(ref_snapshot, "immutable_tree_snapshot_v1", schema_dir)
    if ref_snapshot.get("root_hash_sha256") != snapshot.get("root_hash_sha256"):
        _fail("INVALID:SNAPSHOT_PARITY")
    if ref_snapshot.get("files") != snapshot.get("files"):
        _fail("INVALID:SNAPSHOT_PARITY")

    ref_prom_hash = canonical_hash_json(ref_promotion_path)
    kernel_prom_hash = canonical_hash_json(promotion_path)
    if ref_prom_hash != kernel_prom_hash:
        _fail("INVALID:PROMOTION_PARITY")

    receipt = _load_json(receipt_path)
    _validate_jsonschema(receipt, "kernel_run_receipt_v1", schema_dir)
    stable = _stable_run_receipt_hash(receipt)
    if receipt.get("receipt_hash") != stable:
        _fail("INVALID:RUN_RECEIPT_HASH")

    return str(ref_snapshot.get("root_hash_sha256")), stable


def _sealed_rebuild_and_hash(repo_root: Path) -> str:
    crate_dir = repo_root / "CDEL-v2" / "cdel" / "v15_0" / "rust" / "agi_kernel_rs_v1"
    result = subprocess.run(
        ["cargo", "build", "--release", "--locked", "--offline"],
        cwd=crate_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _fail("INVALID:KERNEL_BUILD_REPLAY")
    binary = crate_dir / "target" / "release" / "agi_kernel_v15"
    if not binary.exists():
        _fail("INVALID:KERNEL_BUILD_REPLAY")
    ensure_native_kernel_binary(binary)
    return _sha256_file(binary)


def _sealed_lean_replay(repo_root: Path, lean_manifest: dict[str, Any], proof_path: Path) -> None:
    argv = list(lean_manifest["invocation_template"])
    argv.append(str(proof_path))
    result = subprocess.run(argv, cwd=repo_root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        _fail("INVALID:LEAN_REPLAY")


def _replay_kernel_for_determinism(repo_root: Path, case: dict[str, Any], kernel_hash: str) -> None:
    crate_dir = repo_root / "CDEL-v2" / "cdel" / "v15_0" / "rust" / "agi_kernel_rs_v1"
    binary = crate_dir / "target" / "release" / "agi_kernel_v15"
    verify_kernel_binary_hash(binary, kernel_hash)

    spec_src = repo_root / case["run_spec_rel"]
    run_spec = load_run_spec(spec_src)
    replay_root = repo_root / "runs" / "_v15_verify_replay"
    replay_root.mkdir(parents=True, exist_ok=True)

    receipts: list[dict[str, Any]] = []
    ledger_heads: list[str] = []
    trace_heads: list[str] = []
    snapshots: list[str] = []

    for idx in [1, 2]:
        out_rel = f"runs/_v15_verify_replay/{case['capability_id'].lower()}_{idx}"
        replay_case = repo_root / out_rel
        if replay_case.exists():
            shutil.rmtree(replay_case)

        local_spec = dict(run_spec)
        paths = dict(local_spec["paths"])
        paths["out_dir_rel"] = out_rel
        local_spec["paths"] = paths
        local_spec_path = replay_root / f"{case['capability_id'].lower()}_{idx}.kernel_run_spec_v1.json"
        write_canon_json(local_spec_path, local_spec)

        result = subprocess.run(
            [str(binary), "run", "--run_spec", str(local_spec_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            _fail(f"INVALID:KERNEL_EXIT_CODE:{result.returncode}")

        receipt_path = replay_case / "kernel" / "receipts" / "kernel_run_receipt_v1.json"
        trace_path = replay_case / "kernel" / "trace" / "kernel_trace_v1.jsonl"
        ledger_path = replay_case / "kernel" / "ledger" / "kernel_ledger_v1.jsonl"
        snap_path = replay_case / "kernel" / "snapshot" / "immutable_tree_snapshot_v1.json"
        for path in [receipt_path, trace_path, ledger_path, snap_path]:
            if not path.exists():
                _fail("INVALID:MISSING_ARTIFACT")

        receipt = _load_json(receipt_path)
        receipts.append(receipt)
        trace = load_trace(trace_path)
        ledger = load_ledger(ledger_path)
        validate_trace_chain(trace)
        validate_ledger_chain(ledger)
        ledger_heads.append(ledger[-1]["event_ref_hash"] if ledger else "GENESIS")
        trace_heads.append(trace[-1]["event_ref_hash"] if trace else "GENESIS")
        snap = _load_json(snap_path)
        snapshots.append(str(snap.get("root_hash_sha256")))

    if len(set(ledger_heads)) != 1:
        _fail("INVALID:DETERMINISM_LEDGER")
    if len(set(trace_heads)) != 1:
        _fail("INVALID:DETERMINISM_TRACE")
    if len(set(snapshots)) != 1:
        _fail("INVALID:DETERMINISM_SNAPSHOT")

    stable_hashes = [_stable_run_receipt_hash(r) for r in receipts]
    if len(set(stable_hashes)) != 1:
        _fail("INVALID:DETERMINISM_RECEIPT")


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        _fail("INVALID:MODE_UNSUPPORTED")

    state_dir = state_dir.resolve()
    schema_dir = _schema_dir()
    repo_root = _repo_root()

    config_dir = state_dir.parent / "config"
    pack_path = config_dir / "rsi_sas_kernel_pack_v1.json"
    pack = _load_json(pack_path)
    _validate_jsonschema(pack, "suitepack_v1", schema_dir) if pack.get("schema_version") == "suitepack_v1" else None

    required_pack_keys = {
        "schema_version",
        "kernel_policy_rel",
        "capability_registry_rel",
        "fixture_matrix_rel",
        "suitepack_dev_rel",
        "suitepack_heldout_rel",
        "toolchain_manifest_kernel_rel",
        "toolchain_manifest_py_rel",
        "toolchain_manifest_rust_rel",
        "toolchain_manifest_lean_rel",
    }
    if set(pack.keys()) != required_pack_keys or pack.get("schema_version") != "rsi_sas_kernel_pack_v1":
        _fail("INVALID:SCHEMA_FAIL")

    manifests = _validate_toolchain_manifests(config_dir, pack, schema_dir)

    _scan_rust_structure(repo_root / "CDEL-v2" / "cdel" / "v15_0" / "rust" / "agi_kernel_rs_v1" / "src")
    _scan_python_shims(repo_root)

    proof_path = state_dir / "attempts" / "kernel.proof.lean"
    if not proof_path.exists():
        _fail("INVALID:LEAN_PROOF_MISSING")
    _scan_lean_forbidden(proof_path)

    kernel_hash = _sealed_rebuild_and_hash(repo_root)
    _sealed_lean_replay(repo_root, manifests["lean"], proof_path)

    case_index_path = state_dir / "kernel_case_index_v1.json"
    case_index = _load_json(case_index_path)
    _validate_jsonschema(case_index, "fixture_matrix_v1", schema_dir) if case_index.get("schema_version") == "fixture_matrix_v1" else None
    if case_index.get("schema_version") != "kernel_case_index_v1":
        _fail("INVALID:SCHEMA_FAIL")

    cases = case_index.get("cases")
    if not isinstance(cases, list) or not cases:
        _fail("INVALID:SCHEMA_FAIL")

    for case in cases:
        if not isinstance(case, dict):
            _fail("INVALID:SCHEMA_FAIL")
        required = {
            "capability_id",
            "run_spec_rel",
            "case_out_dir_rel",
            "reference_snapshot_rel",
            "reference_promotion_bundle_rel",
        }
        if set(case.keys()) != required:
            _fail("INVALID:SCHEMA_FAIL")

    # Replay checks (sealed deterministic replay from recorded run specs)
    for case in cases:
        _replay_kernel_for_determinism(repo_root, case, kernel_hash)

    # Case output checks
    for case in cases:
        _validate_case_outputs(repo_root, case, schema_dir)

    # Kernel hash pin in activation receipts
    for case in cases:
        act_path = repo_root / case["case_out_dir_rel"] / "kernel" / "receipts" / "kernel_activation_receipt_v1.json"
        if not act_path.exists():
            _fail("INVALID:ACTIVATION_MISSING")
        activation = _load_json(act_path)
        _validate_jsonschema(activation, "kernel_activation_receipt_v1", schema_dir)
        if activation.get("binary_sha256") != kernel_hash:
            _fail("INVALID:KERNEL_HASH_MISMATCH")

    # Perf gate
    perf = compute_control_opcode_gate(repo_root)
    if perf["candidate_control_opcodes"] * 1000 > perf["baseline_control_opcodes"]:
        _fail("INVALID:PERF_GATE_FAIL")

    # Deterministic print behavior
    print("VALID")
    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_sas_kernel_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()
    try:
        verify(Path(args.state_dir), mode=args.mode)
    except SASKernelError as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
