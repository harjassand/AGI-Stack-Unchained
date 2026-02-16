"""Fail-closed verifier for RSI SAS VAL v17.0."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import warnings
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from .hotloop.hotloop_counter_v1 import generate_workload_messages, load_fixture_messages
from .runtime.val_patch_store_v1 import decode_code_bytes, validate_patch_manifest
from .runtime.val_runner_sealed_v1 import (
    SealedRunnerError,
    aggregate_io_hash,
    ensure_trace_complete,
    run_runner_batch,
    trace_head_hash,
)
from .runtime.sas_val_run_v1 import run_sas_val as run_v17_campaign
from .val.val_cost_model_v1 import gate_valcycles
from .val.val_decode_aarch64_v1 import ValDecodeError, decode_trace_py, decode_trace_rs, decoded_trace_hash
from .val.val_equivalence_v1 import ValEquivalenceError, build_equivalence_receipt_from_outputs, generate_vector_messages
from .val.val_isa_v1 import ValPolicyError, parse_policy
from .val.val_lift_ir_v1 import ValLiftError, lift_ir_hash, lift_ir_py, lift_ir_rs
from .val.val_verify_safety_v1 import verify_safety, verify_safety_shadow

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


class SASValVerifyError(CanonError):
    pass


SCHEMA_STORE_CACHE: dict[str, dict[str, Any]] = {}
VALIDATOR_CACHE: dict[tuple[str, str], Any] = {}


def _fail(reason: str) -> None:
    raise SASValVerifyError(reason)


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
    return Path(__file__).resolve().parents[3]


def _schema_dir() -> Path:
    return _repo_root() / "Genesis" / "schema" / "v17_0"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        obj = load_canon_json(path)
    except CanonError:
        _fail("INVALID:SCHEMA_FAIL")
    if not isinstance(obj, dict):
        _fail("INVALID:SCHEMA_FAIL")
    return obj


def _validate_jsonschema(obj: dict[str, Any], schema_name: str, schema_dir: Path) -> None:
    if Draft202012Validator is None:
        return

    schema_root = schema_dir.resolve()
    schema_root_key = schema_root.as_posix()
    schema_path = schema_dir / f"{schema_name}.jsonschema"
    if not schema_path.exists():
        _fail("INVALID:SCHEMA_FAIL")

    store = SCHEMA_STORE_CACHE.get(schema_root_key)
    if store is None:
        store = {}
        for path in schema_root.glob("*.jsonschema"):
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
        SCHEMA_STORE_CACHE[schema_root_key] = store

    validator_key = (schema_root_key, schema_name)
    validator = VALIDATOR_CACHE.get(validator_key)
    if validator is None:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema = dict(schema)
        schema["$id"] = schema_path.resolve().as_uri()
        if RefResolver is not None:
            resolver = RefResolver.from_schema(schema, store=store)
            validator = Draft202012Validator(schema, resolver=resolver)
        else:
            validator = Draft202012Validator(schema)
        VALIDATOR_CACHE[validator_key] = validator

    validator.validate(obj)


def _resolve_state(path: Path) -> tuple[Path, Path]:
    root = path.resolve()
    candidate = root / "daemon" / "rsi_sas_val_v17_0" / "state"
    if candidate.exists():
        return candidate, candidate.parent
    candidate = root / "state"
    if candidate.exists() and (root / "config").exists():
        return candidate, root
    if (root / "inputs").exists() and (root.parent / "config").exists():
        return root, root.parent
    _fail("INVALID:SCHEMA_FAIL")
    return root, root


def _collect_single(path: Path, pattern: str) -> Path:
    rows = sorted(path.glob(pattern))
    if len(rows) != 1:
        _fail("INVALID:SCHEMA_FAIL")
    return rows[0]


def _collect_by_hash(path: Path, suffix: str, h: str) -> Path:
    if not isinstance(h, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", h):
        _fail("INVALID:SCHEMA_FAIL")
    target = path / f"sha256_{h.split(':',1)[1]}.{suffix}"
    if not target.exists() or not target.is_file():
        _fail("INVALID:MISSING_STATE_INPUT")
    return target


def _canon_hash(path: Path) -> str:
    obj = _load_json(path)
    return sha256_prefixed(canon_bytes(obj))


def _wallclock_gate(*, baseline_ns: int, candidate_ns: int, num: int, den: int) -> bool:
    if baseline_ns <= 0 or candidate_ns < 0 or num <= 0 or den <= 0:
        return False
    return candidate_ns * den <= baseline_ns * num


def _parse_v17_max_tasks() -> int | None:
    raw = str(os.environ.get("V17_MAX_TASKS", "")).strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except Exception:  # noqa: BLE001
        _fail("INVALID:V17_MAX_TASKS")
    if parsed < 1 or parsed > 100000:
        _fail("INVALID:V17_MAX_TASKS")
    return parsed


def _tree_hash(outputs: list[bytes]) -> str:
    return sha256_prefixed(
        canon_bytes(
            {
                "schema_version": "val_output_tree_v1",
                "output_hashes": [sha256_prefixed(x) for x in outputs],
            }
        )
    )


def _neon_stats(decoded_trace: dict[str, Any]) -> tuple[int, int]:
    neon_insn_count = 0
    neon_loadstore_count = 0
    for row in decoded_trace.get("instructions", []):
        mnemonic = str(row.get("mnemonic", "")).lower()
        ops = " ".join(str(x).lower() for x in row.get("operands_norm", []))
        has_vec_reg = bool(re.search(r"\b[vsq][0-9]+\b", ops))
        if mnemonic in {"ld1", "st1"}:
            neon_loadstore_count += 1
            neon_insn_count += 1
            continue
        if mnemonic.startswith("sha256") or (mnemonic in {"eor", "and", "orr", "add", "sub"} and has_vec_reg) or has_vec_reg:
            neon_insn_count += 1
    return neon_insn_count, neon_loadstore_count


def _extract_determinism_keys_from_state(state_dir: Path) -> dict[str, str]:
    promotion_path = _collect_single(state_dir / "promotion", "sha256_*.sas_val_promotion_bundle_v1.json")
    promotion = _load_json(promotion_path)
    patch_manifest = _load_json(
        _collect_by_hash(
            state_dir / "candidate" / "patch",
            "val_patch_manifest_v1.json",
            str(promotion.get("patch_manifest_hash", "")),
        )
    )
    try:
        trace_head = trace_head_hash(state_dir / "candidate" / "exec_trace" / "val_exec_trace.jsonl")
    except SealedRunnerError:
        _fail("INVALID:NONDETERMINISTIC")
        return {}
    return {
        "val_patch_id": str(patch_manifest.get("patch_id", "")),
        "val_lift_ir_hash": str(promotion.get("lift_ir_hash", "")),
        "val_safety_receipt_hash": str(promotion.get("safety_receipt_hash", "")),
        "val_exec_trace_head_hash": trace_head,
        "promotion_bundle_hash": str(promotion.get("bundle_id", "")),
    }


def _run_determinism_replay(*, config_dir: Path) -> dict[str, str]:
    pack_path = config_dir / "rsi_sas_val_pack_v17_0.json"
    if not pack_path.exists():
        _fail("INVALID:NONDETERMINISTIC")
    try:
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            out_a = Path(tmp_a) / "run_a"
            out_b = Path(tmp_b) / "run_b"
            run_v17_campaign(campaign_pack=pack_path, out_dir=out_a, campaign_tag="rsi_sas_val_v17_0", skip_downstream=True)
            run_v17_campaign(campaign_pack=pack_path, out_dir=out_b, campaign_tag="rsi_sas_val_v17_0", skip_downstream=True)
            state_a, _ = _resolve_state(out_a)
            state_b, _ = _resolve_state(out_b)
            keys_a = _extract_determinism_keys_from_state(state_a)
            keys_b = _extract_determinism_keys_from_state(state_b)
    except Exception:  # noqa: BLE001
        _fail("INVALID:NONDETERMINISTIC")
        return {}
    if keys_a != keys_b:
        _fail("INVALID:NONDETERMINISTIC")
    return keys_a


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        _fail("INVALID:MODE_UNSUPPORTED")

    state_dir, daemon_root = _resolve_state(state_dir)
    config_dir = daemon_root / "config"
    schema_dir = _schema_dir()

    pack = _load_json(config_dir / "rsi_sas_val_pack_v17_0.json")
    policy_obj = _load_json(config_dir / "sas_val_policy_v1.json")
    workload_obj = _load_json(config_dir / "workload" / "kernel_workload_suitepack_v1.json")
    fixture_obj = _load_json(config_dir / "fixtures" / "brain_suitepack_dev_v15_1.json")

    _validate_jsonschema(pack, "rsi_sas_val_pack_v17_0", schema_dir)
    _validate_jsonschema(policy_obj, "sas_val_policy_v1", schema_dir)

    try:
        policy = parse_policy(policy_obj)
    except ValPolicyError as exc:
        _fail(str(exc))
    max_tasks = _parse_v17_max_tasks()

    promo_path = _collect_single(state_dir / "promotion", "sha256_*.sas_val_promotion_bundle_v1.json")
    promotion = _load_json(promo_path)
    _validate_jsonschema(promotion, "sas_val_promotion_bundle_v1", schema_dir)

    expected_bundle_id = sha256_prefixed(
        canon_bytes({k: v for k, v in promotion.items() if k not in _BUNDLE_ID_OMIT_FIELDS})
    )
    if str(promotion.get("bundle_id", "")) != expected_bundle_id:
        _fail("INVALID:SCHEMA_FAIL")

    if _canon_hash(config_dir / "rsi_sas_val_pack_v17_0.json") != str(promotion.get("pack_hash", "")):
        _fail("INVALID:SCHEMA_FAIL")
    if _canon_hash(config_dir / "sas_val_policy_v1.json") != str(promotion.get("policy_hash", "")):
        _fail("INVALID:SCHEMA_FAIL")

    hotloop = _load_json(
        _collect_by_hash(
            state_dir / "hotloop",
            "kernel_hotloop_report_v1.json",
            str(promotion.get("hotloop_report_hash", "")),
        )
    )
    _validate_jsonschema(hotloop, "kernel_hotloop_report_v1", schema_dir)
    top_loops = hotloop.get("top_loops")
    if not isinstance(top_loops, list) or len(top_loops) < 10 or int(hotloop.get("top_n", 0)) < 10:
        _fail("INVALID:PILOT_NOT_DOMINANT_HOTLOOP")
    if str(hotloop.get("pilot_loop_id", "")) != str(hotloop.get("dominant_loop_id", "")):
        _fail("INVALID:PILOT_NOT_DOMINANT_HOTLOOP")

    patch_path = _collect_by_hash(
        state_dir / "candidate" / "patch",
        "val_patch_manifest_v1.json",
        str(promotion.get("patch_manifest_hash", "")),
    )
    patch_manifest = _load_json(patch_path)
    _validate_jsonschema(patch_manifest, "val_patch_manifest_v1", schema_dir)
    try:
        validate_patch_manifest(patch_manifest, max_code_bytes=policy.max_code_bytes)
    except Exception:
        _fail("INVALID:SCHEMA_FAIL")

    code_bytes = decode_code_bytes(patch_manifest)
    code_bytes_hash = sha256_prefixed(code_bytes)

    try:
        decoded_py = decode_trace_py(code_bytes)
        decoded_rs = decode_trace_rs(code_bytes)
    except ValDecodeError as exc:
        _fail(str(exc))

    decoded_hash_py = decoded_trace_hash(decoded_py)
    decoded_hash_rs = decoded_trace_hash(decoded_rs)
    if policy.require_dual_decoder_parity and decoded_hash_py != decoded_hash_rs:
        _fail("INVALID:VAL_DUAL_DECODER_DIVERGENCE")
    if decoded_hash_py != str(promotion.get("decoded_trace_hash", "")):
        _fail("INVALID:NONREPLAYABLE")

    decoded_state = _load_json(
        _collect_by_hash(
            state_dir / "candidate" / "trace",
            "val_decoded_trace_v1.json",
            str(promotion.get("decoded_trace_hash", "")),
        )
    )
    _validate_jsonschema(decoded_state, "val_decoded_trace_v1", schema_dir)
    if decoded_state != decoded_py:
        _fail("INVALID:NONREPLAYABLE")
    neon_insn_count, neon_loadstore_count = _neon_stats(decoded_state)
    if neon_insn_count < 1 or neon_loadstore_count < 1:
        _fail("INVALID:NOT_SIMD_NEON")

    try:
        lifted_py = lift_ir_py(decoded_py)
        lifted_rs = lift_ir_rs(decoded_py)
    except ValLiftError as exc:
        _fail(str(exc))
    lift_hash_py = lift_ir_hash(lifted_py)
    lift_hash_rs = lift_ir_hash(lifted_rs)
    if policy.require_dual_lifter_parity and lift_hash_py != lift_hash_rs:
        _fail("INVALID:VAL_DUAL_LIFTER_DIVERGENCE")
    if lift_hash_py != str(promotion.get("lift_ir_hash", "")):
        _fail("INVALID:NONREPLAYABLE")

    lifted_state = _load_json(
        _collect_by_hash(
            state_dir / "candidate" / "ir",
            "val_lift_ir_v1.json",
            str(promotion.get("lift_ir_hash", "")),
        )
    )
    _validate_jsonschema(lifted_state, "val_lift_ir_v1", schema_dir)
    if lifted_state != lifted_py:
        _fail("INVALID:NONREPLAYABLE")

    safety = verify_safety(
        decoded_trace=decoded_py,
        lifted_ir=lifted_py,
        patch_manifest=patch_manifest,
        policy=policy,
    )
    shadow = verify_safety_shadow(
        decoded_trace=decoded_py,
        lifted_ir=lifted_py,
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

    safety_hash = sha256_prefixed(canon_bytes(safety))
    if safety_hash != str(promotion.get("safety_receipt_hash", "")):
        _fail("INVALID:NONREPLAYABLE")

    safety_state = _load_json(
        _collect_by_hash(
            state_dir / "candidate" / "safety",
            "val_safety_receipt_v1.json",
            str(promotion.get("safety_receipt_hash", "")),
        )
    )
    _validate_jsonschema(safety_state, "val_safety_receipt_v1", schema_dir)
    if safety_state != safety:
        _fail("INVALID:NONREPLAYABLE")

    safety_status = str(safety.get("status", "UNSAFE"))
    if safety_status != "SAFE":
        if (state_dir / "candidate" / "exec" / "val_exec_backend_v1.json").exists():
            _fail("INVALID:EXEC_BEFORE_SAFE")
        _fail("INVALID:EXEC_BEFORE_SAFE")

    baseline_backend_path = state_dir / "baseline" / "exec" / "val_exec_backend_v1.json"
    candidate_backend_path = state_dir / "candidate" / "exec" / "val_exec_backend_v1.json"
    if not baseline_backend_path.exists() or not candidate_backend_path.exists():
        _fail("INVALID:SEALED_RUN_RECEIPT_MISSING")

    baseline_backend = _load_json(baseline_backend_path)
    candidate_backend = _load_json(candidate_backend_path)
    _validate_jsonschema(baseline_backend, "val_exec_backend_v1", schema_dir)
    _validate_jsonschema(candidate_backend, "val_exec_backend_v1", schema_dir)

    if str(candidate_backend.get("exec_backend", "")) != "RUST_NATIVE_AARCH64_MMAP_RX_V1":
        _fail("INVALID:EXEC_BACKEND_NOT_NATIVE")
    if sha256_prefixed(canon_bytes(baseline_backend)) != str(promotion.get("baseline_exec_backend_hash", "")):
        _fail("INVALID:NONREPLAYABLE")
    if sha256_prefixed(canon_bytes(candidate_backend)) != str(promotion.get("candidate_exec_backend_hash", "")):
        _fail("INVALID:NONREPLAYABLE")

    runner_hash = str(promotion.get("runner_binary_hash", ""))
    if str(candidate_backend.get("runner_bin_hash", "")) != runner_hash:
        _fail("INVALID:SEALED_RUN_RECEIPT_MISSING")

    baseline_sealed = _load_json(
        _collect_by_hash(
            state_dir / "baseline" / "exec",
            "sealed_run_receipt_v1.json",
            str(promotion.get("baseline_sealed_run_receipt_hash", "")),
        )
    )
    candidate_sealed = _load_json(
        _collect_by_hash(
            state_dir / "candidate" / "exec",
            "sealed_run_receipt_v1.json",
            str(promotion.get("candidate_sealed_run_receipt_hash", "")),
        )
    )

    if int(baseline_sealed.get("spawn_count", 0)) < 1 or int(candidate_sealed.get("spawn_count", 0)) < 1:
        _fail("INVALID:SEALED_RUN_RECEIPT_MISSING")
    if str(baseline_sealed.get("runner_bin_hash", "")) != runner_hash:
        _fail("INVALID:SEALED_RUN_RECEIPT_MISSING")
    if str(candidate_sealed.get("runner_bin_hash", "")) != runner_hash:
        _fail("INVALID:SEALED_RUN_RECEIPT_MISSING")

    if int(promotion.get("baseline_spawn_count", 0)) < 1 or int(promotion.get("candidate_spawn_count", 0)) < 1:
        _fail("INVALID:SEALED_RUN_RECEIPT_MISSING")

    candidate_trace = state_dir / "candidate" / "exec_trace" / "val_exec_trace.jsonl"
    try:
        ensure_trace_complete(candidate_trace)
    except SealedRunnerError:
        _fail("INVALID:EXEC_TRACE_INCOMPLETE")
    for raw in candidate_trace.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        row = json.loads(raw)
        if not isinstance(row, dict):
            _fail("INVALID:EXEC_TRACE_INCOMPLETE")
        _validate_jsonschema(row, "val_exec_trace_v1", schema_dir)
    try:
        replay_trace_head = trace_head_hash(candidate_trace)
    except SealedRunnerError:
        _fail("INVALID:EXEC_TRACE_INCOMPLETE")
    if replay_trace_head != str(promotion.get("val_exec_trace_head_hash", "")):
        _fail("INVALID:NONREPLAYABLE")

    # Replay workload through the same native runner.
    runner_bin = _repo_root() / "CDEL-v2" / "cdel" / "v17_0" / "rust" / "val_runner_rs_v1" / "target" / "release" / "val_runner_rs_v1"
    if not runner_bin.exists() or sha256_prefixed(runner_bin.read_bytes()) != runner_hash:
        _fail("INVALID:SEALED_RUN_RECEIPT_MISSING")

    workload_messages = generate_workload_messages(workload_obj)
    if max_tasks is not None:
        workload_messages = workload_messages[:max_tasks]
    if not workload_messages:
        _fail("INVALID:V17_MAX_TASKS")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            baseline_work = run_runner_batch(
                runner_bin=runner_bin,
                mode="baseline_ref",
                messages=workload_messages,
                patch_bytes=code_bytes,
                trace_path=tmpdir / "verify_baseline_trace.jsonl",
                receipt_path=tmpdir / "verify_baseline_receipt.json",
                max_len_bytes=policy.max_blocks_len * 64,
                step_bytes=1,
                safety_status="SAFE",
                runner_bin_hash=runner_hash,
                code_bytes_hash=code_bytes_hash,
            )
            candidate_work = run_runner_batch(
                runner_bin=runner_bin,
                mode="patch_native",
                messages=workload_messages,
                patch_bytes=code_bytes,
                trace_path=tmpdir / "verify_candidate_trace.jsonl",
                receipt_path=tmpdir / "verify_candidate_receipt.json",
                max_len_bytes=policy.max_blocks_len * 64,
                step_bytes=1,
                safety_status="SAFE",
                runner_bin_hash=runner_hash,
                code_bytes_hash=code_bytes_hash,
            )
    except SealedRunnerError:
        _fail("INVALID:EXEC_TRACE_INCOMPLETE")

    if int(candidate_work.get("returncode", -1)) != 0:
        _fail("INVALID:EXEC_TRACE_INCOMPLETE")
    if int(baseline_work.get("returncode", -1)) != 0:
        _fail("INVALID:EXEC_TRACE_INCOMPLETE")

    baseline_outputs = list(baseline_work.get("outputs", []))
    candidate_outputs = list(candidate_work.get("outputs", []))

    baseline_in_hash, baseline_out_hash = aggregate_io_hash(messages=workload_messages, outputs=baseline_outputs)
    candidate_in_hash, candidate_out_hash = aggregate_io_hash(messages=workload_messages, outputs=candidate_outputs)

    if str(baseline_backend.get("input_hash", "")) != baseline_in_hash:
        _fail("INVALID:NONREPLAYABLE")
    if str(candidate_backend.get("input_hash", "")) != candidate_in_hash:
        _fail("INVALID:NONREPLAYABLE")
    if str(baseline_backend.get("output_hash", "")) != baseline_out_hash:
        _fail("INVALID:NONREPLAYABLE")
    if str(candidate_backend.get("output_hash", "")) != candidate_out_hash:
        _fail("INVALID:NONREPLAYABLE")

    # Equivalence replay.
    try:
        vector_messages = generate_vector_messages(policy.equivalence_vectors)
    except ValEquivalenceError as exc:
        _fail(str(exc))
    if max_tasks is not None:
        vector_messages = vector_messages[:max_tasks]
    if not vector_messages:
        _fail("INVALID:V17_MAX_TASKS")

    with tempfile.TemporaryDirectory() as tmp_eq:
        tmpdir_eq = Path(tmp_eq)
        baseline_eq = run_runner_batch(
            runner_bin=runner_bin,
            mode="baseline_ref",
            messages=vector_messages,
            patch_bytes=code_bytes,
            trace_path=tmpdir_eq / "verify_eq_baseline_trace.jsonl",
            receipt_path=tmpdir_eq / "verify_eq_baseline_receipt.json",
            max_len_bytes=policy.max_blocks_len * 64,
            step_bytes=1,
            safety_status="SAFE",
            runner_bin_hash=runner_hash,
            code_bytes_hash=code_bytes_hash,
        )
        candidate_eq = run_runner_batch(
            runner_bin=runner_bin,
            mode="patch_native",
            messages=vector_messages,
            patch_bytes=code_bytes,
            trace_path=tmpdir_eq / "verify_eq_candidate_trace.jsonl",
            receipt_path=tmpdir_eq / "verify_eq_candidate_receipt.json",
            max_len_bytes=policy.max_blocks_len * 64,
            step_bytes=1,
            safety_status="SAFE",
            runner_bin_hash=runner_hash,
            code_bytes_hash=code_bytes_hash,
        )
    if int(candidate_eq.get("returncode", -1)) != 0:
        _fail("INVALID:EXEC_TRACE_INCOMPLETE")

    eq = build_equivalence_receipt_from_outputs(
        patch_id=str(patch_manifest["patch_id"]),
        vectors_cfg=policy.equivalence_vectors,
        baseline_outputs=list(baseline_eq.get("outputs", [])),
        candidate_outputs=list(candidate_eq.get("outputs", [])),
    )
    eq_hash = sha256_prefixed(canon_bytes(eq))
    if eq_hash != str(promotion.get("equivalence_receipt_hash", "")):
        _fail("INVALID:NONREPLAYABLE")
    if not bool(eq.get("pass", False)):
        _fail("INVALID:SEMANTIC_MISMATCH")

    # Fixture replay.
    fixture_messages = load_fixture_messages(fixture_obj)
    if max_tasks is not None:
        fixture_messages = fixture_messages[:max_tasks]
    if not fixture_messages:
        _fail("INVALID:V17_MAX_TASKS")
    with tempfile.TemporaryDirectory() as tmp_fx:
        tmpdir_fx = Path(tmp_fx)
        baseline_fx = run_runner_batch(
            runner_bin=runner_bin,
            mode="baseline_ref",
            messages=fixture_messages,
            patch_bytes=code_bytes,
            trace_path=tmpdir_fx / "verify_fx_baseline_trace.jsonl",
            receipt_path=tmpdir_fx / "verify_fx_baseline_receipt.json",
            max_len_bytes=policy.max_blocks_len * 64,
            step_bytes=1,
            safety_status="SAFE",
            runner_bin_hash=runner_hash,
            code_bytes_hash=code_bytes_hash,
        )
        candidate_fx = run_runner_batch(
            runner_bin=runner_bin,
            mode="patch_native",
            messages=fixture_messages,
            patch_bytes=code_bytes,
            trace_path=tmpdir_fx / "verify_fx_candidate_trace.jsonl",
            receipt_path=tmpdir_fx / "verify_fx_candidate_receipt.json",
            max_len_bytes=policy.max_blocks_len * 64,
            step_bytes=1,
            safety_status="SAFE",
            runner_bin_hash=runner_hash,
            code_bytes_hash=code_bytes_hash,
        )
    if int(candidate_fx.get("returncode", -1)) != 0:
        _fail("INVALID:EXEC_TRACE_INCOMPLETE")

    baseline_fixture_tree_hash = _tree_hash(list(baseline_fx.get("outputs", [])))
    candidate_fixture_tree_hash = _tree_hash(list(candidate_fx.get("outputs", [])))
    if baseline_fixture_tree_hash != candidate_fixture_tree_hash:
        _fail("INVALID:SEMANTIC_MISMATCH")
    if baseline_fixture_tree_hash != str(promotion.get("baseline_kernel_tree_hash", "")):
        _fail("INVALID:NONREPLAYABLE")
    if candidate_fixture_tree_hash != str(promotion.get("candidate_kernel_tree_hash", "")):
        _fail("INVALID:NONREPLAYABLE")

    # Performance and conservation gates from recorded reports.
    baseline_report = _load_json(_collect_single(state_dir / "baseline", "sha256_*.kernel_hash_workload_report_v1.json"))
    candidate_report = _load_json(_collect_single(state_dir / "candidate", "sha256_*.kernel_hash_workload_report_v1.json"))

    if int(baseline_report.get("spawn_count", 0)) < 1 or int(candidate_report.get("spawn_count", 0)) < 1:
        _fail("INVALID:SEALED_RUN_RECEIPT_MISSING")

    work_conservation = int(candidate_report.get("bytes_hashed", -1)) == int(baseline_report.get("bytes_hashed", -2))
    if not work_conservation:
        _fail("INVALID:WORK_CONSERVATION_FAIL")

    valcycles_gate_ok = gate_valcycles(
        candidate=int(candidate_report.get("val_cycles_total", -1)),
        baseline=int(baseline_report.get("val_cycles_total", -1)),
        num=policy.perf_gate_valcycles_num,
        den=policy.perf_gate_valcycles_den,
    )
    if not valcycles_gate_ok:
        _fail("INVALID:PERF_VALCYCLES_GATE_FAIL")

    baseline_bench = _load_json(
        _collect_by_hash(
            state_dir / "baseline" / "benchmark",
            "val_benchmark_report_v1.json",
            str(promotion.get("baseline_benchmark_report_hash", "")),
        )
    )
    bench = _load_json(
        _collect_by_hash(
            state_dir / "candidate" / "benchmark",
            "val_benchmark_report_v1.json",
            str(promotion.get("candidate_benchmark_report_hash", "")),
        )
    )
    _validate_jsonschema(baseline_bench, "val_benchmark_report_v1", schema_dir)
    _validate_jsonschema(bench, "val_benchmark_report_v1", schema_dir)
    if baseline_bench != bench:
        _fail("INVALID:NONREPLAYABLE")
    if len(list(bench.get("samples_ns_baseline", []))) != int(policy.benchmark_reps):
        _fail("INVALID:PERF_WALLCLOCK_GATE_FAIL")
    if len(list(bench.get("samples_ns_candidate", []))) != int(policy.benchmark_reps):
        _fail("INVALID:PERF_WALLCLOCK_GATE_FAIL")
    wallclock_gate_ok = _wallclock_gate(
        baseline_ns=int(bench.get("median_ns_baseline", -1)),
        candidate_ns=int(bench.get("median_ns_candidate", -1)),
        num=policy.perf_gate_wallclock_num,
        den=policy.perf_gate_wallclock_den,
    )
    if not wallclock_gate_ok:
        _fail("INVALID:PERF_WALLCLOCK_GATE_FAIL")

    meta_core_receipt = _load_json(state_dir / "downstream" / "meta_core_promo_verify_receipt_v1.json")
    v16_smoke_receipt = _load_json(state_dir / "downstream" / "v16_1_smoke_receipt_v1.json")
    _validate_jsonschema(meta_core_receipt, "meta_core_promo_verify_receipt_v1", schema_dir)
    _validate_jsonschema(v16_smoke_receipt, "v16_1_smoke_receipt_v1", schema_dir)
    if sha256_prefixed(canon_bytes(meta_core_receipt)) != str(promotion.get("downstream_meta_core_receipt_hash", "")):
        _fail("INVALID:NONREPLAYABLE")
    if sha256_prefixed(canon_bytes(v16_smoke_receipt)) != str(promotion.get("downstream_v16_1_receipt_hash", "")):
        _fail("INVALID:NONREPLAYABLE")
    if not bool(meta_core_receipt.get("pass", False)):
        _fail("INVALID:DOWNSTREAM_META_CORE_FAIL")
    if not bool(v16_smoke_receipt.get("pass", False)):
        _fail("INVALID:DOWNSTREAM_V16_1_FAIL")

    determinism_keys = promotion.get("determinism_keys")
    if not isinstance(determinism_keys, dict):
        _fail("INVALID:NONDETERMINISTIC")
    expected_keys = {
        "val_patch_id": str(patch_manifest["patch_id"]),
        "val_decoded_trace_hash": decoded_hash_py,
        "val_lift_ir_hash": lift_hash_py,
        "val_safety_receipt_hash": safety_hash,
        "val_exec_trace_head_hash": replay_trace_head,
        "baseline_exec_backend_hash": sha256_prefixed(canon_bytes(baseline_backend)),
        "candidate_exec_backend_hash": sha256_prefixed(canon_bytes(candidate_backend)),
    }
    for key, value in expected_keys.items():
        if determinism_keys.get(key) != value:
            _fail("INVALID:NONDETERMINISTIC")

    replay = _run_determinism_replay(config_dir=config_dir)
    for key in [
        "val_patch_id",
        "val_lift_ir_hash",
        "val_safety_receipt_hash",
        "val_exec_trace_head_hash",
    ]:
        if replay.get(key) != expected_keys.get(key):
            _fail("INVALID:NONDETERMINISTIC")
    if replay.get("promotion_bundle_hash") != str(promotion.get("bundle_id", "")):
        _fail("INVALID:NONDETERMINISTIC")

    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_sas_val_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        result = verify(Path(args.state_dir), mode=args.mode)
        print(result)
    except (SASValVerifyError, SealedRunnerError) as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
