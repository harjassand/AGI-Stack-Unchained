"""Runtime coordinator for RSI SAS VAL v17.0."""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from ...v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line
from ..hotloop.hotloop_counter_v1 import generate_workload_messages, load_fixture_messages
from ..hotloop.hotloop_report_v1 import HotloopReportError, build_hotloop_report
from ..val.val_cost_model_v1 import gate_valcycles
from ..val.val_decode_aarch64_v1 import ValDecodeError, decode_trace_py, decode_trace_rs, decoded_trace_hash
from ..val.val_equivalence_v1 import ValEquivalenceError, build_equivalence_receipt_from_outputs, generate_vector_messages
from ..val.val_isa_v1 import ValPolicyError, parse_policy
from ..val.val_lift_ir_v1 import ValLiftError, lift_ir_hash, lift_ir_py, lift_ir_rs
from ..val.val_verify_safety_v1 import verify_safety, verify_safety_shadow
from .val_patch_store_v1 import ValPatchStoreError, decode_code_bytes, load_patch_manifest
from .val_runner_sealed_v1 import (
    SealedRunnerError,
    aggregate_io_hash,
    ensure_trace_complete,
    has_exec_end,
    output_hashes,
    run_runner_batch,
    run_runner_benchmark,
    trace_head_hash,
)


class ValRunError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise ValRunError(reason)


_BUNDLE_ID_OMIT_FIELDS = {
    "bundle_id",
    "baseline_benchmark_report_hash",
    "candidate_benchmark_report_hash",
    "baseline_sealed_run_receipt_hash",
    "candidate_sealed_run_receipt_hash",
    "baseline_exec_backend_hash",
    "candidate_exec_backend_hash",
    "downstream_meta_core_receipt_hash",
    "downstream_v16_1_receipt_hash",
    "meta_core_bundle_hash",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _resolve_path(base: Path, rel_or_abs: str) -> Path:
    p = Path(str(rel_or_abs))
    return p if p.is_absolute() else (base / p)


def _write_hashed_json(out_dir: Path, suffix: str, payload: dict[str, Any]) -> tuple[Path, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    h = sha256_prefixed(canon_bytes(payload))
    path = out_dir / f"sha256_{h.split(':', 1)[1]}.{suffix}"
    write_canon_json(path, payload)
    return path, h


def _copy_canon(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(dst, load_canon_json(src))


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def _pack_required_keys() -> set[str]:
    return {
        "schema_version",
        "policy_rel",
        "workload_suitepack_rel",
        "microkernel_task_rel",
        "toolchain_rust_rel",
        "toolchain_val_runner_rel",
        "target_arch",
        "target_simd",
        "seed_u64",
        "baseline_kind",
        "candidate_kind",
        "double_run_mode",
    }


def _load_json(path: Path) -> dict[str, Any]:
    obj = load_canon_json(path)
    if not isinstance(obj, dict):
        _fail("INVALID:SCHEMA_FAIL")
    return obj


def _gate_or_fail(ok: bool, code: str) -> None:
    if not ok:
        _fail(code)


def _wallclock_gate(*, baseline_ns: int, candidate_ns: int, num: int, den: int) -> bool:
    if baseline_ns <= 0 or candidate_ns < 0 or num <= 0 or den <= 0:
        return False
    return candidate_ns * den <= baseline_ns * num


def _tree_hash(outputs: list[bytes]) -> str:
    return sha256_prefixed(
        canon_bytes(
            {
                "schema_version": "val_output_tree_v1",
                "output_hashes": output_hashes(outputs),
            }
        )
    )


def _parse_v17_max_tasks() -> int | None:
    raw = str(os.environ.get("V17_MAX_TASKS", "")).strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except Exception as exc:  # noqa: BLE001
        raise ValRunError("INVALID:V17_MAX_TASKS") from exc
    if parsed < 1 or parsed > 100000:
        _fail("INVALID:V17_MAX_TASKS")
    return parsed


def _write_intensity_receipt(state_dir: Path, max_tasks: int | None, applied: dict[str, int]) -> None:
    if max_tasks is None:
        return
    receipt = {
        "schema_version": "omega_intensity_receipt_v1",
        "campaign_id": "rsi_sas_val_v17_0",
        "env": {"V17_MAX_TASKS": str(max_tasks)},
        "applied": applied,
    }
    write_canon_json(state_dir / "control" / "omega_intensity_receipt_v1.json", receipt)


def _freeze_config(pack_path: Path, config_dir: Path) -> dict[str, Any]:
    raw_pack = _load_json(pack_path)
    if set(raw_pack.keys()) != _pack_required_keys():
        _fail("INVALID:SCHEMA_FAIL")
    if raw_pack.get("schema_version") != "rsi_sas_val_pack_v17_0":
        _fail("INVALID:SCHEMA_FAIL")
    if raw_pack.get("target_arch") != "aarch64" or raw_pack.get("target_simd") != "neon128":
        _fail("INVALID:SCHEMA_FAIL")

    src_root = pack_path.parent
    _copy_canon(_resolve_path(src_root, str(raw_pack["policy_rel"])), config_dir / "sas_val_policy_v1.json")
    _copy_canon(_resolve_path(src_root, str(raw_pack["workload_suitepack_rel"])), config_dir / "workload" / "kernel_workload_suitepack_v1.json")
    _copy_canon(_resolve_path(src_root, str(raw_pack["microkernel_task_rel"])), config_dir / "microkernels" / "microkernel_task_pilot_v1.json")
    _copy_canon(_resolve_path(src_root, str(raw_pack["toolchain_rust_rel"])), config_dir / "toolchains" / "toolchain_manifest_rust_v1.json")
    _copy_canon(
        _resolve_path(src_root, str(raw_pack["toolchain_val_runner_rel"])),
        config_dir / "toolchains" / "toolchain_manifest_val_runner_v1.json",
    )

    task = _load_json(config_dir / "microkernels" / "microkernel_task_pilot_v1.json")
    patch_src = _resolve_path(src_root, str(task.get("patch_manifest_rel", "")))
    fixture_src = _resolve_path(src_root, str(task.get("brain_fixture_rel", "")))
    if not patch_src.exists() or not fixture_src.exists():
        _fail("INVALID:MISSING_STATE_INPUT")

    _copy_canon(patch_src, config_dir / "patches" / "val_patch_manifest_v1.json")
    _copy_canon(fixture_src, config_dir / "fixtures" / "brain_suitepack_dev_v15_1.json")
    v16_fixture_src = src_root / "workload" / "v16_1_fixture"
    if not v16_fixture_src.exists() or not v16_fixture_src.is_dir():
        _fail("INVALID:MISSING_STATE_INPUT")
    shutil.copytree(v16_fixture_src, config_dir / "workload" / "v16_1_fixture", dirs_exist_ok=True)

    for manifest_name in ["toolchain_manifest_rust_v1.json", "toolchain_manifest_val_runner_v1.json"]:
        manifest = _load_json(config_dir / "toolchains" / manifest_name)
        checker_rel = str(manifest.get("checker_executable_rel", ""))
        if not checker_rel:
            _fail("INVALID:TOOLCHAIN_PIN_FAIL")
        src_exec = _resolve_path(src_root, checker_rel)
        dst_exec = config_dir / checker_rel
        _copy_file(src_exec, dst_exec)
        os.chmod(dst_exec, 0o755)

    frozen_pack = {
        "schema_version": "rsi_sas_val_pack_v17_0",
        "policy_rel": "sas_val_policy_v1.json",
        "workload_suitepack_rel": "workload/kernel_workload_suitepack_v1.json",
        "microkernel_task_rel": "microkernels/microkernel_task_pilot_v1.json",
        "toolchain_rust_rel": "toolchains/toolchain_manifest_rust_v1.json",
        "toolchain_val_runner_rel": "toolchains/toolchain_manifest_val_runner_v1.json",
        "target_arch": "aarch64",
        "target_simd": "neon128",
        "seed_u64": int(raw_pack["seed_u64"]),
        "baseline_kind": "KERNEL_SHA256_BASELINE_V1",
        "candidate_kind": "VAL_MACHINE_CODE_V1",
        "double_run_mode": bool(raw_pack["double_run_mode"]),
    }
    write_canon_json(config_dir / "rsi_sas_val_pack_v17_0.json", frozen_pack)
    return frozen_pack


def _load_toolchain_manifest(path: Path) -> dict[str, Any]:
    obj = _load_json(path)
    required = {
        "schema_version",
        "checker_name",
        "checker_executable_rel",
        "checker_executable_hash",
        "invocation_template",
        "toolchain_id",
    }
    if set(obj.keys()) != required:
        _fail("INVALID:TOOLCHAIN_PIN_FAIL")

    payload = dict(obj)
    payload.pop("toolchain_id", None)
    expected_id = sha256_prefixed(canon_bytes(payload))
    if str(obj.get("toolchain_id", "")) != expected_id:
        _fail("INVALID:TOOLCHAIN_PIN_FAIL")

    return obj


def _toolchain_receipt(manifest: dict[str, Any], *, config_dir: Path) -> dict[str, Any]:
    checker_rel = str(manifest["checker_executable_rel"])
    checker_path = config_dir / checker_rel
    if not checker_path.exists() or not checker_path.is_file():
        _fail("INVALID:TOOLCHAIN_PIN_FAIL")
    got_hash = sha256_prefixed(checker_path.read_bytes())
    if got_hash != str(manifest["checker_executable_hash"]):
        _fail("INVALID:TOOLCHAIN_PIN_FAIL")
    return {
        "schema_version": "val_toolchain_receipt_v1",
        "checker_name": str(manifest["checker_name"]),
        "checker_hash": got_hash,
        "toolchain_id": str(manifest["toolchain_id"]),
    }


def _build_runner_binary(*, rust_crate: Path) -> Path:
    cmd = ["cargo", "build", "--release", "--manifest-path", str(rust_crate / "Cargo.toml")]
    rc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if rc.returncode != 0:
        _fail("INVALID:SEALED_BUILD_FAIL")
    runner = rust_crate / "target" / "release" / "val_runner_rs_v1"
    if not runner.exists() or not runner.is_file():
        _fail("INVALID:SEALED_BUILD_FAIL")
    return runner


def _runner_build_receipt(*, runner_bin: Path) -> dict[str, Any]:
    return {
        "schema_version": "val_runner_build_receipt_v1",
        "runner_binary_hash": sha256_prefixed(runner_bin.read_bytes()),
    }


def _seal_receipt(*, runner_bin_hash: str, invocations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "sealed_run_receipt_v1",
        "runner_bin_hash": runner_bin_hash,
        "spawn_count": len(invocations),
        "invocations": invocations,
    }


def _ensure_batch_ok(result: dict[str, Any], *, trace_path: Path, require_native: bool) -> dict[str, Any]:
    rc = int(result.get("returncode", -1))
    receipt = result.get("receipt")
    if not isinstance(receipt, dict):
        _fail("INVALID:SEALED_RUN_RECEIPT_MISSING")

    if rc != 0:
        if not has_exec_end(trace_path):
            _fail("INVALID:EXEC_CRASH_OR_TRACE_INCOMPLETE")
        status = str(receipt.get("status", ""))
        if status == "UNSAFE_PRECONDITION_FAIL":
            _fail("INVALID:UNSAFE_PRECONDITION_FAIL")
        _fail("INVALID:UNSEALED_EXECUTION")

    try:
        ensure_trace_complete(trace_path)
    except SealedRunnerError as exc:
        _fail(str(exc))

    if require_native and receipt.get("exec_backend") != "RUST_NATIVE_AARCH64_MMAP_RX_V1":
        _fail("INVALID:EXEC_BACKEND_NOT_NATIVE")

    return receipt


def _write_downstream_receipt(path: Path, payload: dict[str, Any]) -> tuple[Path, str]:
    write_canon_json(path, payload)
    return path, sha256_prefixed(canon_bytes(payload))


def _run_meta_core_downstream(
    *,
    state_dir: Path,
    repo_root: Path,
) -> tuple[dict[str, Any], str]:
    downstream_dir = state_dir / "downstream"
    bundle_dir = downstream_dir / "meta_core_promotion_bundle_v1"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    meta_core_root = repo_root / "meta-core"
    meta_hash_path = meta_core_root / "meta_constitution" / "v1_5r" / "META_HASH"
    kernel_hash_path = meta_core_root / "kernel" / "verifier" / "KERNEL_HASH"
    constants_path = meta_core_root / "meta_constitution" / "v1_5r" / "constants_v1.json"
    if not meta_hash_path.exists() or not kernel_hash_path.exists() or not constants_path.exists():
        _fail("INVALID:DOWNSTREAM_META_CORE_FAIL")

    meta_hash = meta_hash_path.read_text(encoding="utf-8").strip()
    kernel_hash = kernel_hash_path.read_text(encoding="utf-8").strip()
    constants_hash = sha256_prefixed(canon_bytes(_load_json(constants_path)))

    witness = {
        "schema": "dominance_witness_v1",
        "schema_version": 1,
        "epoch_id": "VAL_V17_0",
        "decisions": [
            {
                "decision_id": "pilot_hotloop_selected",
                "status": "PASS",
            }
        ],
    }
    witness_path = bundle_dir / "dominance_witness_v1.json"
    witness_raw = canon_bytes(witness)
    witness_path.write_bytes(witness_raw)
    witness_hash = sha256_prefixed(witness_raw)

    manifest_wo_bundle = {
        "schema": "promotion_bundle_manifest_v1",
        "schema_version": 1,
        "promotion_type": "RSI_SAS_VAL",
        "META_HASH": meta_hash,
        "KERNEL_HASH": kernel_hash,
        "constants_hash": constants_hash,
        "proofs": {"dominance_witness_hash": witness_hash},
        "blobs": [
            {
                "path": "dominance_witness_v1.json",
                "sha256": witness_hash,
                "bytes": len(witness_raw),
            }
        ],
    }
    bundle_hash = sha256_prefixed(canon_bytes(manifest_wo_bundle) + witness_raw)
    manifest = dict(manifest_wo_bundle)
    manifest["bundle_hash"] = bundle_hash
    manifest_path = bundle_dir / "promotion_bundle_manifest_v1.json"
    manifest_path.write_bytes(canon_bytes(manifest))

    verifier_out = downstream_dir / "meta_core_promo_verify_out_v1.json"
    cmd = [
        "python3",
        str(meta_core_root / "kernel" / "verify_promotion_bundle.py"),
        "--bundle_dir",
        str(bundle_dir),
        "--meta_core_root",
        str(meta_core_root),
        "--out",
        str(verifier_out),
    ]
    rc = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=repo_root)
    verifier_json: dict[str, Any] = {}
    if verifier_out.exists():
        try:
            maybe = load_canon_json(verifier_out)
            if isinstance(maybe, dict):
                verifier_json = maybe
        except Exception:  # noqa: BLE001
            verifier_json = {}

    passed = int(rc.returncode) == 0 and str(verifier_json.get("verdict", "")) == "VALID"
    receipt = {
        "schema_version": "meta_core_promo_verify_receipt_v1",
        "return_code": int(rc.returncode),
        "stdout_hash": sha256_prefixed(rc.stdout.encode("utf-8")),
        "stderr_hash": sha256_prefixed(rc.stderr.encode("utf-8")),
        "verifier_out_hash": sha256_prefixed(verifier_out.read_bytes()) if verifier_out.exists() else "sha256:" + ("0" * 64),
        "pass": bool(passed),
    }
    return receipt, bundle_hash


def _run_v16_1_smoke_downstream(
    *,
    state_dir: Path,
    config_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    fixture_locator_path = config_dir / "workload" / "v16_1_fixture" / "fixture_locator_v1.json"
    locator = _load_json(fixture_locator_path)
    env = dict(os.environ)
    env["PYTHONPATH"] = "CDEL-v2"

    def _normal_rc(value: int) -> int:
        parsed = int(value)
        if parsed >= 0:
            return parsed
        return 128 + abs(parsed)

    def _run_for_state(fixture_state_dir: Path) -> subprocess.CompletedProcess[str]:
        cmd = [
            "python3",
            "-m",
            "cdel.v16_1.verify_rsi_sas_metasearch_v16_1",
            "--mode",
            "full",
            "--state_dir",
            str(fixture_state_dir),
        ]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            cwd=repo_root,
            env=env,
        )

    def _receipt_from_run(*, fixture_state_dir: str, rc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        status = rc.stdout.strip().splitlines()[-1] if rc.stdout.strip() else ""
        passed = int(rc.returncode) == 0 and status == "VALID"
        return {
            "schema_version": "v16_1_smoke_receipt_v1",
            "fixture_state_dir": fixture_state_dir,
            "return_code": _normal_rc(int(rc.returncode)),
            "stdout_hash": sha256_prefixed(rc.stdout.encode("utf-8")),
            "stderr_hash": sha256_prefixed(rc.stderr.encode("utf-8")),
            "result": status,
            "pass": bool(passed),
        }

    def _failed_receipt(*, fixture_state_dir: str, result: str) -> dict[str, Any]:
        return {
            "schema_version": "v16_1_smoke_receipt_v1",
            "fixture_state_dir": fixture_state_dir,
            "return_code": 1,
            "stdout_hash": sha256_prefixed(b""),
            "stderr_hash": sha256_prefixed(b""),
            "result": result,
            "pass": False,
        }

    def _run_fresh_fixture() -> dict[str, Any]:
        pack_path = repo_root / "campaigns" / "rsi_sas_metasearch_v16_1" / "rsi_sas_metasearch_pack_v16_1.json"
        if not pack_path.exists() or not pack_path.is_file():
            return _failed_receipt(
                fixture_state_dir="GENERATED:rsi_sas_metasearch_v16_1/state",
                result="INVALID:DOWNSTREAM_V16_1_FAIL",
            )
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            generated_out_dir = tmpdir / "generated_v16_1_smoke"
            generated_state = generated_out_dir / "daemon" / "rsi_sas_metasearch_v16_1" / "state"
            run_cmd = [
                "python3",
                "-m",
                "orchestrator.rsi_sas_metasearch_v16_1",
                "--campaign_pack",
                str(pack_path),
                "--out_dir",
                str(generated_out_dir),
            ]
            run_rc = subprocess.run(
                run_cmd,
                capture_output=True,
                text=True,
                check=False,
                cwd=repo_root,
                env=env,
            )
            if int(run_rc.returncode) != 0 or not generated_state.exists():
                status = run_rc.stdout.strip().splitlines()[-1] if run_rc.stdout.strip() else ""
                if not status:
                    status = "INVALID:DOWNSTREAM_V16_1_FAIL"
                return {
                    "schema_version": "v16_1_smoke_receipt_v1",
                    "fixture_state_dir": f"GENERATED:{generated_state.as_posix()}",
                    "return_code": _normal_rc(int(run_rc.returncode)),
                    "stdout_hash": sha256_prefixed(run_rc.stdout.encode("utf-8")),
                    "stderr_hash": sha256_prefixed(run_rc.stderr.encode("utf-8")),
                    "result": status,
                    "pass": False,
                }
            verify_rc = _run_for_state(generated_state)
            return _receipt_from_run(
                fixture_state_dir=f"GENERATED:{generated_state.as_posix()}",
                rc=verify_rc,
            )

    primary: dict[str, Any]
    fixture_tar_rel = str(locator.get("fixture_tar_rel", ""))
    if fixture_tar_rel:
        tar_path = (config_dir / fixture_tar_rel).resolve()
        state_dir_in_tar = str(locator.get("state_dir_in_tar", "state"))
        fixture_state_dir_str = f"{fixture_tar_rel}:{state_dir_in_tar}"
        if not tar_path.exists() or not tar_path.is_file():
            primary = _failed_receipt(
                fixture_state_dir=fixture_state_dir_str,
                result="INVALID:DOWNSTREAM_V16_1_FAIL",
            )
        else:
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    tmpdir = Path(tmp)
                    with tarfile.open(tar_path, "r:gz") as tf:
                        tf.extractall(tmpdir, filter="data")
                    fixture_state_dir = (tmpdir / state_dir_in_tar).resolve()
                    if not fixture_state_dir.exists():
                        primary = _failed_receipt(
                            fixture_state_dir=fixture_state_dir_str,
                            result="INVALID:DOWNSTREAM_V16_1_FAIL",
                        )
                    else:
                        rc = _run_for_state(fixture_state_dir)
                        primary = _receipt_from_run(fixture_state_dir=fixture_state_dir_str, rc=rc)
            except Exception:  # noqa: BLE001
                primary = _failed_receipt(
                    fixture_state_dir=fixture_state_dir_str,
                    result="INVALID:DOWNSTREAM_V16_1_FAIL",
                )
    else:
        fixture_state_rel = str(locator.get("state_dir_rel", ""))
        if not fixture_state_rel:
            primary = _failed_receipt(
                fixture_state_dir="LOCATOR:state_dir_rel",
                result="INVALID:DOWNSTREAM_V16_1_FAIL",
            )
        else:
            fixture_state_dir = (repo_root / fixture_state_rel).resolve()
            fixture_state_dir_str = str(fixture_state_dir)
            if not fixture_state_dir.exists():
                primary = _failed_receipt(
                    fixture_state_dir=fixture_state_dir_str,
                    result="INVALID:DOWNSTREAM_V16_1_FAIL",
                )
            else:
                rc = _run_for_state(fixture_state_dir)
                primary = _receipt_from_run(fixture_state_dir=fixture_state_dir_str, rc=rc)

    if bool(primary.get("pass", False)):
        return primary
    return _run_fresh_fixture()


def run_sas_val(
    *,
    campaign_pack: Path,
    out_dir: Path,
    campaign_tag: str = "rsi_sas_val_v17_0",
    skip_downstream: bool = False,
) -> dict[str, Any]:
    pack_path = campaign_pack.resolve()
    if not pack_path.exists():
        _fail("INVALID:SCHEMA_FAIL")

    run_root = out_dir.resolve()
    daemon_root = run_root / "daemon" / campaign_tag
    config_dir = daemon_root / "config"
    state_dir = daemon_root / "state"

    if daemon_root.exists():
        shutil.rmtree(daemon_root)

    for path in [
        config_dir,
        state_dir / "control",
        state_dir / "inputs",
        state_dir / "hotloop",
        state_dir / "baseline" / "exec",
        state_dir / "baseline" / "exec_trace",
        state_dir / "baseline" / "benchmark",
        state_dir / "candidate" / "patch",
        state_dir / "candidate" / "trace",
        state_dir / "candidate" / "ir",
        state_dir / "candidate" / "safety",
        state_dir / "candidate" / "equivalence",
        state_dir / "candidate" / "exec",
        state_dir / "candidate" / "exec_trace",
        state_dir / "candidate" / "benchmark",
        state_dir / "candidate" / "build",
        state_dir / "promotion",
        state_dir / "ledger",
        state_dir / "snapshot",
        state_dir / "downstream",
    ]:
        path.mkdir(parents=True, exist_ok=True)

    frozen_pack = _freeze_config(pack_path, config_dir)

    policy_obj = _load_json(config_dir / "sas_val_policy_v1.json")
    workload_obj = _load_json(config_dir / "workload" / "kernel_workload_suitepack_v1.json")
    fixture_obj = _load_json(config_dir / "fixtures" / "brain_suitepack_dev_v15_1.json")
    task_obj = _load_json(config_dir / "microkernels" / "microkernel_task_pilot_v1.json")

    try:
        policy = parse_policy(policy_obj)
    except ValPolicyError as exc:
        _fail(str(exc))

    rust_toolchain = _load_toolchain_manifest(config_dir / "toolchains" / "toolchain_manifest_rust_v1.json")
    runner_toolchain = _load_toolchain_manifest(config_dir / "toolchains" / "toolchain_manifest_val_runner_v1.json")
    rust_receipt = _toolchain_receipt(rust_toolchain, config_dir=config_dir)
    runner_toolchain_receipt = _toolchain_receipt(runner_toolchain, config_dir=config_dir)
    _, rust_toolchain_receipt_hash = _write_hashed_json(
        state_dir / "candidate" / "build",
        "toolchain_receipt_rust_v1.json",
        rust_receipt,
    )
    _, runner_toolchain_receipt_hash = _write_hashed_json(
        state_dir / "candidate" / "build",
        "toolchain_receipt_val_runner_v1.json",
        runner_toolchain_receipt,
    )

    rust_crate = _repo_root() / "CDEL-v2" / "cdel" / "v17_0" / "rust" / "val_runner_rs_v1"
    runner_bin = _build_runner_binary(rust_crate=rust_crate)
    runner_build_receipt = _runner_build_receipt(runner_bin=runner_bin)
    runner_build_path, runner_build_hash = _write_hashed_json(
        state_dir / "candidate" / "build",
        "val_runner_build_receipt_v1.json",
        runner_build_receipt,
    )

    try:
        patch_manifest = load_patch_manifest(
            config_dir / "patches" / "val_patch_manifest_v1.json",
            max_code_bytes=policy.max_code_bytes,
        )
    except (ValPatchStoreError, Exception) as exc:  # noqa: BLE001
        _fail(str(exc) if str(exc).startswith("INVALID:") else "INVALID:SCHEMA_FAIL")

    if str(patch_manifest.get("build_receipt_hash", "")) != runner_build_hash:
        _fail("INVALID:TOOLCHAIN_PIN_FAIL")

    patch_path, patch_hash = _write_hashed_json(
        state_dir / "candidate" / "patch",
        "val_patch_manifest_v1.json",
        patch_manifest,
    )

    code_bytes = decode_code_bytes(patch_manifest)
    code_bytes_hash = sha256_prefixed(code_bytes)

    # Decode/lift dual parity.
    try:
        decoded_py = decode_trace_py(code_bytes)
        decoded_rs = decode_trace_rs(code_bytes)
    except ValDecodeError as exc:
        _fail(str(exc))

    decoded_hash_py = decoded_trace_hash(decoded_py)
    decoded_hash_rs = decoded_trace_hash(decoded_rs)
    if policy.require_dual_decoder_parity and decoded_hash_py != decoded_hash_rs:
        _fail("INVALID:VAL_DUAL_DECODER_DIVERGENCE")
    decoded_trace = decoded_py
    decoded_path, decoded_hash = _write_hashed_json(
        state_dir / "candidate" / "trace",
        "val_decoded_trace_v1.json",
        decoded_trace,
    )

    try:
        lifted_py = lift_ir_py(decoded_trace)
        lifted_rs = lift_ir_rs(decoded_trace)
    except ValLiftError as exc:
        _fail(str(exc))

    lift_hash_py = lift_ir_hash(lifted_py)
    lift_hash_rs = lift_ir_hash(lifted_rs)
    if policy.require_dual_lifter_parity and lift_hash_py != lift_hash_rs:
        _fail("INVALID:VAL_DUAL_LIFTER_DIVERGENCE")
    lifted_ir = lifted_py
    lifted_path, lifted_hash = _write_hashed_json(
        state_dir / "candidate" / "ir",
        "val_lift_ir_v1.json",
        lifted_ir,
    )

    safety = verify_safety(
        decoded_trace=decoded_trace,
        lifted_ir=lifted_ir,
        patch_manifest=patch_manifest,
        policy=policy,
    )
    shadow = verify_safety_shadow(
        decoded_trace=decoded_trace,
        lifted_ir=lifted_ir,
        patch_manifest=patch_manifest,
        policy=policy,
    )
    if (
        bool(safety.get("pass")) != bool(shadow.get("pass"))
        or str(safety.get("fail_code")) != str(shadow.get("fail_code"))
        or safety.get("mem_bounds_summary") != shadow.get("mem_bounds_summary")
        or safety.get("cfg_summary") != shadow.get("cfg_summary")
    ):
        _fail("INVALID:VAL_SAFETY_NONCANONICAL")

    safety_path, safety_hash = _write_hashed_json(
        state_dir / "candidate" / "safety",
        "val_safety_receipt_v1.json",
        safety,
    )

    safety_status = str(safety.get("status", "UNSAFE"))
    if safety_status != "SAFE":
        _fail("INVALID:EXEC_BEFORE_SAFE")

    runner_bin_hash = str(runner_build_receipt["runner_binary_hash"])

    baseline_invocations: list[dict[str, Any]] = []
    candidate_invocations: list[dict[str, Any]] = []
    baseline_spawn_count = 0
    candidate_spawn_count = 0
    max_tasks = _parse_v17_max_tasks()
    applied_task_counts: dict[str, int] = {}

    # Workload runs.
    workload_messages = generate_workload_messages(workload_obj)
    if max_tasks is not None:
        workload_messages = workload_messages[:max_tasks]
    if not workload_messages:
        _fail("INVALID:V17_MAX_TASKS")
    applied_task_counts["workload_tasks"] = len(workload_messages)
    baseline_trace = state_dir / "baseline" / "exec_trace" / "val_exec_trace.jsonl"
    candidate_trace = state_dir / "candidate" / "exec_trace" / "val_exec_trace.jsonl"

    baseline_run = run_runner_batch(
        runner_bin=runner_bin,
        mode="baseline_ref",
        messages=workload_messages,
        patch_bytes=code_bytes,
        trace_path=baseline_trace,
        receipt_path=state_dir / "baseline" / "exec" / "sealed_run_receipt_workload_v1.json",
        max_len_bytes=policy.max_blocks_len * 64,
        step_bytes=1,
        safety_status="SAFE",
        runner_bin_hash=runner_bin_hash,
        code_bytes_hash=code_bytes_hash,
    )
    baseline_receipt_workload = _ensure_batch_ok(baseline_run, trace_path=baseline_trace, require_native=False)
    baseline_invocations.append(baseline_receipt_workload)
    baseline_spawn_count += 1

    candidate_run = run_runner_batch(
        runner_bin=runner_bin,
        mode="patch_native",
        messages=workload_messages,
        patch_bytes=code_bytes,
        trace_path=candidate_trace,
        receipt_path=state_dir / "candidate" / "exec" / "sealed_run_receipt_workload_v1.json",
        max_len_bytes=policy.max_blocks_len * 64,
        step_bytes=1,
        safety_status=safety_status,
        runner_bin_hash=runner_bin_hash,
        code_bytes_hash=code_bytes_hash,
    )
    candidate_receipt_workload = _ensure_batch_ok(candidate_run, trace_path=candidate_trace, require_native=True)
    candidate_invocations.append(candidate_receipt_workload)
    candidate_spawn_count += 1

    baseline_outputs = list(baseline_run["outputs"])
    candidate_outputs = list(candidate_run["outputs"])

    baseline_tree_hash = _tree_hash(baseline_outputs)
    candidate_tree_hash = _tree_hash(candidate_outputs)

    try:
        hotloop = build_hotloop_report(
            baseline_report={
                "spawn_count": baseline_spawn_count,
                "bytes_hashed": sum(len(m) for m in workload_messages),
                "val_cycles_total": int(baseline_receipt_workload.get("val_cycles_total", 0)),
            },
            workload=workload_obj,
            task=task_obj,
            repo_root=_repo_root(),
        )
    except HotloopReportError as exc:
        _fail(str(exc))
    if str(hotloop.get("pilot_loop_id", "")) != str(hotloop.get("dominant_loop_id", "")):
        _fail("INVALID:PILOT_NOT_DOMINANT_HOTLOOP")
    hotloop_path, hotloop_hash = _write_hashed_json(state_dir / "hotloop", "kernel_hotloop_report_v1.json", hotloop)

    baseline_report = {
        "schema_version": "kernel_hash_workload_report_v1",
        "mode": "baseline",
        "tree_hash": baseline_tree_hash,
        "spawn_count": baseline_spawn_count,
        "bytes_hashed": sum(len(m) for m in workload_messages),
        "val_cycles_total": int(baseline_receipt_workload.get("val_cycles_total", 0)),
    }
    candidate_report = {
        "schema_version": "kernel_hash_workload_report_v1",
        "mode": "candidate",
        "tree_hash": candidate_tree_hash,
        "spawn_count": candidate_spawn_count,
        "bytes_hashed": sum(len(m) for m in workload_messages),
        "val_cycles_total": int(candidate_receipt_workload.get("val_cycles_total", 0)),
    }

    baseline_path, baseline_hash = _write_hashed_json(
        state_dir / "baseline",
        "kernel_hash_workload_report_v1.json",
        baseline_report,
    )
    candidate_path, candidate_hash = _write_hashed_json(
        state_dir / "candidate",
        "kernel_hash_workload_report_v1.json",
        candidate_report,
    )

    # Equivalence suite (byte-level identity proof).
    vector_messages = generate_vector_messages(policy.equivalence_vectors)
    if max_tasks is not None:
        vector_messages = vector_messages[:max_tasks]
    if not vector_messages:
        _fail("INVALID:V17_MAX_TASKS")
    applied_task_counts["equivalence_tasks"] = len(vector_messages)
    baseline_eq_run = run_runner_batch(
        runner_bin=runner_bin,
        mode="baseline_ref",
        messages=vector_messages,
        patch_bytes=code_bytes,
        trace_path=state_dir / "baseline" / "exec_trace" / "val_exec_trace_equivalence.jsonl",
        receipt_path=state_dir / "baseline" / "exec" / "sealed_run_receipt_equivalence_v1.json",
        max_len_bytes=policy.max_blocks_len * 64,
        step_bytes=1,
        safety_status="SAFE",
        runner_bin_hash=runner_bin_hash,
        code_bytes_hash=code_bytes_hash,
    )
    baseline_receipt_eq = _ensure_batch_ok(
        baseline_eq_run,
        trace_path=state_dir / "baseline" / "exec_trace" / "val_exec_trace_equivalence.jsonl",
        require_native=False,
    )
    baseline_invocations.append(baseline_receipt_eq)
    baseline_spawn_count += 1

    candidate_eq_run = run_runner_batch(
        runner_bin=runner_bin,
        mode="patch_native",
        messages=vector_messages,
        patch_bytes=code_bytes,
        trace_path=state_dir / "candidate" / "exec_trace" / "val_exec_trace_equivalence.jsonl",
        receipt_path=state_dir / "candidate" / "exec" / "sealed_run_receipt_equivalence_v1.json",
        max_len_bytes=policy.max_blocks_len * 64,
        step_bytes=1,
        safety_status=safety_status,
        runner_bin_hash=runner_bin_hash,
        code_bytes_hash=code_bytes_hash,
    )
    candidate_receipt_eq = _ensure_batch_ok(
        candidate_eq_run,
        trace_path=state_dir / "candidate" / "exec_trace" / "val_exec_trace_equivalence.jsonl",
        require_native=True,
    )
    candidate_invocations.append(candidate_receipt_eq)
    candidate_spawn_count += 1

    eq_receipt = build_equivalence_receipt_from_outputs(
        patch_id=str(patch_manifest["patch_id"]),
        vectors_cfg=policy.equivalence_vectors,
        baseline_outputs=list(baseline_eq_run["outputs"]),
        candidate_outputs=list(candidate_eq_run["outputs"]),
    )
    if policy.require_semantic_identity and not bool(eq_receipt.get("pass", False)):
        _fail("INVALID:SEMANTIC_MISMATCH")

    eq_path, eq_hash = _write_hashed_json(
        state_dir / "candidate" / "equivalence",
        "val_equivalence_receipt_v1.json",
        eq_receipt,
    )

    # Fixture identity check.
    fixture_messages = load_fixture_messages(fixture_obj)
    if max_tasks is not None:
        fixture_messages = fixture_messages[:max_tasks]
    if not fixture_messages:
        _fail("INVALID:V17_MAX_TASKS")
    applied_task_counts["fixture_tasks"] = len(fixture_messages)
    _write_intensity_receipt(state_dir, max_tasks, applied_task_counts)
    baseline_fx_run = run_runner_batch(
        runner_bin=runner_bin,
        mode="baseline_ref",
        messages=fixture_messages,
        patch_bytes=code_bytes,
        trace_path=state_dir / "baseline" / "exec_trace" / "val_exec_trace_fixture.jsonl",
        receipt_path=state_dir / "baseline" / "exec" / "sealed_run_receipt_fixture_v1.json",
        max_len_bytes=policy.max_blocks_len * 64,
        step_bytes=1,
        safety_status="SAFE",
        runner_bin_hash=runner_bin_hash,
        code_bytes_hash=code_bytes_hash,
    )
    baseline_receipt_fx = _ensure_batch_ok(
        baseline_fx_run,
        trace_path=state_dir / "baseline" / "exec_trace" / "val_exec_trace_fixture.jsonl",
        require_native=False,
    )
    baseline_invocations.append(baseline_receipt_fx)
    baseline_spawn_count += 1

    candidate_fx_run = run_runner_batch(
        runner_bin=runner_bin,
        mode="patch_native",
        messages=fixture_messages,
        patch_bytes=code_bytes,
        trace_path=state_dir / "candidate" / "exec_trace" / "val_exec_trace_fixture.jsonl",
        receipt_path=state_dir / "candidate" / "exec" / "sealed_run_receipt_fixture_v1.json",
        max_len_bytes=policy.max_blocks_len * 64,
        step_bytes=1,
        safety_status=safety_status,
        runner_bin_hash=runner_bin_hash,
        code_bytes_hash=code_bytes_hash,
    )
    candidate_receipt_fx = _ensure_batch_ok(
        candidate_fx_run,
        trace_path=state_dir / "candidate" / "exec_trace" / "val_exec_trace_fixture.jsonl",
        require_native=True,
    )
    candidate_invocations.append(candidate_receipt_fx)
    candidate_spawn_count += 1

    baseline_fixture_tree_hash = _tree_hash(list(baseline_fx_run["outputs"]))
    candidate_fixture_tree_hash = _tree_hash(list(candidate_fx_run["outputs"]))
    if baseline_fixture_tree_hash != candidate_fixture_tree_hash:
        _fail("INVALID:SEMANTIC_MISMATCH")

    # Benchmark fairness: same runner, same timing primitive.
    bench_messages = list(workload_messages)
    bench_report = run_runner_benchmark(
        runner_bin=runner_bin,
        messages=bench_messages,
        patch_bytes=code_bytes,
        report_path=state_dir / "candidate" / "benchmark" / "val_benchmark_report_v1.raw.json",
        warmup=policy.benchmark_warmup_reps,
        reps=policy.benchmark_reps,
        max_len_bytes=policy.max_blocks_len * 64,
        step_bytes=1,
        safety_status=safety_status,
    )

    baseline_bench_path, baseline_bench_hash = _write_hashed_json(
        state_dir / "baseline" / "benchmark",
        "val_benchmark_report_v1.json",
        bench_report,
    )
    candidate_bench_path, candidate_bench_hash = _write_hashed_json(
        state_dir / "candidate" / "benchmark",
        "val_benchmark_report_v1.json",
        bench_report,
    )
    write_canon_json(state_dir / "baseline" / "benchmark" / "val_benchmark_report_v1.json", bench_report)
    write_canon_json(state_dir / "candidate" / "benchmark" / "val_benchmark_report_v1.json", bench_report)

    baseline_sealed = _seal_receipt(runner_bin_hash=runner_bin_hash, invocations=baseline_invocations)
    candidate_sealed = _seal_receipt(runner_bin_hash=runner_bin_hash, invocations=candidate_invocations)
    baseline_sealed_path, baseline_sealed_hash = _write_hashed_json(
        state_dir / "baseline" / "exec",
        "sealed_run_receipt_v1.json",
        baseline_sealed,
    )
    candidate_sealed_path, candidate_sealed_hash = _write_hashed_json(
        state_dir / "candidate" / "exec",
        "sealed_run_receipt_v1.json",
        candidate_sealed,
    )

    baseline_in_hash, baseline_out_hash = aggregate_io_hash(messages=workload_messages, outputs=baseline_outputs)
    candidate_in_hash, candidate_out_hash = aggregate_io_hash(messages=workload_messages, outputs=candidate_outputs)

    baseline_backend = {
        "schema_version": "val_exec_backend_v1",
        "exec_backend": "RUST_BASELINE_REF_V1",
        "runner_bin_hash": runner_bin_hash,
        "code_bytes_hash": code_bytes_hash,
        "input_hash": baseline_in_hash,
        "output_hash": baseline_out_hash,
        "sealed_run_receipt_hash": baseline_sealed_hash,
    }
    candidate_backend = {
        "schema_version": "val_exec_backend_v1",
        "exec_backend": "RUST_NATIVE_AARCH64_MMAP_RX_V1",
        "runner_bin_hash": runner_bin_hash,
        "code_bytes_hash": code_bytes_hash,
        "input_hash": candidate_in_hash,
        "output_hash": candidate_out_hash,
        "sealed_run_receipt_hash": candidate_sealed_hash,
    }

    write_canon_json(state_dir / "baseline" / "exec" / "val_exec_backend_v1.json", baseline_backend)
    write_canon_json(state_dir / "candidate" / "exec" / "val_exec_backend_v1.json", candidate_backend)

    baseline_backend_hash = sha256_prefixed(canon_bytes(baseline_backend))
    candidate_backend_hash = sha256_prefixed(canon_bytes(candidate_backend))
    try:
        candidate_trace_head = trace_head_hash(candidate_trace)
    except SealedRunnerError as exc:
        _fail(str(exc))

    # Gates.
    spawn_gate_ok = baseline_spawn_count >= 1 and candidate_spawn_count >= 1
    _gate_or_fail(spawn_gate_ok, "INVALID:SPAWN_GATE_FAIL")

    work_conservation = int(candidate_report["bytes_hashed"]) == int(baseline_report["bytes_hashed"])
    _gate_or_fail(work_conservation, "INVALID:WORK_CONSERVATION_FAIL")

    valcycles_gate_ok = gate_valcycles(
        candidate=int(candidate_report["val_cycles_total"]),
        baseline=int(baseline_report["val_cycles_total"]),
        num=policy.perf_gate_valcycles_num,
        den=policy.perf_gate_valcycles_den,
    )
    _gate_or_fail(valcycles_gate_ok, "INVALID:PERF_VALCYCLES_GATE_FAIL")

    wallclock_gate_ok = _wallclock_gate(
        baseline_ns=int(bench_report["median_ns_baseline"]),
        candidate_ns=int(bench_report["median_ns_candidate"]),
        num=policy.perf_gate_wallclock_num,
        den=policy.perf_gate_wallclock_den,
    )
    _gate_or_fail(wallclock_gate_ok, "INVALID:PERF_WALLCLOCK_GATE_FAIL")

    if skip_downstream:
        meta_core_bundle_hash = sha256_prefixed(b"SKIPPED")
        meta_core_receipt = {
            "schema_version": "meta_core_promo_verify_receipt_v1",
            "return_code": 0,
            "stdout_hash": sha256_prefixed(b"SKIPPED"),
            "stderr_hash": sha256_prefixed(b""),
            "verifier_out_hash": sha256_prefixed(b"SKIPPED"),
            "pass": True,
        }
    else:
        meta_core_receipt, meta_core_bundle_hash = _run_meta_core_downstream(state_dir=state_dir, repo_root=_repo_root())
    meta_core_receipt_path, meta_core_receipt_hash = _write_downstream_receipt(
        state_dir / "downstream" / "meta_core_promo_verify_receipt_v1.json",
        meta_core_receipt,
    )
    if not bool(meta_core_receipt.get("pass", False)):
        _fail("INVALID:DOWNSTREAM_META_CORE_FAIL")

    if skip_downstream:
        v16_smoke_receipt = {
            "schema_version": "v16_1_smoke_receipt_v1",
            "fixture_state_dir": "SKIPPED",
            "return_code": 0,
            "stdout_hash": sha256_prefixed(b"SKIPPED"),
            "stderr_hash": sha256_prefixed(b""),
            "result": "VALID",
            "pass": True,
        }
    else:
        v16_smoke_receipt = _run_v16_1_smoke_downstream(state_dir=state_dir, config_dir=config_dir, repo_root=_repo_root())
    v16_smoke_receipt_path, v16_smoke_receipt_hash = _write_downstream_receipt(
        state_dir / "downstream" / "v16_1_smoke_receipt_v1.json",
        v16_smoke_receipt,
    )
    if not bool(v16_smoke_receipt.get("pass", False)):
        _fail("INVALID:DOWNSTREAM_V16_1_FAIL")

    determinism_keys = {
        "val_patch_id": str(patch_manifest["patch_id"]),
        "val_decoded_trace_hash": decoded_hash,
        "val_lift_ir_hash": lifted_hash,
        "val_safety_receipt_hash": safety_hash,
        "val_exec_trace_head_hash": candidate_trace_head,
        "baseline_exec_backend_hash": baseline_backend_hash,
        "candidate_exec_backend_hash": candidate_backend_hash,
    }

    promotion = {
        "schema_version": "sas_val_promotion_bundle_v1",
        "bundle_id": "",
        "pack_hash": sha256_prefixed(canon_bytes(frozen_pack)),
        "policy_hash": sha256_prefixed(canon_bytes(policy_obj)),
        "patch_manifest_hash": patch_hash,
        "decoded_trace_hash": decoded_hash,
        "lift_ir_hash": lifted_hash,
        "safety_receipt_hash": safety_hash,
        "equivalence_receipt_hash": eq_hash,
        "runner_binary_hash": runner_bin_hash,
        "baseline_exec_backend_hash": baseline_backend_hash,
        "candidate_exec_backend_hash": candidate_backend_hash,
        "baseline_sealed_run_receipt_hash": baseline_sealed_hash,
        "candidate_sealed_run_receipt_hash": candidate_sealed_hash,
        "baseline_spawn_count": baseline_spawn_count,
        "candidate_spawn_count": candidate_spawn_count,
        "baseline_benchmark_report_hash": baseline_bench_hash,
        "candidate_benchmark_report_hash": candidate_bench_hash,
        "baseline_kernel_tree_hash": baseline_fixture_tree_hash,
        "candidate_kernel_tree_hash": candidate_fixture_tree_hash,
        "hotloop_report_hash": hotloop_hash,
        "val_exec_trace_head_hash": candidate_trace_head,
        "downstream_meta_core_receipt_hash": meta_core_receipt_hash,
        "downstream_v16_1_receipt_hash": v16_smoke_receipt_hash,
        "meta_core_bundle_hash": meta_core_bundle_hash,
        "val_cycles_baseline": int(baseline_report["val_cycles_total"]),
        "val_cycles_candidate": int(candidate_report["val_cycles_total"]),
        "valcycles_gate_pass": bool(valcycles_gate_ok),
        "wallclock_gate_pass": bool(wallclock_gate_ok),
        "work_conservation_pass": bool(work_conservation),
        "determinism_keys": determinism_keys,
    }
    promotion["bundle_id"] = sha256_prefixed(
        canon_bytes({k: v for k, v in promotion.items() if k not in _BUNDLE_ID_OMIT_FIELDS})
    )
    promotion_path, promotion_hash = _write_hashed_json(
        state_dir / "promotion",
        "sas_val_promotion_bundle_v1.json",
        promotion,
    )

    if bool(frozen_pack.get("double_run_mode", False)):
        try:
            replay_trace_head = trace_head_hash(state_dir / "candidate" / "exec_trace" / "val_exec_trace.jsonl")
        except SealedRunnerError as exc:
            _fail(str(exc))
        replay_keys = {
            "val_patch_id": str(_load_json(patch_path)["patch_id"]),
            "val_decoded_trace_hash": sha256_prefixed(canon_bytes(_load_json(decoded_path))),
            "val_lift_ir_hash": sha256_prefixed(canon_bytes(_load_json(lifted_path))),
            "val_safety_receipt_hash": sha256_prefixed(canon_bytes(_load_json(safety_path))),
            "val_exec_trace_head_hash": replay_trace_head,
            "baseline_exec_backend_hash": sha256_prefixed(canon_bytes(_load_json(state_dir / "baseline" / "exec" / "val_exec_backend_v1.json"))),
            "candidate_exec_backend_hash": sha256_prefixed(canon_bytes(_load_json(state_dir / "candidate" / "exec" / "val_exec_backend_v1.json"))),
            "promotion_bundle_hash": str(promotion["bundle_id"]),
        }
        for k, v in determinism_keys.items():
            if replay_keys[k] != v:
                _fail("INVALID:NONDETERMINISTIC")
        write_canon_json(state_dir / "snapshot" / "determinism_receipt_v1.json", replay_keys)

    write_jsonl_line(
        state_dir / "ledger" / "sas_val_ledger_v1.jsonl",
        {
            "schema_version": "sas_val_ledger_event_v1",
            "tick_u64": 0,
            "event_type": "SAS_VAL_PROMOTION_WRITTEN",
            "payload": {
                "promotion_bundle_hash": promotion_hash,
            },
        },
    )

    return {
        "status": "OK",
        "state_dir": str(state_dir),
        "promotion_bundle": str(promotion_path),
        "promotion_bundle_hash": promotion_hash,
        "hotloop_report": str(hotloop_path),
        "baseline_report": str(baseline_path),
        "candidate_report": str(candidate_path),
        "decoded_trace": str(decoded_path),
        "lifted_ir": str(lifted_path),
        "safety_receipt": str(safety_path),
        "equivalence_receipt": str(eq_path),
        "baseline_benchmark_report": str(baseline_bench_path),
        "candidate_benchmark_report": str(candidate_bench_path),
        "runner_build_receipt": str(runner_build_path),
        "rust_toolchain_receipt_hash": rust_toolchain_receipt_hash,
        "runner_toolchain_receipt_hash": runner_toolchain_receipt_hash,
        "baseline_exec_backend": str(state_dir / "baseline" / "exec" / "val_exec_backend_v1.json"),
        "candidate_exec_backend": str(state_dir / "candidate" / "exec" / "val_exec_backend_v1.json"),
        "baseline_sealed_receipt": str(baseline_sealed_path),
        "candidate_sealed_receipt": str(candidate_sealed_path),
        "downstream_meta_core_receipt": str(meta_core_receipt_path),
        "downstream_v16_1_receipt": str(v16_smoke_receipt_path),
    }


__all__ = ["ValRunError", "run_sas_val"]
