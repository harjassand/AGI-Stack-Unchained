"""v19 replay verifier extending v18 with policy VM + policy market checks."""

from __future__ import annotations

import argparse
import json
import os
import traceback
from pathlib import Path
from typing import Any

from ..v18_0.ccap_runtime_v1 import compute_repo_base_tree_id_tolerant
from ..v18_0.omega_common_v1 import (
    canon_hash_obj,
    fail as fail_v18,
    load_canon_dict,
    repo_root as repo_root_v18,
    validate_schema as validate_schema_v18,
    write_hashed_json,
)
from ..v18_0 import verify_rsi_omega_daemon_v1 as verify_v18_module
from ..v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error
from ..v18_0.verify_rsi_omega_daemon_v1 import verify as verify_v18
from .common_v1 import validate_schema as validate_schema_v19
from .omega_promoter_v1 import _verify_axis_bundle_gate
from .verify_coordinator_isa_program_v1 import verify_program
from .verify_coordinator_opcode_table_v1 import verify_opcode_table
from .verify_counterfactual_trace_example_v1 import verify_counterfactual_trace_example
from .verify_hint_bundle_v1 import verify_hint_bundle
from .verify_inputs_descriptor_v1 import verify_inputs_descriptor
from .verify_merged_hint_state_v1 import verify_merged_hint_state
from .verify_policy_market_selection_v1 import verify_policy_market_selection
from .verify_policy_vm_stark_proof_v1 import verify_policy_vm_stark_proof
from .verify_policy_trace_proposal_v1 import verify_policy_trace_proposal
from .verify_policy_vm_trace_v1 import verify_policy_vm_trace
from .orch_bandit.verify_orch_bandit_v1 import verify_orch_bandit_v1
from .epistemic.action_market_v1 import build_default_action_market_profile, verify_action_market_replay
from .epistemic.compaction_v1 import verify_compaction_bundle
from .epistemic.verify_epistemic_certs_v1 import verify_certs_bundle
from .epistemic.verify_epistemic_capsule_v1 import verify_capsule_bundle
from .epistemic.usable_index_v1 import load_usable_capsule_ids, load_usable_graph_ids, load_rows as load_usable_rows
from .shadow_corpus_v1 import load_shadow_corpus_entries
from orchestrator.native.runtime_stats_v1 import (
    WORK_UNITS_FORMULA_ID,
    derive_total_work_units,
    derive_work_units_from_row,
)

_GE_SH1_CAMPAIGN_ID = "rsi_ge_symbiotic_optimizer_sh1_v0_1"
_HEAVY_DECLARED_CLASSES = {"FRONTIER_HEAVY", "CANARY_HEAVY"}
_AXIS_EXEMPTIONS_REL = "configs/omega_axis_gate_exemptions_v1.json"
_AXIS_EXEMPTIONS_SET_CACHE: set[str] | None = None
_DEFAULT_ORCH_MLX_MODEL_ID = "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit"


def _resolve_state_dir(path: Path) -> Path:
    root = path.resolve()
    if (root / "state").is_dir() and (root / "config").is_dir():
        return root / "state"
    if (root / "daemon" / "rsi_omega_daemon_v18_0" / "state").is_dir():
        return root / "daemon" / "rsi_omega_daemon_v18_0" / "state"
    if (root / "daemon" / "rsi_omega_daemon_v19_0" / "state").is_dir():
        return root / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    if root.name == "state" and (root.parent / "config").is_dir():
        return root
    fail_v18("SCHEMA_FAIL")
    return root


def _load_canon_json(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if not isinstance(payload, dict):
        fail_v18("SCHEMA_FAIL")
    return payload


def _relpath_or_abs(path_value: Any) -> str | None:
    if not isinstance(path_value, (str, Path)):
        return None
    try:
        path = Path(path_value).resolve()
    except Exception:
        return None
    try:
        return path.relative_to(repo_root_v18()).as_posix()
    except Exception:
        return path.as_posix()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and len(value.split(":", 1)[1]) == 64


def _resolve_orch_runtime_provenance(*, env_map: dict[str, Any] | None = None) -> tuple[str, str]:
    source = os.environ if env_map is None else env_map
    backend = str(source.get("ORCH_LLM_BACKEND", "mlx")).strip().lower() or "mlx"
    if backend == "mlx":
        model_id = str(source.get("ORCH_MLX_MODEL", _DEFAULT_ORCH_MLX_MODEL_ID)).strip() or _DEFAULT_ORCH_MLX_MODEL_ID
        return backend, model_id
    model_id = str(source.get("ORCH_MODEL_ID", "")).strip() or f"{backend}:default"
    return backend, model_id


def _verify_manifest_orch_provenance(manifest_payload: dict[str, Any]) -> None:
    declared_backend = str(manifest_payload.get("resolved_orch_llm_backend", "")).strip().lower()
    declared_model_id = str(manifest_payload.get("resolved_orch_model_id", "")).strip()
    if not declared_backend or not declared_model_id:
        env_payload = manifest_payload.get("env")
        if not isinstance(env_payload, dict):
            fail_v18("SCHEMA_FAIL")
        declared_backend, declared_model_id = _resolve_orch_runtime_provenance(env_map=env_payload)
    runtime_backend, runtime_model_id = _resolve_orch_runtime_provenance()
    if runtime_backend != declared_backend or runtime_model_id != declared_model_id:
        fail_v18("NONDETERMINISTIC")


def _require_sha256(value: Any, *, reason: str = "SCHEMA_FAIL") -> str:
    raw = str(value).strip()
    if not _is_sha256(raw):
        fail_v18(reason)
    return raw


def _nondeterministic_failure_detail(
    *,
    exc: BaseException,
) -> tuple[str | None, str | None, str | None, str | None]:
    frames = list(traceback.walk_tb(exc.__traceback__)) if exc.__traceback__ is not None else []
    failure_site: str | None = None
    path_rel: str | None = None
    expected_hash: str | None = None
    observed_hash: str | None = None
    for frame, lineno in reversed(frames):
        filename = Path(frame.f_code.co_filename)
        if filename.name != "verify_rsi_omega_daemon_v1.py":
            continue
        if failure_site is None:
            failure_site = f"{filename.name}:{int(lineno)}:{frame.f_code.co_name}"
        locals_map = frame.f_locals
        if path_rel is None:
            for key in (
                "path",
                "bundle_path",
                "promotion_path",
                "axis_path",
                "state_root",
                "state_dir",
                "replay_state_abs",
                "ccap_path",
            ):
                candidate = _relpath_or_abs(locals_map.get(key))
                if candidate is not None:
                    path_rel = candidate
                    break
        if expected_hash is None or observed_hash is None:
            for key in sorted(locals_map.keys()):
                value = locals_map.get(key)
                if not _is_sha256(value):
                    continue
                lowered = str(key).strip().lower()
                if expected_hash is None and "expected" in lowered:
                    expected_hash = str(value)
                    continue
                if observed_hash is None and any(token in lowered for token in ("observed", "actual", "adjusted", "replay")):
                    observed_hash = str(value)
    return failure_site, path_rel, expected_hash, observed_hash


def _write_state_verifier_failure_detail(
    *,
    state_dir: Path,
    reason_code: str,
    exc: BaseException,
) -> str | None:
    try:
        state_root = _resolve_state_dir(state_dir)
    except Exception:
        return None
    out_dir = state_root.parent / "state_verifier"
    failure_site, path_rel, expected_hash, observed_hash = _nondeterministic_failure_detail(exc=exc)
    payload: dict[str, Any] = {
        "schema_name": "state_verifier_failure_detail_v1",
        "schema_version": "v19_0",
        "failure_detail_id": "sha256:" + ("0" * 64),
        "reason_code": str(reason_code).strip() or "NONDETERMINISTIC",
        "failure_site": failure_site or "verify_rsi_omega_daemon_v1.py:unknown",
        "path_rel": path_rel,
        "expected_hash": expected_hash,
        "observed_hash": observed_hash,
    }
    _path, _payload, digest = write_hashed_json(
        out_dir,
        "state_verifier_failure_detail_v1.json",
        payload,
        id_field="failure_detail_id",
    )
    return digest


def _tail_lines(text: Any, *, max_lines: int = 10, max_chars: int = 4096) -> list[str]:
    rows = [str(line).rstrip() for line in str(text or "").splitlines() if str(line).rstrip()]
    if len(rows) > int(max_lines):
        rows = rows[-int(max_lines) :]
    out: list[str] = []
    for row in rows:
        if len(row) > int(max_chars):
            out.append(row[-int(max_chars) :])
        else:
            out.append(row)
    return out


def _write_state_verifier_replay_fail_detail(
    *,
    state_dir: Path,
    exc: BaseException,
) -> str | None:
    try:
        state_root = _resolve_state_dir(state_dir)
    except Exception:
        return None
    out_dir = state_root.parent / "state_verifier"
    v18_detail = verify_v18_module.get_last_subverifier_replay_fail_detail()
    detail = dict(v18_detail) if isinstance(v18_detail, dict) else {}
    reason_branch = str(detail.get("reason_branch", "")).strip().upper()
    if reason_branch not in {"MISSING_REPLAY_BINDING", "IMMUTABLE_TREE_MODIFIED", "REPLAY_CMD_FAILED"}:
        reason_branch = "MISSING_REPLAY_BINDING"
    replay_cmd_args_raw = detail.get("replay_cmd_args_v1")
    replay_cmd_args = [str(row) for row in replay_cmd_args_raw] if isinstance(replay_cmd_args_raw, list) else []
    replay_cmd_exit_code = detail.get("replay_cmd_exit_code")
    replay_cmd_stdout_tail_v1 = _tail_lines(detail.get("replay_cmd_stdout_tail_v1", ""))
    replay_cmd_stderr_tail_v1 = _tail_lines(detail.get("replay_cmd_stderr_tail_v1", ""))
    if isinstance(detail.get("replay_cmd_stdout_tail_v1"), list):
        replay_cmd_stdout_tail_v1 = _tail_lines("\n".join(str(row) for row in detail.get("replay_cmd_stdout_tail_v1")))
    if isinstance(detail.get("replay_cmd_stderr_tail_v1"), list):
        replay_cmd_stderr_tail_v1 = _tail_lines("\n".join(str(row) for row in detail.get("replay_cmd_stderr_tail_v1")))
    payload: dict[str, Any] = {
        "schema_name": "state_verifier_subverifier_replay_fail_detail_v1",
        "schema_version": "v19_0",
        "detail_id": "sha256:" + ("0" * 64),
        "tick_u64": int(max(0, int(detail.get("tick_u64", 0)))),
        "campaign_id": str(detail.get("campaign_id", "")).strip() or None,
        "verifier_module": str(detail.get("verifier_module", "")).strip() or None,
        "subrun_state_dir_rel": str(detail.get("subrun_state_dir_rel", "")).strip() or None,
        "expected_state_dir_hash": str(detail.get("expected_state_dir_hash", "")).strip() or None,
        "recomputed_state_dir_hash": str(detail.get("recomputed_state_dir_hash", "")).strip() or None,
        "reason_branch": reason_branch,
        "reason_detail": str(detail.get("reason_detail", "")).strip() or str(exc),
        "replay_cmd_args_v1": replay_cmd_args,
        "replay_cmd_exit_code": (int(replay_cmd_exit_code) if replay_cmd_exit_code is not None else None),
        "replay_cmd_stdout_tail_v1": replay_cmd_stdout_tail_v1,
        "replay_cmd_stderr_tail_v1": replay_cmd_stderr_tail_v1,
    }
    _path, _payload, digest = write_hashed_json(
        out_dir,
        "state_verifier_subverifier_replay_fail_detail_v1.json",
        payload,
        id_field="detail_id",
    )
    return digest


def _canonical_axis_gate_relpath(path_value: Any) -> str:
    raw = str(path_value).strip().replace("\\", "/")
    if not raw:
        fail_v18("SCHEMA_FAIL")
    parts: list[str] = []
    for token in raw.split("/"):
        part = str(token).strip()
        if not part or part == ".":
            continue
        if part == "..":
            fail_v18("SCHEMA_FAIL")
        parts.append(part)
    if not parts:
        fail_v18("SCHEMA_FAIL")
    rel = "/".join(parts)
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts:
        fail_v18("SCHEMA_FAIL")
    return rel


def _canonical_axis_gate_relpaths(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for row in value:
        text = str(row).strip()
        if not text:
            continue
        rel = _canonical_axis_gate_relpath(text)
        if rel not in seen:
            out.append(rel)
            seen.add(rel)
    return sorted(out)


def _load_axis_gate_exemptions_set() -> set[str]:
    global _AXIS_EXEMPTIONS_SET_CACHE
    cached = _AXIS_EXEMPTIONS_SET_CACHE
    if cached is not None:
        return set(cached)
    payload = _load_canon_json((repo_root_v18() / _AXIS_EXEMPTIONS_REL).resolve())
    if str(payload.get("schema_version", "")).strip() != "omega_axis_gate_exemptions_v1":
        fail_v18("SCHEMA_FAIL")
    rows = payload.get("exempt_relpaths")
    if not isinstance(rows, list) or not rows:
        fail_v18("SCHEMA_FAIL")
    out: set[str] = set()
    for row in rows:
        out.add(_canonical_axis_gate_relpath(row))
    _AXIS_EXEMPTIONS_SET_CACHE = set(out)
    return set(out)


def _load_axis_gate_decision_for_dispatch(*, state_root: Path, subrun_root_rel: str) -> dict[str, Any] | None:
    candidates: list[Path] = []
    subrun_rel = Path(subrun_root_rel)
    if not subrun_rel.is_absolute() and ".." not in subrun_rel.parts:
        candidates.append((state_root / subrun_rel / "promotion" / "axis_gate_decision_v1.json").resolve())
    candidates.extend(
        sorted(
            state_root.glob("dispatch/*/promotion/axis_gate_decision_v1.json"),
            key=lambda row: row.as_posix(),
        )
    )
    axis_path = next((path for path in candidates if path.exists() and path.is_file()), None)
    if axis_path is None:
        return None
    payload = _load_canon_json(axis_path)
    if str(payload.get("schema_name", "")).strip() != "axis_gate_decision_v1":
        fail_v18("SCHEMA_FAIL")
    if str(payload.get("schema_version", "")).strip() != "v19_0":
        fail_v18("SCHEMA_FAIL")
    return payload


def _load_pinned_pack_payload(
    *,
    config_dir: Path,
    pack: dict[str, Any],
    rel_key: str,
    id_key: str,
    payload_id_field: str,
    schema_name: str,
) -> dict[str, Any]:
    rel_raw = str(pack.get(rel_key, "")).strip()
    id_raw = str(pack.get(id_key, "")).strip()
    if not rel_raw or not id_raw:
        fail_v18("MISSING_STATE_INPUT")
    rel_path = Path(rel_raw)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        fail_v18("SCHEMA_FAIL")
    declared_id = _require_sha256(id_raw, reason="PIN_HASH_MISMATCH")
    path = config_dir / rel_path
    if not path.exists() or not path.is_file():
        fail_v18("MISSING_STATE_INPUT")
    payload = _load_canon_json(path)
    validate_schema_v19(payload, schema_name)
    observed_id = _require_sha256(payload.get(payload_id_field), reason="PIN_HASH_MISMATCH")
    payload_no_id = dict(payload)
    payload_no_id.pop(payload_id_field, None)
    if canon_hash_obj(payload_no_id) != observed_id:
        fail_v18("PIN_HASH_MISMATCH")
    if observed_id != declared_id:
        fail_v18("PIN_HASH_MISMATCH")
    return payload


def _task_input_set_hash(task_input_ids: list[str]) -> str:
    return canon_hash_obj(
        {
            "schema_version": "epistemic_cert_task_input_set_v1",
            "task_input_ids": sorted(_require_sha256(v, reason="SCHEMA_FAIL") for v in task_input_ids),
        }
    )


def _load_shadow_candidate_outputs(state_root: Path) -> dict[str, Any]:
    epi_root = state_root / "epistemic"
    capsule_rows = sorted((epi_root / "capsules").glob("sha256_*.epistemic_capsule_v1.json"), key=lambda p: p.as_posix())
    graph_rows = sorted((epi_root / "graphs").glob("sha256_*.qxwmr_graph_v1.json"), key=lambda p: p.as_posix())
    binding_rows = sorted((epi_root / "type_bindings").glob("sha256_*.epistemic_type_binding_v1.json"), key=lambda p: p.as_posix())
    registry_rows = sorted((epi_root / "type_registry").glob("sha256_*.epistemic_type_registry_v1.json"), key=lambda p: p.as_posix())
    eufc_rows = sorted((epi_root / "certs").glob("sha256_*.epistemic_eufc_v1.json"), key=lambda p: p.as_posix())
    strip_receipt_rows = sorted(
        (epi_root / "strip_receipts").glob("sha256_*.epistemic_instruction_strip_receipt_v1.json"),
        key=lambda p: p.as_posix(),
    )
    if not (capsule_rows and graph_rows and binding_rows and registry_rows and eufc_rows and strip_receipt_rows):
        fail_v18("MISSING_STATE_INPUT")
    capsule = _load_canon_json(capsule_rows[-1])
    graph = _load_canon_json(graph_rows[-1])
    type_binding = _load_canon_json(binding_rows[-1])
    type_registry = _load_canon_json(registry_rows[-1])
    eufc = _load_canon_json(eufc_rows[-1])
    strip_receipts = [_load_canon_json(path) for path in strip_receipt_rows]
    validate_schema_v19(capsule, "epistemic_capsule_v1")
    validate_schema_v19(graph, "qxwmr_graph_v1")
    validate_schema_v19(type_binding, "epistemic_type_binding_v1")
    validate_schema_v19(type_registry, "epistemic_type_registry_v1")
    validate_schema_v19(eufc, "epistemic_eufc_v1")
    for strip_receipt in strip_receipts:
        validate_schema_v19(strip_receipt, "epistemic_instruction_strip_receipt_v1")
    task_input_ids_raw = eufc.get("task_input_ids")
    if not isinstance(task_input_ids_raw, list):
        fail_v18("SCHEMA_FAIL")
    strip_contract_ids = sorted(
        {
            _require_sha256(strip_receipt.get("instruction_strip_contract_id"), reason="SCHEMA_FAIL")
            for strip_receipt in strip_receipts
        }
    )
    if len(strip_contract_ids) != 1:
        fail_v18("NONDETERMINISTIC")
    return {
        "graph_id": _require_sha256(graph.get("graph_id"), reason="SCHEMA_FAIL"),
        "type_binding_id": _require_sha256(type_binding.get("binding_id"), reason="SCHEMA_FAIL"),
        "type_registry_id": _require_sha256(type_registry.get("registry_id"), reason="SCHEMA_FAIL"),
        "cert_id": _require_sha256(eufc.get("eufc_id"), reason="SCHEMA_FAIL"),
        "cert_profile_id": _require_sha256(capsule.get("cert_profile_id"), reason="SCHEMA_FAIL"),
        "instruction_strip_contract_id": str(strip_contract_ids[0]),
        "strip_receipt_id": _require_sha256(capsule.get("strip_receipt_id"), reason="SCHEMA_FAIL"),
        "task_input_ids": sorted(_require_sha256(v, reason="SCHEMA_FAIL") for v in task_input_ids_raw),
    }


def _path_for_hash(dir_path: Path, digest: str, suffix: str) -> Path | None:
    if not _is_sha256(digest):
        return None
    hexd = digest.split(":", 1)[1]
    path = dir_path / f"sha256_{hexd}.{suffix}"
    if path.exists() and path.is_file():
        return path
    return None


def _load_hash_bound_payload(*, dir_path: Path, digest: str, suffix: str, schema_version: str) -> dict[str, Any]:
    path = _path_for_hash(dir_path, digest, suffix)
    if path is None:
        fail_v18("MISSING_STATE_INPUT")
    payload = _load_canon_json(path)
    if str(payload.get("schema_version", "")).strip() != schema_version:
        fail_v18("SCHEMA_FAIL")
    if canon_hash_obj(payload) != digest:
        fail_v18("NONDETERMINISTIC")
    return payload


def _latest_snapshot_or_fail(snapshot_dir: Path) -> dict[str, Any]:
    rows = sorted(snapshot_dir.glob("sha256_*.omega_tick_snapshot_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        fail_v18("MISSING_STATE_INPUT")
    best_payload: dict[str, Any] | None = None
    best_tick = -1
    for row in rows:
        payload = _load_canon_json(row)
        tick = int(payload.get("tick_u64", -1))
        if tick > best_tick:
            best_tick = tick
            best_payload = payload
    if best_payload is None:
        fail_v18("MISSING_STATE_INPUT")
    return best_payload


def _ledger_rows(state_root: Path) -> list[dict[str, Any]]:
    ledger_path = state_root / "ledger" / "omega_ledger_v1.jsonl"
    if not ledger_path.exists() or not ledger_path.is_file():
        fail_v18("MISSING_STATE_INPUT")
    rows: list[dict[str, Any]] = []
    prev_event_id: str | None = None
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            fail_v18("SCHEMA_FAIL")
            return rows
        if isinstance(row, dict):
            if str(row.get("schema_version", "")) != "omega_ledger_event_v1":
                fail_v18("SCHEMA_FAIL")
            event_id = str(row.get("event_id", "")).strip()
            if not _is_sha256(event_id):
                fail_v18("SCHEMA_FAIL")
            prev = row.get("prev_event_id")
            if prev_event_id is None:
                if prev is not None:
                    fail_v18("TRACE_HASH_MISMATCH")
            else:
                if str(prev) != prev_event_id:
                    fail_v18("TRACE_HASH_MISMATCH")
            prev_event_id = event_id
            rows.append(row)
    return rows


def _ledger_event_types(state_root: Path) -> list[str]:
    return [str(row.get("event_type", "")) for row in _ledger_rows(state_root)]


def _verify_long_run_ledger_bindings(state_root: Path) -> None:
    repo_root_path = repo_root_v18().resolve()
    rows = _ledger_rows(state_root)
    for row in rows:
        event_type = str(row.get("event_type", "")).strip()
        artifact_hash = _require_sha256(row.get("artifact_hash"), reason="SCHEMA_FAIL")
        if event_type == "LONG_RUN_LAUNCH_MANIFEST":
            path = _path_for_hash(
                state_root / "long_run" / "launch",
                artifact_hash,
                "long_run_launch_manifest_binding_v1.json",
            )
            if path is None:
                fail_v18("MISSING_STATE_INPUT")
            payload = _load_canon_json(path)
            if canon_hash_obj(payload) != artifact_hash:
                fail_v18("NONDETERMINISTIC")
            if str(payload.get("schema_name", "")).strip() != "long_run_launch_manifest_binding_v1":
                fail_v18("SCHEMA_FAIL")
            if str(payload.get("schema_version", "")).strip() != "v1":
                fail_v18("SCHEMA_FAIL")
            manifest_relpath = str(payload.get("manifest_relpath", "")).strip()
            if not manifest_relpath:
                fail_v18("SCHEMA_FAIL")
            manifest_path = repo_root_path / manifest_relpath
            try:
                manifest_path.resolve().relative_to(repo_root_path)
            except Exception:
                fail_v18("SCHEMA_FAIL")
            if not manifest_path.exists() or not manifest_path.is_file():
                fail_v18("MISSING_STATE_INPUT")
            manifest_payload = _load_canon_json(manifest_path)
            validate_schema_v19(manifest_payload, "long_run_launch_manifest_v1")
            manifest_id = _require_sha256(manifest_payload.get("manifest_id"), reason="SCHEMA_FAIL")
            manifest_no_id = dict(manifest_payload)
            manifest_no_id.pop("manifest_id", None)
            if canon_hash_obj(manifest_no_id) != manifest_id:
                fail_v18("NONDETERMINISTIC")
            if manifest_id != _require_sha256(payload.get("manifest_hash"), reason="SCHEMA_FAIL"):
                fail_v18("NONDETERMINISTIC")
            if str(manifest_payload.get("manifest_relpath", "")).strip() != manifest_relpath:
                fail_v18("NONDETERMINISTIC")
            _verify_manifest_orch_provenance(manifest_payload)
        elif event_type == "LONG_RUN_STOP_RECEIPT":
            path = _path_for_hash(
                state_root / "long_run" / "stop",
                artifact_hash,
                "long_run_stop_receipt_v1.json",
            )
            if path is None:
                fail_v18("MISSING_STATE_INPUT")
            payload = _load_canon_json(path)
            if canon_hash_obj(payload) != artifact_hash:
                fail_v18("NONDETERMINISTIC")
            if str(payload.get("schema_name", "")).strip() != "long_run_stop_receipt_v1":
                fail_v18("SCHEMA_FAIL")
            if str(payload.get("schema_version", "")).strip() != "v19_0":
                fail_v18("SCHEMA_FAIL")
            manifest_relpath = str(payload.get("manifest_relpath", "")).strip()
            if not manifest_relpath:
                fail_v18("SCHEMA_FAIL")
            manifest_path = repo_root_path / manifest_relpath
            try:
                manifest_path.resolve().relative_to(repo_root_path)
            except Exception:
                fail_v18("SCHEMA_FAIL")
            if not manifest_path.exists() or not manifest_path.is_file():
                fail_v18("MISSING_STATE_INPUT")
            manifest_payload = _load_canon_json(manifest_path)
            validate_schema_v19(manifest_payload, "long_run_launch_manifest_v1")
            manifest_id = _require_sha256(manifest_payload.get("manifest_id"), reason="SCHEMA_FAIL")
            manifest_no_id = dict(manifest_payload)
            manifest_no_id.pop("manifest_id", None)
            if canon_hash_obj(manifest_no_id) != manifest_id:
                fail_v18("NONDETERMINISTIC")
            if manifest_id != _require_sha256(payload.get("manifest_hash"), reason="SCHEMA_FAIL"):
                fail_v18("NONDETERMINISTIC")
            _verify_manifest_orch_provenance(manifest_payload)


def _find_nested_hash(state_root: Path, digest: str, suffix: str) -> Path:
    hexd = str(digest).split(":", 1)[1]
    target = f"sha256_{hexd}.{suffix}"
    rows = sorted(state_root.glob(f"dispatch/*/**/{target}"), key=lambda row: row.as_posix())
    if len(rows) != 1:
        fail_v18("MISSING_STATE_INPUT")
    return rows[0]


def _load_promotion_bundle_by_hash(state_root: Path, bundle_hash: str) -> Path | None:
    if not _is_sha256(bundle_hash):
        return None
    hexd = bundle_hash.split(":", 1)[1]
    rows = sorted(state_root.glob(f"subruns/**/sha256_{hexd}.*.json"), key=lambda row: row.as_posix())
    if not rows:
        return None
    return rows[0]


def _rethrow_as_v18(exc: Exception) -> None:
    msg = str(exc).strip()
    if msg.startswith("INVALID:"):
        msg = msg.split(":", 1)[1].strip()
    if not msg:
        msg = "NONDETERMINISTIC"
    fail_v18(msg)


def _load_pack(config_dir: Path) -> dict[str, Any]:
    pack = _load_canon_json(config_dir / "rsi_omega_daemon_pack_v1.json")
    if str(pack.get("schema_version", "")).strip() != "rsi_omega_daemon_pack_v2":
        fail_v18("NONDETERMINISTIC")
    return pack


def _verify_shadow_path(*, state_root: Path, config_dir: Path, snapshot: dict[str, Any]) -> None:
    pack = _load_pack(config_dir)
    shadow_integrity_hash = snapshot.get("shadow_fs_integrity_report_hash")
    shadow_tier_a_hash = snapshot.get("shadow_tier_a_receipt_hash")
    shadow_tier_b_hash = snapshot.get("shadow_tier_b_receipt_hash")
    shadow_readiness_hash = snapshot.get("shadow_readiness_receipt_hash")
    shadow_corpus_invariance_hash = snapshot.get("shadow_corpus_invariance_receipt_hash")

    any_shadow_hash = any(
        _is_sha256(value)
        for value in [
            shadow_integrity_hash,
            shadow_tier_a_hash,
            shadow_tier_b_hash,
            shadow_readiness_hash,
            shadow_corpus_invariance_hash,
        ]
    )
    if not any_shadow_hash:
        if bool(pack.get("auto_swap_b", False)):
            fail_v18("TIER_B_REQUIRED_FOR_SWAP")
        return

    if _is_sha256(shadow_integrity_hash):
        integrity_payload = _load_hash_bound_payload(
            dir_path=state_root / "shadow" / "integrity",
            digest=str(shadow_integrity_hash),
            suffix="shadow_fs_integrity_report_v1.json",
            schema_version="v19_0",
        )
        if str(integrity_payload.get("schema_name", "")) != "shadow_fs_integrity_report_v1":
            fail_v18("SCHEMA_FAIL")
        validate_schema_v19(integrity_payload, "shadow_fs_integrity_report_v1")
        if str(integrity_payload.get("status", "")) != "PASS":
            fail_v18("SHADOW_PROTECTED_ROOT_MUTATION")
    elif shadow_integrity_hash is not None:
        fail_v18("SCHEMA_FAIL")

    tier_a_payload = None
    tier_b_payload = None
    if _is_sha256(shadow_tier_a_hash):
        tier_a_payload = _load_hash_bound_payload(
            dir_path=state_root / "shadow" / "tier_a",
            digest=str(shadow_tier_a_hash),
            suffix="shadow_tier_receipt_v1.json",
            schema_version="v19_0",
        )
        if str(tier_a_payload.get("schema_name", "")) != "shadow_tier_receipt_v1":
            fail_v18("SCHEMA_FAIL")
        if str(tier_a_payload.get("tier", "")) != "A":
            fail_v18("SCHEMA_FAIL")
        if int(tier_a_payload.get("n_live_ticks", 0)) != 250:
            fail_v18("SCHEMA_FAIL")
        if int(tier_a_payload.get("n_fuzz_cases", 0)) != 512:
            fail_v18("SCHEMA_FAIL")
        if int(tier_a_payload.get("n_double_runs", 0)) != 50:
            fail_v18("SCHEMA_FAIL")
    elif shadow_tier_a_hash is not None:
        fail_v18("SCHEMA_FAIL")

    if _is_sha256(shadow_tier_b_hash):
        tier_b_payload = _load_hash_bound_payload(
            dir_path=state_root / "shadow" / "tier_b",
            digest=str(shadow_tier_b_hash),
            suffix="shadow_tier_receipt_v1.json",
            schema_version="v19_0",
        )
        if str(tier_b_payload.get("schema_name", "")) != "shadow_tier_receipt_v1":
            fail_v18("SCHEMA_FAIL")
        if str(tier_b_payload.get("tier", "")) != "B":
            fail_v18("SCHEMA_FAIL")
        if int(tier_b_payload.get("n_live_ticks", 0)) != 1000:
            fail_v18("SCHEMA_FAIL")
        if int(tier_b_payload.get("n_fuzz_cases", 0)) != 20000:
            fail_v18("SCHEMA_FAIL")
        if int(tier_b_payload.get("n_double_runs", 0)) != 1000:
            fail_v18("SCHEMA_FAIL")
    elif shadow_tier_b_hash is not None:
        fail_v18("SCHEMA_FAIL")

    readiness_payload = None
    if _is_sha256(shadow_readiness_hash):
        readiness_payload = _load_hash_bound_payload(
            dir_path=state_root / "shadow" / "readiness",
            digest=str(shadow_readiness_hash),
            suffix="shadow_regime_readiness_receipt_v1.json",
            schema_version="v19_0",
        )
        if str(readiness_payload.get("schema_name", "")) != "shadow_regime_readiness_receipt_v1":
            fail_v18("SCHEMA_FAIL")
        validate_schema_v19(readiness_payload, "shadow_regime_readiness_receipt_v1")
    elif shadow_readiness_hash is not None:
        fail_v18("SCHEMA_FAIL")

    corpus_invariance_payload = None
    if _is_sha256(shadow_corpus_invariance_hash):
        corpus_invariance_payload = _load_hash_bound_payload(
            dir_path=state_root / "shadow" / "invariance",
            digest=str(shadow_corpus_invariance_hash),
            suffix="shadow_corpus_invariance_receipt_v1.json",
            schema_version="v19_0",
        )
        if str(corpus_invariance_payload.get("schema_name", "")) != "shadow_corpus_invariance_receipt_v1":
            fail_v18("SCHEMA_FAIL")
        validate_schema_v19(corpus_invariance_payload, "shadow_corpus_invariance_receipt_v1")
    elif shadow_corpus_invariance_hash is not None:
        fail_v18("SCHEMA_FAIL")

    if isinstance(corpus_invariance_payload, dict):
        graph_contract = _load_pinned_pack_payload(
            config_dir=config_dir,
            pack=pack,
            rel_key="shadow_graph_invariance_contract_rel",
            id_key="shadow_graph_invariance_contract_id",
            payload_id_field="contract_id",
            schema_name="graph_invariance_contract_v1",
        )
        type_contract = _load_pinned_pack_payload(
            config_dir=config_dir,
            pack=pack,
            rel_key="shadow_type_binding_invariance_contract_rel",
            id_key="shadow_type_binding_invariance_contract_id",
            payload_id_field="contract_id",
            schema_name="type_binding_invariance_contract_v1",
        )
        cert_contract = _load_pinned_pack_payload(
            config_dir=config_dir,
            pack=pack,
            rel_key="shadow_cert_invariance_contract_rel",
            id_key="shadow_cert_invariance_contract_id",
            payload_id_field="contract_id",
            schema_name="cert_invariance_contract_v1",
        )
        if str(corpus_invariance_payload.get("graph_invariance_contract_id", "")) != str(graph_contract.get("contract_id", "")):
            fail_v18("PIN_HASH_MISMATCH")
        if (
            str(corpus_invariance_payload.get("type_binding_invariance_contract_id", ""))
            != str(type_contract.get("contract_id", ""))
        ):
            fail_v18("PIN_HASH_MISMATCH")
        if str(corpus_invariance_payload.get("cert_invariance_contract_id", "")) != str(cert_contract.get("contract_id", "")):
            fail_v18("PIN_HASH_MISMATCH")

        corpus_descriptor_payload = _load_pinned_pack_payload(
            config_dir=config_dir,
            pack=pack,
            rel_key="shadow_corpus_descriptor_rel",
            id_key="shadow_corpus_descriptor_id",
            payload_id_field="descriptor_id",
            schema_name="corpus_descriptor_v1",
        )
        corpus_descriptor_rel = str(pack.get("shadow_corpus_descriptor_rel", "")).strip()
        if not corpus_descriptor_rel:
            fail_v18("MISSING_STATE_INPUT")
        corpus_descriptor_rel_path = Path(corpus_descriptor_rel)
        if corpus_descriptor_rel_path.is_absolute() or ".." in corpus_descriptor_rel_path.parts:
            fail_v18("SCHEMA_FAIL")
        shadow_bundle = load_shadow_corpus_entries(
            corpus_descriptor=dict(corpus_descriptor_payload),
            descriptor_dir=(config_dir / corpus_descriptor_rel_path).parent,
        )
        replay_entries = [dict(row) for row in list(shadow_bundle.get("replay_entries") or []) if isinstance(row, dict)]
        replay_by_manifest_id = {
            str(row.get("entry_manifest_id", "")): row
            for row in replay_entries
            if isinstance(row, dict)
        }
        if len(replay_by_manifest_id) != len(replay_entries):
            fail_v18("NONDETERMINISTIC")

        shadow_cert_profile_id = _require_sha256(pack.get("shadow_cert_profile_id"), reason="MISSING_STATE_INPUT")
        shadow_instruction_strip_contract_id = _require_sha256(
            pack.get("shadow_instruction_strip_contract_id"),
            reason="MISSING_STATE_INPUT",
        )
        candidate_outputs = _load_shadow_candidate_outputs(state_root)
        if candidate_outputs["cert_profile_id"] != shadow_cert_profile_id:
            fail_v18("PIN_HASH_MISMATCH")
        if candidate_outputs["instruction_strip_contract_id"] != shadow_instruction_strip_contract_id:
            fail_v18("PIN_HASH_MISMATCH")

        rows = corpus_invariance_payload.get("compared_rows")
        if not isinstance(rows, list) or not rows:
            fail_v18("SCHEMA_FAIL")
        observed_graph_id = str(candidate_outputs["graph_id"])
        observed_type_binding_id = str(candidate_outputs["type_binding_id"])
        observed_type_registry_id = str(candidate_outputs["type_registry_id"])
        observed_cert_id = str(candidate_outputs["cert_id"])
        observed_cert_profile_id = str(candidate_outputs["cert_profile_id"])
        observed_strip_receipt_id = str(candidate_outputs["strip_receipt_id"])
        observed_task_input_set_hash = _task_input_set_hash(list(candidate_outputs["task_input_ids"]))
        graph_mode = str(graph_contract.get("equality_mode", "")).strip()
        graph_pass = True
        type_pass = True
        cert_pass = True
        for row in rows:
            if not isinstance(row, dict):
                fail_v18("SCHEMA_FAIL")
            entry_manifest_id = _require_sha256(row.get("entry_manifest_id"), reason="SCHEMA_FAIL")
            replay_entry = replay_by_manifest_id.get(entry_manifest_id)
            if replay_entry is None:
                fail_v18("NONDETERMINISTIC")
            contracts = replay_entry.get("contracts")
            expected_outputs = replay_entry.get("expected_outputs")
            if not isinstance(contracts, dict) or not isinstance(expected_outputs, dict):
                fail_v18("SCHEMA_FAIL")
            if str(contracts.get("instruction_strip_contract_id", "")) != shadow_instruction_strip_contract_id:
                fail_v18("PIN_HASH_MISMATCH")
            if str(contracts.get("cert_profile_id", "")) != shadow_cert_profile_id:
                fail_v18("PIN_HASH_MISMATCH")
            if str(expected_outputs.get("cert_profile_id", "")) != shadow_cert_profile_id:
                fail_v18("PIN_HASH_MISMATCH")
            if str(row.get("run_id", "")).strip() != str(replay_entry.get("run_id", "")).strip():
                fail_v18("NONDETERMINISTIC")
            if int(row.get("tick_u64", -1)) != int(replay_entry.get("tick_u64", -1)):
                fail_v18("NONDETERMINISTIC")
            if _require_sha256(row.get("tick_snapshot_hash"), reason="SCHEMA_FAIL") != str(
                replay_entry.get("tick_snapshot_hash", "")
            ):
                fail_v18("NONDETERMINISTIC")

            expected_graph_id = _require_sha256(expected_outputs.get("graph_id"), reason="SCHEMA_FAIL")
            expected_type_binding_id = _require_sha256(expected_outputs.get("type_binding_id"), reason="SCHEMA_FAIL")
            expected_cert_id = _require_sha256(expected_outputs.get("eufc_id"), reason="SCHEMA_FAIL")
            expected_strip_receipt_id = _require_sha256(expected_outputs.get("strip_receipt_id"), reason="SCHEMA_FAIL")
            expected_task_input_ids = expected_outputs.get("task_input_ids")
            if not isinstance(expected_task_input_ids, list):
                fail_v18("SCHEMA_FAIL")
            expected_task_input_set_hash = _task_input_set_hash([str(v) for v in expected_task_input_ids])

            if _require_sha256(row.get("expected_graph_id"), reason="SCHEMA_FAIL") != expected_graph_id:
                fail_v18("NONDETERMINISTIC")
            if _require_sha256(row.get("observed_graph_id"), reason="SCHEMA_FAIL") != observed_graph_id:
                fail_v18("NONDETERMINISTIC")
            if _require_sha256(row.get("expected_type_binding_id"), reason="SCHEMA_FAIL") != expected_type_binding_id:
                fail_v18("NONDETERMINISTIC")
            if _require_sha256(row.get("observed_type_binding_id"), reason="SCHEMA_FAIL") != observed_type_binding_id:
                fail_v18("NONDETERMINISTIC")
            if _require_sha256(row.get("expected_cert_id"), reason="SCHEMA_FAIL") != expected_cert_id:
                fail_v18("NONDETERMINISTIC")
            if _require_sha256(row.get("observed_cert_id"), reason="SCHEMA_FAIL") != observed_cert_id:
                fail_v18("NONDETERMINISTIC")
            if _require_sha256(row.get("expected_strip_receipt_id"), reason="SCHEMA_FAIL") != expected_strip_receipt_id:
                fail_v18("NONDETERMINISTIC")
            if _require_sha256(row.get("observed_strip_receipt_id"), reason="SCHEMA_FAIL") != observed_strip_receipt_id:
                fail_v18("NONDETERMINISTIC")
            if _require_sha256(row.get("expected_task_input_set_hash"), reason="SCHEMA_FAIL") != expected_task_input_set_hash:
                fail_v18("NONDETERMINISTIC")
            if _require_sha256(row.get("observed_task_input_set_hash"), reason="SCHEMA_FAIL") != observed_task_input_set_hash:
                fail_v18("NONDETERMINISTIC")

            if graph_mode == "ID_EQUAL":
                graph_match_b = observed_graph_id == expected_graph_id
            elif graph_mode == "CANON_PAYLOAD_EQUAL":
                graph_match_b = observed_graph_id == expected_graph_id
            else:
                fail_v18("SCHEMA_FAIL")
            type_match_b = observed_type_binding_id == expected_type_binding_id
            if bool(type_contract.get("require_same_type_registry_b", True)):
                type_match_b = bool(
                    type_match_b
                    and observed_type_registry_id
                    == _require_sha256(contracts.get("type_registry_id"), reason="SCHEMA_FAIL")
                )
            cert_match_b = observed_cert_id == expected_cert_id
            if bool(cert_contract.get("require_same_cert_profile_b", True)):
                cert_match_b = bool(cert_match_b and observed_cert_profile_id == str(expected_outputs["cert_profile_id"]))
            if bool(cert_contract.get("require_same_strip_receipt_b", True)):
                cert_match_b = bool(cert_match_b and observed_strip_receipt_id == expected_strip_receipt_id)
            if bool(cert_contract.get("require_same_task_input_ids_b", True)):
                cert_match_b = bool(cert_match_b and observed_task_input_set_hash == expected_task_input_set_hash)

            if bool(row.get("graph_match_b", False)) != bool(graph_match_b):
                fail_v18("NONDETERMINISTIC")
            if bool(row.get("type_binding_match_b", False)) != bool(type_match_b):
                fail_v18("NONDETERMINISTIC")
            if bool(row.get("cert_match_b", False)) != bool(cert_match_b):
                fail_v18("NONDETERMINISTIC")

            graph_pass = bool(graph_pass and graph_match_b)
            type_pass = bool(type_pass and type_match_b)
            cert_pass = bool(cert_pass and cert_match_b)

        if bool(corpus_invariance_payload.get("graph_invariance_pass_b", False)) != bool(graph_pass):
            fail_v18("NONDETERMINISTIC")
        if bool(corpus_invariance_payload.get("type_binding_invariance_pass_b", False)) != bool(type_pass):
            fail_v18("NONDETERMINISTIC")
        if bool(corpus_invariance_payload.get("cert_invariance_pass_b", False)) != bool(cert_pass):
            fail_v18("NONDETERMINISTIC")
        if bool(corpus_invariance_payload.get("pass_b", False)) != bool(graph_pass and type_pass and cert_pass):
            fail_v18("NONDETERMINISTIC")

    if isinstance(readiness_payload, dict):
        if bool(readiness_payload.get("runtime_tier_b_pass_b", False)) != bool(readiness_payload.get("tier_b_pass_b", False)):
            fail_v18("NONDETERMINISTIC")
        if isinstance(tier_a_payload, dict) and bool(tier_a_payload.get("pass_b", False)) != bool(readiness_payload.get("tier_a_pass_b", False)):
            fail_v18("NONDETERMINISTIC")
        if isinstance(tier_b_payload, dict) and bool(tier_b_payload.get("pass_b", False)) != bool(readiness_payload.get("tier_b_pass_b", False)):
            fail_v18("NONDETERMINISTIC")
        if isinstance(tier_b_payload, dict):
            if bool(tier_b_payload.get("window_rule_pass_b", False)) != bool(readiness_payload.get("j_window_rule_verified_b", False)):
                fail_v18("NONDETERMINISTIC")
            if bool(tier_b_payload.get("per_tick_floor_pass_b", False)) != bool(readiness_payload.get("j_per_tick_floor_verified_b", False)):
                fail_v18("NONDETERMINISTIC")
            if bool(tier_b_payload.get("determinism_pass_b", False)) != bool(readiness_payload.get("deterministic_fuzz_verified_b", False)):
                fail_v18("NONDETERMINISTIC")
            if bool(tier_b_payload.get("conservatism_pass_b", False)) != bool(readiness_payload.get("corpus_replay_verified_b", False)):
                fail_v18("NONDETERMINISTIC")
        if isinstance(corpus_invariance_payload, dict):
            if bool(corpus_invariance_payload.get("pass_b", False)) != bool(readiness_payload.get("corpus_invariance_verified_b", False)):
                fail_v18("NONDETERMINISTIC")
            if str(readiness_payload.get("corpus_invariance_receipt_id", "")) != str(corpus_invariance_payload.get("receipt_id", "")):
                fail_v18("NONDETERMINISTIC")
        elif bool(readiness_payload.get("corpus_invariance_verified_b", False)):
            fail_v18("MISSING_STATE_INPUT")

    if bool(pack.get("auto_swap_b", False)):
        if not isinstance(readiness_payload, dict):
            fail_v18("TIER_B_REQUIRED_FOR_SWAP")
        if not bool(readiness_payload.get("runtime_tier_b_pass_b", False)):
            fail_v18("TIER_B_REQUIRED_FOR_SWAP")
        if str(readiness_payload.get("verdict", "")) != "READY":
            fail_v18("TIER_B_REQUIRED_FOR_SWAP")

        handoff_rel = str(pack.get("shadow_handoff_receipt_rel", "")).strip()
        if not handoff_rel:
            fail_v18("TIER_B_REQUIRED_FOR_SWAP")
        handoff_rel_path = Path(handoff_rel)
        if handoff_rel_path.is_absolute() or ".." in handoff_rel_path.parts:
            fail_v18("SCHEMA_FAIL")
        handoff_path = config_dir / handoff_rel_path
        if not handoff_path.exists() or not handoff_path.is_file():
            fail_v18("MISSING_STATE_INPUT")
        handoff_payload = _load_canon_json(handoff_path)
        validate_schema_v19(handoff_payload, "shadow_regime_readiness_receipt_v1")
        if not bool(handoff_payload.get("runtime_tier_b_pass_b", False)):
            fail_v18("TIER_B_REQUIRED_FOR_SWAP")
        if isinstance(readiness_payload, dict):
            if str(handoff_payload.get("rollback_evidence_hash", "")) != str(readiness_payload.get("rollback_evidence_hash", "")):
                fail_v18("NONDETERMINISTIC")


def _verify_core_policy_assets(*, config_dir: Path, pack: dict[str, Any], descriptor_payload: dict[str, Any]) -> dict[str, Any]:
    opcode_rel = str(pack.get("coordinator_opcode_table_rel", "")).strip()
    if not opcode_rel:
        fail_v18("MISSING_STATE_INPUT")
    opcode_payload = _load_canon_json(config_dir / opcode_rel)
    try:
        verify_opcode_table(opcode_payload)
    except Exception as exc:
        _rethrow_as_v18(exc)
    if str(pack.get("coordinator_opcode_table_id", "")) != str(opcode_payload.get("opcode_table_id", "")):
        fail_v18("PIN_HASH_MISMATCH")
    descriptor_opcode_id = str(
        descriptor_payload.get("opcode_table_id", descriptor_payload.get("coordinator_opcode_table_id", ""))
    ).strip()
    if descriptor_opcode_id and descriptor_opcode_id != str(opcode_payload.get("opcode_table_id", "")):
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    predictor_payload = None
    predictor_id = str(pack.get("predictor_id", "")).strip() or ("sha256:" + ("0" * 64))
    predictor_rel = str(pack.get("predictor_weights_rel", "")).strip()
    if predictor_rel:
        predictor_payload = _load_canon_json(config_dir / predictor_rel)
        payload_predictor_id = predictor_payload.get("predictor_id")
        if payload_predictor_id is not None and str(payload_predictor_id).strip() != predictor_id:
            fail_v18("PREDICTOR_HASH_MISMATCH")
    descriptor_predictor_id = descriptor_payload.get("predictor_id")
    if descriptor_predictor_id is not None and str(descriptor_predictor_id) != predictor_id:
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    j_profile_payload = None
    j_profile_id = str(pack.get("objective_j_profile_id", "")).strip() or ("sha256:" + ("0" * 64))
    j_profile_rel = str(pack.get("objective_j_profile_rel", "")).strip()
    if j_profile_rel:
        j_profile_payload = _load_canon_json(config_dir / j_profile_rel)
        payload_profile_id = j_profile_payload.get("profile_id")
        if payload_profile_id is not None and str(payload_profile_id).strip() != j_profile_id:
            fail_v18("J_PROFILE_HASH_MISMATCH")
    descriptor_j_profile_id = descriptor_payload.get("j_profile_id")
    if descriptor_j_profile_id is not None and str(descriptor_j_profile_id) != j_profile_id:
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    policy_budget_spec_payload = None
    policy_budget_spec_id = str(pack.get("policy_budget_spec_id", "")).strip() or ("sha256:" + ("0" * 64))
    policy_budget_spec_rel = str(pack.get("policy_budget_spec_rel", "")).strip()
    if policy_budget_spec_rel:
        policy_budget_spec_payload = _load_canon_json(config_dir / policy_budget_spec_rel)
        if canon_hash_obj(policy_budget_spec_payload) != policy_budget_spec_id:
            fail_v18("PIN_HASH_MISMATCH")
    descriptor_budget_id = descriptor_payload.get("budget_spec_id")
    if descriptor_budget_id is not None and str(descriptor_budget_id) != policy_budget_spec_id:
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    determinism_contract_payload = None
    determinism_contract_id = str(pack.get("policy_determinism_contract_id", "")).strip() or ("sha256:" + ("0" * 64))
    determinism_contract_rel = str(pack.get("policy_determinism_contract_rel", "")).strip()
    if determinism_contract_rel:
        determinism_contract_payload = _load_canon_json(config_dir / determinism_contract_rel)
        if str(determinism_contract_payload.get("determinism_contract_id", "")) != determinism_contract_id:
            fail_v18("PIN_HASH_MISMATCH")
    descriptor_det_id = descriptor_payload.get("determinism_contract_id")
    if descriptor_det_id is not None and str(descriptor_det_id) != determinism_contract_id:
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    return {
        "opcode_table": opcode_payload,
        "predictor_payload": predictor_payload,
        "predictor_id": predictor_id,
        "j_profile_payload": j_profile_payload,
        "j_profile_id": j_profile_id,
        "policy_budget_spec_payload": policy_budget_spec_payload,
    }


def _verify_decision_only_vm_replay(
    *,
    state_root: Path,
    config_dir: Path,
    pack: dict[str, Any],
    descriptor_payload: dict[str, Any],
    descriptor_hash: str,
    decision_payload: dict[str, Any],
    snapshot: dict[str, Any],
    assets: dict[str, Any],
    skip_vm_replay: bool = False,
) -> None:
    program_rel = str(pack.get("coordinator_isa_program_rel", "")).strip()
    if not program_rel:
        fail_v18("MISSING_STATE_INPUT")
    program = _load_canon_json(config_dir / program_rel)
    try:
        verify_program(program)
    except Exception as exc:
        _rethrow_as_v18(exc)
    if str(pack.get("coordinator_isa_program_id", "")) != str(program.get("program_id", "")):
        fail_v18("PIN_HASH_MISMATCH")
    program_ids = descriptor_payload.get("policy_program_ids")
    if isinstance(program_ids, list):
        if len(program_ids) != 1 or str(program_ids[0]) != str(program.get("program_id", "")):
            fail_v18("INPUTS_DESCRIPTOR_MISMATCH")
    else:
        legacy_program_id = str(descriptor_payload.get("coordinator_isa_program_id", "")).strip()
        if legacy_program_id and legacy_program_id != str(program.get("program_id", "")):
            fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    trace_hash = snapshot.get("policy_vm_trace_hash")
    trace_payload = None
    if trace_hash is not None:
        if not _is_sha256(trace_hash):
            fail_v18("SCHEMA_FAIL")
        trace_payload = _load_hash_bound_payload(
            dir_path=state_root / "policy" / "traces",
            digest=str(trace_hash),
            suffix="policy_vm_trace_v1.json",
            schema_version="policy_vm_trace_v1",
        )
        try:
            verify_policy_vm_trace(trace_payload)
        except Exception as exc:
            _rethrow_as_v18(exc)

    observation_payload = _load_hash_bound_payload(
        dir_path=state_root / "observations",
        digest=str(snapshot.get("observation_report_hash")),
        suffix="omega_observation_report_v1.json",
        schema_version="omega_observation_report_v1",
    )

    from orchestrator.omega_v19_0.policy_vm_v1 import run_policy_vm_v1

    if skip_vm_replay:
        return

    replay_out = run_policy_vm_v1(
        tick_u64=int(decision_payload.get("tick_u64", 0)),
        mode="DECISION_ONLY",
        inputs_descriptor_hash=descriptor_hash,
        observation_report=observation_payload,
        observation_hash=str(snapshot.get("observation_report_hash")),
        issue_bundle_hash=str(snapshot.get("issue_bundle_hash")),
        policy_hash=str(decision_payload.get("policy_hash")),
        registry=_load_canon_json(config_dir / "omega_capability_registry_v2.json"),
        registry_hash=str(decision_payload.get("registry_hash")),
        budgets_hash=str(decision_payload.get("budgets_hash")),
        program=program,
        opcode_table=assets["opcode_table"],
        predictor_payload=assets["predictor_payload"],
        predictor_id=assets["predictor_id"],
        j_profile_payload=assets["j_profile_payload"],
        j_profile_id=assets["j_profile_id"],
        branch_id=str(pack.get("policy_branch_id", "b00")),
        round_u32=int(pack.get("policy_round_u32", 0)),
        policy_budget_spec=assets["policy_budget_spec_payload"],
    )
    replay_plan = replay_out.get("decision_plan")
    if not isinstance(replay_plan, dict):
        fail_v18("NONDETERMINISTIC")
    if canon_hash_obj(replay_plan) != canon_hash_obj(decision_payload):
        tie_break_path = decision_payload.get("tie_break_path")
        forced_frontier_override_b = (
            isinstance(tie_break_path, list)
            and any(str(row).strip() == "FORCED_FRONTIER_OVERRIDE" for row in tie_break_path)
        )
        if not forced_frontier_override_b:
            fail_v18("NONDETERMINISTIC")
    if trace_payload is not None:
        replay_trace = replay_out.get("policy_vm_trace")
        if not isinstance(replay_trace, dict):
            fail_v18("NONDETERMINISTIC")
        if canon_hash_obj(replay_trace) != canon_hash_obj(trace_payload):
            fail_v18("NONDETERMINISTIC")


def _verify_policy_market_replay(
    *,
    state_root: Path,
    config_dir: Path,
    pack: dict[str, Any],
    descriptor_payload: dict[str, Any],
    descriptor_hash: str,
    decision_payload: dict[str, Any],
    snapshot: dict[str, Any],
    assets: dict[str, Any],
) -> None:
    selection_hash = snapshot.get("policy_market_selection_hash")
    if not _is_sha256(selection_hash):
        fail_v18("MISSING_STATE_INPUT")
    selection_payload = _load_hash_bound_payload(
        dir_path=state_root / "policy" / "selection",
        digest=str(selection_hash),
        suffix="policy_market_selection_v1.json",
        schema_version="policy_market_selection_v1",
    )
    try:
        verify_policy_market_selection(selection_payload)
    except Exception as exc:
        _rethrow_as_v18(exc)
    if str(selection_payload.get("inputs_descriptor_hash", "")) != descriptor_hash:
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    proposal_hashes = selection_payload.get("proposal_hashes")
    if not isinstance(proposal_hashes, list) or not proposal_hashes:
        fail_v18("SCHEMA_FAIL")
    proposals_by_hash: dict[str, dict[str, Any]] = {}
    traces_by_hash: dict[str, dict[str, Any]] = {}
    decisions_by_hash: dict[str, dict[str, Any]] = {}
    for proposal_hash in proposal_hashes:
        if not _is_sha256(proposal_hash):
            fail_v18("SCHEMA_FAIL")
        proposal_payload = _load_hash_bound_payload(
            dir_path=state_root / "policy" / "proposals",
            digest=str(proposal_hash),
            suffix="policy_trace_proposal_v1.json",
            schema_version="policy_trace_proposal_v1",
        )
        try:
            verify_policy_trace_proposal(proposal_payload)
        except Exception as exc:
            _rethrow_as_v18(exc)
        if str(proposal_payload.get("inputs_descriptor_hash", "")) != descriptor_hash:
            fail_v18("INPUTS_DESCRIPTOR_MISMATCH")
        vm_trace_hash = str(proposal_payload.get("vm_trace_hash", ""))
        trace_payload = _load_hash_bound_payload(
            dir_path=state_root / "policy" / "traces",
            digest=vm_trace_hash,
            suffix="policy_vm_trace_v1.json",
            schema_version="policy_vm_trace_v1",
        )
        try:
            verify_policy_vm_trace(trace_payload)
        except Exception as exc:
            _rethrow_as_v18(exc)
        decision_hash = str(proposal_payload.get("decision_plan_hash", ""))
        decision_branch = _load_hash_bound_payload(
            dir_path=state_root / "policy" / "branch_decisions",
            digest=decision_hash,
            suffix="omega_decision_plan_v1.json",
            schema_version="omega_decision_plan_v1",
        )
        if str((decision_branch.get("recompute_proof") or {}).get("inputs_hash", "")) != descriptor_hash:
            fail_v18("INPUTS_DESCRIPTOR_MISMATCH")
        proposals_by_hash[str(proposal_hash)] = proposal_payload
        traces_by_hash[vm_trace_hash] = trace_payload
        decisions_by_hash[decision_hash] = decision_branch

    hint_files = sorted((state_root / "policy" / "hints").glob("sha256_*.hint_bundle_v1.json"), key=lambda p: p.as_posix())
    hint_hashes_by_branch_round: dict[tuple[str, int], str] = {}
    for path in hint_files:
        hint_payload = _load_canon_json(path)
        hint_hash = "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]
        if canon_hash_obj(hint_payload) != hint_hash:
            fail_v18("NONDETERMINISTIC")
        try:
            verify_hint_bundle(hint_payload)
        except Exception as exc:
            _rethrow_as_v18(exc)
        branch_id = str(hint_payload.get("branch_id", "")).strip()
        round_u32 = int(hint_payload.get("round_u32", -1))
        if round_u32 < 0 or not branch_id:
            fail_v18("SCHEMA_FAIL")
        hint_hashes_by_branch_round[(branch_id, round_u32)] = hint_hash
    merged_files = sorted((state_root / "policy" / "merged_hints").glob("sha256_*.merged_hint_state_v1.json"), key=lambda p: p.as_posix())
    for path in merged_files:
        payload = _load_canon_json(path)
        if canon_hash_obj(payload) != "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]:
            fail_v18("NONDETERMINISTIC")
        try:
            verify_merged_hint_state(payload)
        except Exception as exc:
            _rethrow_as_v18(exc)
        round_u32 = int(payload.get("round_u32", -1))
        if round_u32 >= 0:
            expected = sorted(
                value for (branch, rnd), value in hint_hashes_by_branch_round.items() if rnd == round_u32 and branch.startswith("b")
            )
            observed = sorted(str(row) for row in payload.get("contributing_hint_hashes", []))
            if expected and observed != expected:
                fail_v18("HINT_SYNC_VIOLATION")

    selection_policy_rel = str(pack.get("policy_selection_policy_rel", "")).strip()
    if not selection_policy_rel:
        fail_v18("MISSING_STATE_INPUT")
    selection_policy = _load_canon_json(config_dir / selection_policy_rel)

    from orchestrator.omega_bid_market_v2 import select_policy_proposal

    ordered_proposals = sorted(proposals_by_hash.values(), key=lambda row: str(row.get("branch_id", "")))
    replay_selection = select_policy_proposal(
        inputs_descriptor=descriptor_payload,
        proposals=ordered_proposals,
        predictor=assets["predictor_payload"],
        j_profile=assets["j_profile_payload"],
        selection_policy=selection_policy,
        observation_report=_load_hash_bound_payload(
            dir_path=state_root / "observations",
            digest=str(snapshot.get("observation_report_hash")),
            suffix="omega_observation_report_v1.json",
            schema_version="omega_observation_report_v1",
        ),
        traces_by_hash=traces_by_hash,
        decision_plans_by_hash=decisions_by_hash,
    )
    if canon_hash_obj(replay_selection) != str(selection_hash):
        fail_v18("NONDETERMINISTIC")

    winner_hash = str(selection_payload.get("winner_proposal_hash", ""))
    winner = proposals_by_hash.get(winner_hash)
    if not isinstance(winner, dict):
        fail_v18("MISSING_STATE_INPUT")
    winner_decision_hash = str(winner.get("decision_plan_hash", ""))
    if canon_hash_obj(decision_payload) != winner_decision_hash:
        fail_v18("NONDETERMINISTIC")

    cf_hash = snapshot.get("counterfactual_trace_example_hash")
    if cf_hash is not None:
        if not _is_sha256(cf_hash):
            fail_v18("SCHEMA_FAIL")
        cf_payload = _load_hash_bound_payload(
            dir_path=state_root / "policy" / "counterfactual",
            digest=str(cf_hash),
            suffix="counterfactual_trace_example_v1.json",
            schema_version="counterfactual_trace_example_v1",
        )
        try:
            verify_counterfactual_trace_example(cf_payload)
        except Exception as exc:
            _rethrow_as_v18(exc)
        if str(cf_payload.get("inputs_descriptor_hash", "")) != descriptor_hash:
            fail_v18("INPUTS_DESCRIPTOR_MISMATCH")
        if str((cf_payload.get("winner") or {}).get("proposal_hash", "")) != winner_hash:
            fail_v18("NONDETERMINISTIC")


def _verify_policy_path(state_root: Path, snapshot: dict[str, Any]) -> None:
    decision_hash = snapshot.get("decision_plan_hash")
    if not _is_sha256(decision_hash):
        fail_v18("SCHEMA_FAIL")
    decision_payload = _load_hash_bound_payload(
        dir_path=state_root / "decisions",
        digest=str(decision_hash),
        suffix="omega_decision_plan_v1.json",
        schema_version="omega_decision_plan_v1",
    )
    proof = decision_payload.get("recompute_proof")
    if not isinstance(proof, dict):
        fail_v18("NONDETERMINISTIC")
    inputs_hash = proof.get("inputs_hash")
    if not _is_sha256(inputs_hash):
        return

    descriptor_payload = _load_hash_bound_payload(
        dir_path=state_root / "policy" / "inputs",
        digest=str(inputs_hash),
        suffix="inputs_descriptor_v1.json",
        schema_version="inputs_descriptor_v1",
    )
    try:
        verify_inputs_descriptor(descriptor_payload)
    except Exception as exc:
        _rethrow_as_v18(exc)
    if str(snapshot.get("inputs_descriptor_hash")) not in {"None", "null"} and snapshot.get("inputs_descriptor_hash") is not None:
        if str(snapshot.get("inputs_descriptor_hash")) != str(inputs_hash):
            fail_v18("INPUTS_DESCRIPTOR_MISMATCH")
    expected_repo_tree_id = compute_repo_base_tree_id_tolerant(repo_root_v18())
    if str(descriptor_payload.get("repo_tree_id", "")) != str(expected_repo_tree_id):
        fail_v18("INPUTS_DESCRIPTOR_MISMATCH")

    config_dir = state_root.parent / "config"
    if not config_dir.exists() or not config_dir.is_dir():
        fail_v18("MISSING_STATE_INPUT")
    pack = _load_pack(config_dir)
    assets = _verify_core_policy_assets(
        config_dir=config_dir,
        pack=pack,
        descriptor_payload=descriptor_payload,
    )
    proof_hash = snapshot.get("policy_vm_stark_proof_hash")
    proof_runtime_status = snapshot.get("policy_vm_proof_runtime_status")
    proof_fallback_reason = snapshot.get("policy_vm_proof_fallback_reason_code")
    if proof_runtime_status is not None:
        runtime_norm = str(proof_runtime_status).strip().upper()
        if runtime_norm not in {"ABSENT", "FAILED", "EMITTED"}:
            fail_v18("SCHEMA_FAIL")
        proof_runtime_status = runtime_norm
    if proof_fallback_reason is not None:
        proof_fallback_reason = str(proof_fallback_reason).strip()
        if not proof_fallback_reason:
            fail_v18("SCHEMA_FAIL")
    if _is_sha256(proof_hash):
        if proof_runtime_status in {"ABSENT", "FAILED"}:
            fail_v18("NONDETERMINISTIC")
    elif proof_runtime_status == "EMITTED":
        fail_v18("NONDETERMINISTIC")

    ledger_events = _ledger_event_types(state_root)
    if _is_sha256(proof_hash):
        if "POLICY_VM_PROOF" not in ledger_events:
            fail_v18("NONDETERMINISTIC")
    if bool(pack.get("policy_vm_stark_proof_enable_b", False)) and proof_runtime_status in {"ABSENT", "FAILED"}:
        if "POLICY_VM_PROOF_FALLBACK" not in ledger_events:
            fail_v18("NONDETERMINISTIC")
        if not proof_fallback_reason:
            fail_v18("NONDETERMINISTIC")
    if proof_runtime_status == "EMITTED" and proof_fallback_reason:
        fail_v18("NONDETERMINISTIC")

    proof_assets: dict[str, Any] = {}
    if bool(pack.get("policy_vm_stark_proof_enable_b", False)):
        air_profile_rel = str(pack.get("policy_vm_air_profile_rel", "")).strip()
        air_profile_id = str(pack.get("policy_vm_air_profile_id", "")).strip()
        backend_rel = str(pack.get("policy_vm_winterfell_backend_contract_rel", "")).strip()
        backend_id = str(pack.get("policy_vm_winterfell_backend_contract_id", "")).strip()
        action_enum_rel = str(pack.get("policy_vm_action_kind_enum_rel", "")).strip()
        action_enum_id = str(pack.get("policy_vm_action_kind_enum_id", "")).strip()
        campaign_ids_rel = str(pack.get("policy_vm_candidate_campaign_ids_list_rel", "")).strip()
        campaign_ids_id = str(pack.get("policy_vm_candidate_campaign_ids_list_id", "")).strip()
        if not all([air_profile_rel, air_profile_id, backend_rel, backend_id, action_enum_rel, action_enum_id, campaign_ids_rel, campaign_ids_id]):
            fail_v18("MISSING_STATE_INPUT")

        air_profile_payload = _load_canon_json(config_dir / air_profile_rel)
        validate_schema_v19(air_profile_payload, "policy_vm_air_profile_v1")
        observed_air_profile_id = canon_hash_obj({k: v for k, v in air_profile_payload.items() if k != "air_profile_id"})
        if str(air_profile_payload.get("air_profile_id", "")) != observed_air_profile_id:
            fail_v18("PIN_HASH_MISMATCH")
        if observed_air_profile_id != air_profile_id:
            fail_v18("PIN_HASH_MISMATCH")

        backend_payload = _load_canon_json(config_dir / backend_rel)
        validate_schema_v19(backend_payload, "policy_vm_winterfell_backend_contract_v1")
        observed_backend_id = canon_hash_obj({k: v for k, v in backend_payload.items() if k != "backend_contract_id"})
        if str(backend_payload.get("backend_contract_id", "")) != observed_backend_id:
            fail_v18("PIN_HASH_MISMATCH")
        if observed_backend_id != backend_id:
            fail_v18("PIN_HASH_MISMATCH")

        action_kind_enum_payload = _load_canon_json(config_dir / action_enum_rel)
        validate_schema_v19(action_kind_enum_payload, "action_kind_enum_v1")
        observed_action_enum_id = canon_hash_obj({k: v for k, v in action_kind_enum_payload.items() if k != "action_kind_enum_id"})
        if str(action_kind_enum_payload.get("action_kind_enum_id", "")) != observed_action_enum_id:
            fail_v18("PIN_HASH_MISMATCH")
        if observed_action_enum_id != action_enum_id:
            fail_v18("PIN_HASH_MISMATCH")

        candidate_campaign_ids_payload = _load_canon_json(config_dir / campaign_ids_rel)
        validate_schema_v19(candidate_campaign_ids_payload, "candidate_campaign_ids_list_v1")
        observed_campaign_ids_id = canon_hash_obj(
            {k: v for k, v in candidate_campaign_ids_payload.items() if k != "candidate_campaign_ids_list_id"}
        )
        if str(candidate_campaign_ids_payload.get("candidate_campaign_ids_list_id", "")) != observed_campaign_ids_id:
            fail_v18("PIN_HASH_MISMATCH")
        if observed_campaign_ids_id != campaign_ids_id:
            fail_v18("PIN_HASH_MISMATCH")

        if str(air_profile_payload.get("action_kind_enum_hash", "")) != observed_action_enum_id:
            fail_v18("PIN_HASH_MISMATCH")
        if str(air_profile_payload.get("candidate_campaign_ids_list_hash", "")) != observed_campaign_ids_id:
            fail_v18("PIN_HASH_MISMATCH")

        proof_assets = {
            "air_profile_payload": air_profile_payload,
            "backend_contract_payload": backend_payload,
            "action_kind_enum_payload": action_kind_enum_payload,
            "candidate_campaign_ids_payload": candidate_campaign_ids_payload,
        }

    proof_valid = False
    if _is_sha256(proof_hash):
        trace_hash = snapshot.get("policy_vm_trace_hash")
        trace_payload = None
        if _is_sha256(trace_hash):
            trace_payload = _load_hash_bound_payload(
                dir_path=state_root / "policy" / "traces",
                digest=str(trace_hash),
                suffix="policy_vm_trace_v1.json",
                schema_version="policy_vm_trace_v1",
            )
            try:
                verify_policy_vm_trace(trace_payload)
            except Exception as exc:
                _rethrow_as_v18(exc)
        program_ids = descriptor_payload.get("policy_program_ids")
        policy_program_id = None
        if isinstance(program_ids, list) and len(program_ids) == 1 and _is_sha256(program_ids[0]):
            policy_program_id = str(program_ids[0])
        elif _is_sha256(descriptor_payload.get("coordinator_isa_program_id")):
            policy_program_id = str(descriptor_payload.get("coordinator_isa_program_id"))
        if policy_program_id is None and isinstance(program_ids, list):
            proof_payload_peek = _load_hash_bound_payload(
                dir_path=state_root / "policy" / "proofs",
                digest=str(proof_hash),
                suffix="policy_vm_stark_proof_v1.json",
                schema_version="policy_vm_stark_proof_v1",
            )
            candidate_program_id = str(proof_payload_peek.get("policy_program_id", "")).strip()
            if _is_sha256(candidate_program_id) and candidate_program_id in {str(row) for row in program_ids}:
                policy_program_id = candidate_program_id
            else:
                fail_v18("INPUTS_DESCRIPTOR_MISMATCH")
        if policy_program_id is None:
            fail_v18("SCHEMA_FAIL")
        expected = {
            "inputs_descriptor_hash": inputs_hash,
            "policy_program_id": policy_program_id,
            "opcode_table_id": descriptor_payload.get("opcode_table_id"),
            "decision_plan_hash": decision_hash,
            "decision_payload": decision_payload,
        }
        if isinstance(trace_payload, dict):
            expected["trace_payload"] = trace_payload
            expected["steps_executed_u64"] = int(trace_payload.get("steps_executed_u64", 0))
            expected["budget_outcome_hash"] = canon_hash_obj(trace_payload.get("budget_outcome", {}))
        if proof_assets:
            expected.update(proof_assets)
        proof_payload = _load_hash_bound_payload(
            dir_path=state_root / "policy" / "proofs",
            digest=str(proof_hash),
            suffix="policy_vm_stark_proof_v1.json",
            schema_version="policy_vm_stark_proof_v1",
        )
        try:
            verify_policy_vm_stark_proof(proof_payload, state_root=state_root, expected=expected)
            proof_valid = True
        except Exception:
            proof_valid = False

    mode = str(pack.get("policy_vm_mode", "DECISION_ONLY")).strip().upper()
    if mode in {"PROPOSAL_ONLY", "DUAL"} and snapshot.get("policy_market_selection_hash") is not None:
        _verify_policy_market_replay(
            state_root=state_root,
            config_dir=config_dir,
            pack=pack,
            descriptor_payload=descriptor_payload,
            descriptor_hash=str(inputs_hash),
            decision_payload=decision_payload,
            snapshot=snapshot,
            assets=assets,
        )
    else:
        _verify_decision_only_vm_replay(
            state_root=state_root,
            config_dir=config_dir,
            pack=pack,
            descriptor_payload=descriptor_payload,
            descriptor_hash=str(inputs_hash),
            decision_payload=decision_payload,
            snapshot=snapshot,
            assets=assets,
            skip_vm_replay=proof_valid,
        )


def _verify_epistemic_path(state_root: Path, snapshot: dict[str, Any]) -> None:
    ledger_rows = _ledger_rows(state_root)
    capsule_event_rows = [row for row in ledger_rows if str(row.get("event_type", "")) == "EPISTEMIC_CAPSULE_V1"]
    capsule_rows = sorted(
        (state_root / "epistemic" / "capsules").glob("sha256_*.epistemic_capsule_v1.json"),
        key=lambda p: p.as_posix(),
    )
    # Epistemic market events can exist without capsule production.
    # Capsule checks are only mandatory when capsule events/artifacts are present.
    if not capsule_event_rows and not capsule_rows:
        return
    if capsule_rows and not capsule_event_rows:
        fail_v18("NONDETERMINISTIC")
    if capsule_event_rows and not capsule_rows:
        fail_v18("MISSING_STATE_INPUT")

    try:
        summary = verify_capsule_bundle(state_root)
    except Exception as exc:  # noqa: BLE001
        _rethrow_as_v18(exc)
        return
    expected = {
        "capsule_id": str(summary.get("capsule_id", "")),
        "world_snapshot_id": str(summary.get("world_snapshot_id", "")),
        "world_root": str(summary.get("world_root", "")),
        "sip_receipt_id": str(summary.get("sip_receipt_id", "")),
        "distillate_graph_id": str(summary.get("distillate_graph_id", "")),
        "strip_receipt_id": str(summary.get("strip_receipt_id", "")),
        "episode_id": str(summary.get("episode_id", "")),
    }

    def _load_by_id(*, dir_path: Path, suffix: str, schema_version: str, id_field: str, expected_id: str) -> dict[str, Any]:
        rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix())
        match: dict[str, Any] | None = None
        for path in rows:
            payload = _load_canon_json(path)
            if str(payload.get("schema_version", "")).strip() != schema_version:
                fail_v18("SCHEMA_FAIL")
            if canon_hash_obj(payload) != "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]:
                fail_v18("NONDETERMINISTIC")
            declared_id = str(payload.get(id_field, "")).strip()
            if declared_id:
                no_id = dict(payload)
                no_id.pop(id_field, None)
                if canon_hash_obj(no_id) != declared_id:
                    fail_v18("NONDETERMINISTIC")
            if declared_id == expected_id:
                if match is not None:
                    fail_v18("NONDETERMINISTIC")
                match = payload
        if match is None:
            fail_v18("MISSING_STATE_INPUT")
        return match

    capsule_payload = _load_by_id(
        dir_path=state_root / "epistemic" / "capsules",
        suffix="epistemic_capsule_v1.json",
        schema_version="epistemic_capsule_v1",
        id_field="capsule_id",
        expected_id=str(expected["capsule_id"]),
    )
    graph_payload = _load_by_id(
        dir_path=state_root / "epistemic" / "graphs",
        suffix="qxwmr_graph_v1.json",
        schema_version="qxwmr_graph_v1",
        id_field="graph_id",
        expected_id=str(expected["distillate_graph_id"]),
    )
    usable_b = bool(capsule_payload.get("usable_b"))
    cert_gate_status = str(capsule_payload.get("cert_gate_status", "")).strip().upper()
    if cert_gate_status not in {"PASS", "WARN", "BLOCKED"}:
        fail_v18("SCHEMA_FAIL")
    capsule_cert_profile_id_raw = capsule_payload.get("cert_profile_id")
    capsule_cert_profile_id = (
        str(capsule_cert_profile_id_raw).strip()
        if isinstance(capsule_cert_profile_id_raw, str) and capsule_cert_profile_id_raw.strip()
        else ("sha256:" + ("0" * 64))
    )
    if not _is_sha256(capsule_cert_profile_id):
        fail_v18("SCHEMA_FAIL")

    _ = load_usable_rows(state_root)
    usable_capsule_ids = load_usable_capsule_ids(state_root)
    usable_graph_ids = load_usable_graph_ids(state_root)
    if usable_b:
        if str(expected["capsule_id"]) not in usable_capsule_ids:
            fail_v18("CERT_GATE_FAIL")
        if str(expected["distillate_graph_id"]) not in usable_graph_ids:
            fail_v18("CERT_GATE_FAIL")
    else:
        if str(expected["capsule_id"]) in usable_capsule_ids:
            fail_v18("CERT_GATE_FAIL")
        if str(expected["distillate_graph_id"]) in usable_graph_ids:
            fail_v18("CERT_GATE_FAIL")

    cert_gate_mode = "OFF"
    cert_gate_objective_profile_id = "sha256:" + ("0" * 64)
    cert_gate_profile_id = "sha256:" + ("0" * 64)
    cert_gate_rows = sorted(
        (state_root / "epistemic" / "contracts").glob("sha256_*.epistemic_cert_gate_binding_v1.json"),
        key=lambda p: p.as_posix(),
    )
    if not cert_gate_rows:
        cert_gate_rows = sorted(
            (state_root / "epistemic" / "replay_inputs" / "contracts").glob("sha256_*.epistemic_cert_gate_binding_v1.json"),
            key=lambda p: p.as_posix(),
        )
    if len(cert_gate_rows) > 1:
        fail_v18("NONDETERMINISTIC")
    if cert_gate_rows:
        cert_gate_payload = _load_canon_json(cert_gate_rows[0])
        if canon_hash_obj(cert_gate_payload) != "sha256:" + cert_gate_rows[0].name.split(".", 1)[0].split("_", 1)[1]:
            fail_v18("NONDETERMINISTIC")
        if str(cert_gate_payload.get("schema_version", "")) != "epistemic_cert_gate_binding_v1":
            fail_v18("SCHEMA_FAIL")
        cert_gate_mode = str(cert_gate_payload.get("cert_gate_mode", "OFF")).strip().upper()
        if cert_gate_mode not in {"OFF", "WARN", "ENFORCE"}:
            fail_v18("SCHEMA_FAIL")
        cert_gate_objective_profile_id = str(cert_gate_payload.get("objective_profile_id", "")).strip()
        cert_gate_profile_id = str(cert_gate_payload.get("cert_profile_id", cert_gate_profile_id)).strip() or cert_gate_profile_id
        if not _is_sha256(cert_gate_objective_profile_id) or not _is_sha256(cert_gate_profile_id):
            fail_v18("SCHEMA_FAIL")
    if cert_gate_mode != "OFF" and cert_gate_profile_id != capsule_cert_profile_id:
        fail_v18("CERT_GATE_FAIL")

    seen_capsules: set[str] = set()
    matched_expected_capsule_b = False
    for row in capsule_event_rows:
        artifact_hash = str(row.get("artifact_hash", "")).strip()
        if not _is_sha256(artifact_hash):
            fail_v18("SCHEMA_FAIL")
        payload = _load_hash_bound_payload(
            dir_path=state_root / "ledger" / "epistemic",
            digest=artifact_hash,
            suffix="omega_event_epistemic_capsule_v1.json",
            schema_version="v19_0",
        )
        if str(payload.get("schema_name", "")) != "omega_event_epistemic_capsule_v1":
            fail_v18("SCHEMA_FAIL")
        validate_schema_v19(payload, "omega_event_epistemic_capsule_v1")
        capsule_id = str(payload.get("capsule_id", ""))
        if capsule_id in seen_capsules:
            fail_v18("NONDETERMINISTIC")
        seen_capsules.add(capsule_id)
        if capsule_id == str(expected.get("capsule_id", "")):
            matched_expected_capsule_b = True
            for key in ("capsule_id", "world_snapshot_id", "world_root", "sip_receipt_id", "distillate_graph_id", "episode_id"):
                if str(payload.get(key, "")) != str(expected.get(key, "")):
                    fail_v18("NONDETERMINISTIC")
    if not matched_expected_capsule_b:
        fail_v18("MISSING_STATE_INPUT")

    artifact_events: dict[str, list[str]] = {}
    for row in ledger_rows:
        event_type = str(row.get("event_type", ""))
        artifact_hash = str(row.get("artifact_hash", "")).strip()
        if not _is_sha256(artifact_hash):
            fail_v18("SCHEMA_FAIL")
        artifact_events.setdefault(event_type, []).append(artifact_hash)
    optional_event_specs: dict[str, tuple[Path, str, str]] = {
        "EPISTEMIC_TYPE_REGISTRY_V1": (state_root / "epistemic" / "type_registry", "epistemic_type_registry_v1.json", "epistemic_type_registry_v1"),
        "EPISTEMIC_TYPE_BINDING_V1": (state_root / "epistemic" / "type_bindings", "epistemic_type_binding_v1.json", "epistemic_type_binding_v1"),
        "EPISTEMIC_ECAC_V1": (state_root / "epistemic" / "certs", "epistemic_ecac_v1.json", "epistemic_ecac_v1"),
        "EPISTEMIC_EUFC_V1": (state_root / "epistemic" / "certs", "epistemic_eufc_v1.json", "epistemic_eufc_v1"),
        "EPISTEMIC_RETENTION_DELETION_PLAN_V1": (state_root / "epistemic" / "retention", "epistemic_deletion_plan_v1.json", "epistemic_deletion_plan_v1"),
        "EPISTEMIC_RETENTION_SAMPLING_MANIFEST_V1": (state_root / "epistemic" / "retention", "epistemic_sampling_manifest_v1.json", "epistemic_sampling_manifest_v1"),
        "EPISTEMIC_RETENTION_SUMMARY_PROOF_V1": (state_root / "epistemic" / "retention", "epistemic_summary_proof_v1.json", "epistemic_summary_proof_v1"),
        "EPISTEMIC_KERNEL_SPEC_V1": (state_root / "epistemic" / "kernels" / "specs", "epistemic_kernel_spec_v1.json", "epistemic_kernel_spec_v1"),
        "EPISTEMIC_ACTION_MARKET_INPUTS_V1": (
            state_root / "epistemic" / "market" / "actions" / "inputs",
            "epistemic_action_market_inputs_v1.json",
            "epistemic_action_market_inputs_v1",
        ),
        "EPISTEMIC_MARKET_SETTLEMENT_V1": (state_root / "epistemic" / "market", "epistemic_market_settlement_v1.json", "epistemic_market_settlement_v1"),
    }
    loaded_by_event: dict[str, dict[str, Any]] = {}
    for event_type, spec in optional_event_specs.items():
        hashes = artifact_events.get(event_type) or []
        if not hashes:
            continue
        dir_path, suffix, schema_version = spec
        payload = _load_hash_bound_payload(
            dir_path=dir_path,
            digest=str(hashes[-1]),
            suffix=suffix,
            schema_version=schema_version,
        )
        validate_schema_v19(payload, schema_version)
        loaded_by_event[event_type] = payload

    capsule_type_registry_id = capsule_payload.get("type_registry_id")
    capsule_type_binding_id = capsule_payload.get("type_binding_id")
    if (capsule_type_registry_id is None) != (capsule_type_binding_id is None):
        fail_v18("NONDETERMINISTIC")
    if capsule_type_registry_id is not None and capsule_type_binding_id is not None:
        if "EPISTEMIC_TYPE_REGISTRY_V1" not in loaded_by_event or "EPISTEMIC_TYPE_BINDING_V1" not in loaded_by_event:
            fail_v18("MISSING_STATE_INPUT")
        if str(loaded_by_event["EPISTEMIC_TYPE_REGISTRY_V1"].get("registry_id", "")) != str(capsule_type_registry_id):
            fail_v18("NONDETERMINISTIC")
        if str(loaded_by_event["EPISTEMIC_TYPE_BINDING_V1"].get("binding_id", "")) != str(capsule_type_binding_id):
            fail_v18("NONDETERMINISTIC")
        if str((loaded_by_event["EPISTEMIC_TYPE_BINDING_V1"]).get("graph_id", "")) != str(expected["distillate_graph_id"]):
            fail_v18("NONDETERMINISTIC")
        if str((loaded_by_event["EPISTEMIC_TYPE_BINDING_V1"]).get("type_registry_id", "")) != str(capsule_type_registry_id):
            fail_v18("NONDETERMINISTIC")
        graph_registry_id = graph_payload.get("type_registry_id")
        if graph_registry_id is not None and str(graph_registry_id) != str(capsule_type_registry_id):
            fail_v18("NONDETERMINISTIC")

    ecac_payload = loaded_by_event.get("EPISTEMIC_ECAC_V1")
    eufc_payload = loaded_by_event.get("EPISTEMIC_EUFC_V1")
    if (ecac_payload is None) != (eufc_payload is None):
        fail_v18("NONDETERMINISTIC")
    cert_valid = False
    cert_profile_payload: dict[str, Any] | None = None
    if ecac_payload is not None and eufc_payload is not None:
        if str(ecac_payload.get("capsule_id", "")) != str(expected["capsule_id"]):
            fail_v18("NONDETERMINISTIC")
        if str(eufc_payload.get("capsule_id", "")) != str(expected["capsule_id"]):
            fail_v18("NONDETERMINISTIC")
        if str(ecac_payload.get("graph_id", "")) != str(expected["distillate_graph_id"]):
            fail_v18("NONDETERMINISTIC")
        if str(eufc_payload.get("graph_id", "")) != str(expected["distillate_graph_id"]):
            fail_v18("NONDETERMINISTIC")
        if str(ecac_payload.get("strip_receipt_id", "")) != str(expected.get("strip_receipt_id", "")):
            fail_v18("NONDETERMINISTIC")
        if str(eufc_payload.get("strip_receipt_id", "")) != str(expected.get("strip_receipt_id", "")):
            fail_v18("NONDETERMINISTIC")
        if str(ecac_payload.get("objective_profile_id", "")) != str(eufc_payload.get("objective_profile_id", "")):
            fail_v18("NONDETERMINISTIC")
        if not _is_sha256(ecac_payload.get("cert_profile_id")) or not _is_sha256(eufc_payload.get("cert_profile_id")):
            fail_v18("SCHEMA_FAIL")
        if str(ecac_payload.get("cert_profile_id", "")) != str(eufc_payload.get("cert_profile_id", "")):
            fail_v18("NONDETERMINISTIC")
        if list(ecac_payload.get("task_input_ids") or []) != list(eufc_payload.get("task_input_ids") or []):
            fail_v18("NONDETERMINISTIC")
        if str(ecac_payload.get("cert_profile_id", "")) != str(capsule_cert_profile_id):
            fail_v18("CERT_GATE_FAIL")
        type_binding_payload = _load_by_id(
            dir_path=state_root / "epistemic" / "type_bindings",
            suffix="epistemic_type_binding_v1.json",
            schema_version="epistemic_type_binding_v1",
            id_field="binding_id",
            expected_id=str(ecac_payload.get("type_binding_id", "")),
        )
        if cert_gate_mode != "OFF":
            if str(ecac_payload.get("objective_profile_id", "")) != cert_gate_objective_profile_id:
                fail_v18("CERT_GATE_FAIL")
            if str(ecac_payload.get("cert_profile_id", "")) != cert_gate_profile_id:
                fail_v18("CERT_GATE_FAIL")
        cert_profile_paths = sorted(
            (state_root / "epistemic" / "certs" / "profiles").glob("sha256_*.epistemic_cert_profile_v1.json"),
            key=lambda p: p.as_posix(),
        )
        if cert_profile_paths:
            matches: list[dict[str, Any]] = []
            for cert_profile_path in cert_profile_paths:
                payload = _load_canon_json(cert_profile_path)
                if canon_hash_obj(payload) != "sha256:" + cert_profile_path.name.split(".", 1)[0].split("_", 1)[1]:
                    fail_v18("NONDETERMINISTIC")
                validate_schema_v19(payload, "epistemic_cert_profile_v1")
                if str(payload.get("cert_profile_id", "")) == str(ecac_payload.get("cert_profile_id", "")):
                    matches.append(payload)
            if len(matches) > 1:
                fail_v18("NONDETERMINISTIC")
            if len(matches) == 1:
                cert_profile_payload = matches[0]
        try:
            eufc_credit_context: dict[str, Any] | None = None
            if isinstance(eufc_payload, dict):
                eufc_credit_context = {
                    "credited_credit_keys": list(eufc_payload.get("credited_credit_keys") or []),
                    "credit_window_mode": str(eufc_payload.get("credit_window_mode", "")),
                    "credit_window_open_tick_u64": int(eufc_payload.get("credit_window_open_tick_u64", 0)),
                    "credit_window_close_tick_u64": int(eufc_payload.get("credit_window_close_tick_u64", 0)),
                    "credit_window_receipt_ids": list(eufc_payload.get("credit_window_receipt_ids") or []),
                }
            verify_certs_bundle(
                capsule=capsule_payload,
                graph=graph_payload,
                type_binding=type_binding_payload,
                objective_profile_id=str(ecac_payload.get("objective_profile_id", "")),
                cert_profile=cert_profile_payload,
                ecac=ecac_payload,
                eufc=eufc_payload,
                eufc_credit_context=eufc_credit_context,
            )
        except Exception as exc:  # noqa: BLE001
            _rethrow_as_v18(exc)
        cert_valid = str(ecac_payload.get("status", "")) == "OK" and str(eufc_payload.get("status", "")) == "OK"

    if cert_gate_mode == "OFF":
        if not usable_b or cert_gate_status != "PASS":
            fail_v18("CERT_GATE_FAIL")
    elif cert_gate_mode == "ENFORCE":
        if cert_valid:
            if not usable_b or cert_gate_status != "PASS":
                fail_v18("CERT_GATE_FAIL")
        else:
            if usable_b or cert_gate_status != "BLOCKED":
                fail_v18("CERT_GATE_FAIL")
    else:  # WARN
        if cert_valid:
            if not usable_b or cert_gate_status != "PASS":
                fail_v18("CERT_GATE_FAIL")
        else:
            if not usable_b or cert_gate_status != "WARN":
                fail_v18("CERT_GATE_FAIL")

    for event_type in [
        "EPISTEMIC_RETENTION_DELETION_PLAN_V1",
        "EPISTEMIC_RETENTION_SAMPLING_MANIFEST_V1",
        "EPISTEMIC_RETENTION_SUMMARY_PROOF_V1",
    ]:
        payload = loaded_by_event.get(event_type)
        if payload is None:
            continue
        if str(payload.get("capsule_id", "")) != str(expected["capsule_id"]):
            fail_v18("NONDETERMINISTIC")

    market_payload = loaded_by_event.get("EPISTEMIC_MARKET_SETTLEMENT_V1")
    if market_payload is not None:
        has_legacy_bid_receipts = _is_sha256(snapshot.get("bid_selection_receipt_hash")) and _is_sha256(
            snapshot.get("bid_settlement_receipt_hash")
        )
        market_inputs_payload = loaded_by_event.get("EPISTEMIC_ACTION_MARKET_INPUTS_V1")
        if market_inputs_payload is None:
            fail_v18("MISSING_STATE_INPUT")
        if str(market_payload.get("inputs_manifest_id", "")) != str(market_inputs_payload.get("inputs_manifest_id", "")):
            fail_v18("NONDETERMINISTIC")
        if has_legacy_bid_receipts:
            if str(market_payload.get("bid_selection_receipt_hash", "")) != str(snapshot.get("bid_selection_receipt_hash")):
                fail_v18("NONDETERMINISTIC")
            if str(market_payload.get("bid_settlement_receipt_hash", "")) != str(snapshot.get("bid_settlement_receipt_hash")):
                fail_v18("NONDETERMINISTIC")
            selection_payload = _load_hash_bound_payload(
                dir_path=state_root / "market" / "selection",
                digest=str(snapshot.get("bid_selection_receipt_hash")),
                suffix="bid_selection_receipt_v1.json",
                schema_version="bid_selection_receipt_v1",
            )
            settlement_payload = _load_hash_bound_payload(
                dir_path=state_root / "market" / "settlement",
                digest=str(snapshot.get("bid_settlement_receipt_hash")),
                suffix="bid_settlement_receipt_v1.json",
                schema_version="bid_settlement_receipt_v1",
            )
            if str(settlement_payload.get("winner_campaign_id", "")) != str(market_payload.get("winner_campaign_id", "")):
                fail_v18("NONDETERMINISTIC")
            winner = selection_payload.get("winner")
            if isinstance(winner, dict):
                if str(winner.get("campaign_id", "")) != str(market_payload.get("winner_campaign_id", "")):
                    fail_v18("NONDETERMINISTIC")
        else:
            zero_hash = "sha256:" + ("0" * 64)
            if str(market_payload.get("bid_selection_receipt_hash", "")) != zero_hash:
                fail_v18("NONDETERMINISTIC")
            if str(market_payload.get("bid_settlement_receipt_hash", "")) != zero_hash:
                fail_v18("NONDETERMINISTIC")
        capsule_id = market_payload.get("capsule_id")
        if capsule_id is not None:
            if str(capsule_id) != str(expected["capsule_id"]):
                fail_v18("NONDETERMINISTIC")
        ecac_id = market_payload.get("ecac_id")
        eufc_id = market_payload.get("eufc_id")
        if ecac_id is not None:
            if ecac_payload is None or str(ecac_payload.get("ecac_id", "")) != str(ecac_id):
                fail_v18("NONDETERMINISTIC")
        if eufc_id is not None:
            if eufc_payload is None or str(eufc_payload.get("eufc_id", "")) != str(eufc_id):
                fail_v18("NONDETERMINISTIC")

        action_bid_set_hash = market_payload.get("action_bid_set_hash")
        action_selection_hash = market_payload.get("action_selection_receipt_hash")
        action_settlement_hash = market_payload.get("action_settlement_receipt_hash")
        if not (_is_sha256(action_bid_set_hash) and _is_sha256(action_selection_hash) and _is_sha256(action_settlement_hash)):
            fail_v18("MISSING_STATE_INPUT")

        action_bid_set_payload = _load_hash_bound_payload(
            dir_path=state_root / "epistemic" / "market" / "actions" / "bid_sets",
            digest=str(action_bid_set_hash),
            suffix="epistemic_action_bid_set_v1.json",
            schema_version="epistemic_action_bid_set_v1",
        )
        action_selection_payload = _load_hash_bound_payload(
            dir_path=state_root / "epistemic" / "market" / "actions" / "selection",
            digest=str(action_selection_hash),
            suffix="epistemic_action_selection_receipt_v1.json",
            schema_version="epistemic_action_selection_receipt_v1",
        )
        action_settlement_payload = _load_hash_bound_payload(
            dir_path=state_root / "epistemic" / "market" / "actions" / "settlement",
            digest=str(action_settlement_hash),
            suffix="epistemic_action_settlement_receipt_v1.json",
            schema_version="epistemic_action_settlement_receipt_v1",
        )
        if str(action_bid_set_payload.get("inputs_manifest_id", "")) != str(market_inputs_payload.get("inputs_manifest_id", "")):
            fail_v18("NONDETERMINISTIC")
        if str(action_selection_payload.get("inputs_manifest_id", "")) != str(market_inputs_payload.get("inputs_manifest_id", "")):
            fail_v18("NONDETERMINISTIC")
        if str(action_settlement_payload.get("inputs_manifest_id", "")) != str(market_inputs_payload.get("inputs_manifest_id", "")):
            fail_v18("NONDETERMINISTIC")

        action_profile_id = str(market_inputs_payload.get("market_profile_id", "")).strip()
        if not _is_sha256(action_profile_id):
            fail_v18("SCHEMA_FAIL")
        action_profile_rows = sorted(
            (state_root / "epistemic" / "market" / "actions" / "profiles").glob("sha256_*.epistemic_action_market_profile_v1.json"),
            key=lambda p: p.as_posix(),
        )
        action_profile_payload = None
        for row in action_profile_rows:
            payload = _load_canon_json(row)
            if canon_hash_obj(payload) != "sha256:" + row.name.split(".", 1)[0].split("_", 1)[1]:
                fail_v18("NONDETERMINISTIC")
            validate_schema_v19(payload, "epistemic_action_market_profile_v1")
            if str(payload.get("profile_id", "")) == action_profile_id:
                if action_profile_payload is not None:
                    fail_v18("NONDETERMINISTIC")
                action_profile_payload = payload
        if action_profile_payload is None:
            default_profile = build_default_action_market_profile()
            if str(default_profile.get("profile_id", "")) != action_profile_id:
                fail_v18("MISSING_STATE_INPUT")
            action_profile_payload = default_profile

        bid_rows_all = sorted(
            (state_root / "epistemic" / "market" / "actions" / "bids").glob("sha256_*.epistemic_action_bid_v1.json"),
            key=lambda p: p.as_posix(),
        )
        observed_action_bids: list[dict[str, Any]] = []
        for row in bid_rows_all:
            payload = _load_canon_json(row)
            if canon_hash_obj(payload) != "sha256:" + row.name.split(".", 1)[0].split("_", 1)[1]:
                fail_v18("NONDETERMINISTIC")
            validate_schema_v19(payload, "epistemic_action_bid_v1")
            if str(payload.get("inputs_manifest_id", "")) != str(market_inputs_payload.get("inputs_manifest_id", "")):
                continue
            observed_action_bids.append(payload)
        if not observed_action_bids:
            fail_v18("MISSING_STATE_INPUT")
        try:
            verify_action_market_replay(
                inputs_manifest=market_inputs_payload,
                market_profile=action_profile_payload,
                observed_bids=observed_action_bids,
                observed_bid_set=action_bid_set_payload,
                observed_selection=action_selection_payload,
                observed_settlement=action_settlement_payload,
                produced_capsule_id=(str(market_payload.get("capsule_id", "")).strip() or None),
            )
        except Exception as exc:  # noqa: BLE001
            _rethrow_as_v18(exc)
        if eufc_payload is not None:
            credit_key = action_settlement_payload.get("credit_key")
            if credit_key is not None:
                credited_keys = list(eufc_payload.get("credited_credit_keys") or [])
                if credited_keys:
                    if str(eufc_payload.get("credit_window_mode", "")) != "EUFC_WINDOW":
                        fail_v18("NONDETERMINISTIC")
                    if int(eufc_payload.get("credit_window_open_tick_u64", -1)) != int(market_inputs_payload.get("eufc_window_open_tick_u64", -2)):
                        fail_v18("NONDETERMINISTIC")
                    if int(eufc_payload.get("credit_window_close_tick_u64", -1)) != int(market_inputs_payload.get("eufc_window_close_tick_u64", -2)):
                        fail_v18("NONDETERMINISTIC")
                    if list(eufc_payload.get("credit_window_receipt_ids") or []) != list(market_inputs_payload.get("eufc_window_receipt_ids") or []):
                        fail_v18("NONDETERMINISTIC")
                    if credited_keys.count(str(credit_key)) != 1:
                        fail_v18("NONDETERMINISTIC")

    compaction_execution_paths = sorted(
        (state_root / "epistemic" / "retention").glob("sha256_*.epistemic_compaction_execution_receipt_v1.json"),
        key=lambda p: p.as_posix(),
    )
    for execution_path in compaction_execution_paths:
        execution_payload = _load_canon_json(execution_path)
        if canon_hash_obj(execution_payload) != "sha256:" + execution_path.name.split(".", 1)[0].split("_", 1)[1]:
            fail_v18("NONDETERMINISTIC")
        validate_schema_v19(execution_payload, "epistemic_compaction_execution_receipt_v1")

        witness_paths = sorted(
            (state_root / "epistemic" / "retention").glob("sha256_*.epistemic_compaction_witness_v1.json"),
            key=lambda p: p.as_posix(),
        )
        if not witness_paths:
            fail_v18("MISSING_STATE_INPUT")
        witness_payload = None
        for witness_path in witness_paths:
            candidate = _load_canon_json(witness_path)
            if canon_hash_obj(candidate) != "sha256:" + witness_path.name.split(".", 1)[0].split("_", 1)[1]:
                fail_v18("NONDETERMINISTIC")
            validate_schema_v19(candidate, "epistemic_compaction_witness_v1")
            if int(candidate.get("replay_floor_tick_u64", -1)) != int(execution_payload.get("replay_floor_tick_u64", -2)):
                continue
            witness_payload = candidate
            break
        if witness_payload is None:
            fail_v18("MISSING_STATE_INPUT")

        pack_payload = _load_by_id(
            dir_path=state_root / "epistemic" / "retention",
            suffix="epistemic_compaction_pack_manifest_v1.json",
            schema_version="epistemic_compaction_pack_manifest_v1",
            id_field="pack_manifest_id",
            expected_id=str(execution_payload.get("pack_manifest_id", "")),
        )
        mapping_payload = _load_by_id(
            dir_path=state_root / "epistemic" / "retention",
            suffix="epistemic_compaction_mapping_manifest_v1.json",
            schema_version="epistemic_compaction_mapping_manifest_v1",
            id_field="mapping_manifest_id",
            expected_id=str(execution_payload.get("mapping_manifest_id", "")),
        )
        tombstone_payload = _load_by_id(
            dir_path=state_root / "epistemic" / "retention",
            suffix="epistemic_compaction_tombstone_manifest_v1.json",
            schema_version="epistemic_compaction_tombstone_manifest_v1",
            id_field="tombstone_manifest_id",
            expected_id=str(execution_payload.get("tombstone_manifest_id", "")),
        )
        try:
            verify_compaction_bundle(
                state_root=state_root,
                execution_receipt=execution_payload,
                witness=witness_payload,
                pack_manifest=pack_payload,
                mapping_manifest=mapping_payload,
                tombstone_manifest=tombstone_payload,
            )
        except Exception as exc:  # noqa: BLE001
            _rethrow_as_v18(exc)


def _latest_tick_outcome_or_fail(perf_dir: Path) -> dict[str, Any]:
    rows = sorted(perf_dir.glob("sha256_*.omega_tick_outcome_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        fail_v18("MISSING_STATE_INPUT")
    best_payload: dict[str, Any] | None = None
    best_tick = -1
    for row in rows:
        payload = _load_canon_json(row)
        tick = int(payload.get("tick_u64", -1))
        if tick > best_tick:
            best_tick = tick
            best_payload = payload
    if best_payload is None:
        fail_v18("MISSING_STATE_INPUT")
    return best_payload


def _load_optional_utility_policy(*, config_dir: Path) -> dict[str, Any] | None:
    profile_path = config_dir / "long_run_profile_v1.json"
    if not profile_path.exists() or not profile_path.is_file():
        return None
    profile_payload = _load_canon_json(profile_path)
    try:
        validate_schema_v19(profile_payload, "long_run_profile_v1")
    except Exception:
        return None
    profile_id = str(profile_payload.get("profile_id", "")).strip()
    profile_no_id = dict(profile_payload)
    profile_no_id.pop("profile_id", None)
    if _is_sha256(profile_id) and canon_hash_obj(profile_no_id) != profile_id:
        fail_v18("PIN_HASH_MISMATCH")
    rel = str(profile_payload.get("utility_policy_rel", "")).strip()
    declared_id = str(profile_payload.get("utility_policy_id", "")).strip()
    if not rel and not declared_id:
        return None
    if bool(rel) != bool(declared_id):
        fail_v18("SCHEMA_FAIL")
    rel_path = Path(rel)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        fail_v18("SCHEMA_FAIL")
    path = config_dir / rel_path
    if not path.exists() or not path.is_file():
        fail_v18("MISSING_STATE_INPUT")
    payload = _load_canon_json(path)
    validate_schema_v19(payload, "utility_policy_v1")
    observed_id = _require_sha256(payload.get("policy_id"), reason="PIN_HASH_MISMATCH")
    payload_no_id = dict(payload)
    payload_no_id.pop("policy_id", None)
    if canon_hash_obj(payload_no_id) != observed_id:
        fail_v18("PIN_HASH_MISMATCH")
    if observed_id != _require_sha256(declared_id, reason="PIN_HASH_MISMATCH"):
        fail_v18("PIN_HASH_MISMATCH")
    return payload


def _verify_runtime_stats_derivation(*, state_root: Path, utility_policy: dict[str, Any] | None) -> None:
    native_dir = state_root / "ledger" / "native"
    rows = sorted(native_dir.glob("sha256_*.omega_native_runtime_stats_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        fail_v18("MISSING_STATE_INPUT")
    payload = _load_canon_json(rows[-1])
    if canon_hash_obj(payload) != "sha256:" + rows[-1].name.split(".", 1)[0].split("_", 1)[1]:
        fail_v18("NONDETERMINISTIC")
    if str(payload.get("schema_version", "")).strip() != "omega_native_runtime_stats_v1":
        fail_v18("SCHEMA_FAIL")
    if str(payload.get("work_units_formula_id", "")).strip() != WORK_UNITS_FORMULA_ID:
        fail_v18("NONDETERMINISTIC")
    expected_source_id = None
    if isinstance(utility_policy, dict):
        expected_source_id = str(utility_policy.get("runtime_stats_source_id", "")).strip() or None
    observed_source_id = str(payload.get("runtime_stats_source_id", "")).strip()
    if expected_source_id is not None and observed_source_id != expected_source_id:
        fail_v18("NONDETERMINISTIC")
    ops = payload.get("ops")
    if not isinstance(ops, list):
        fail_v18("SCHEMA_FAIL")
    recomputed_rows: list[dict[str, Any]] = []
    for row in ops:
        if not isinstance(row, dict):
            fail_v18("SCHEMA_FAIL")
        recomputed = int(derive_work_units_from_row(row))
        observed = int(row.get("work_units_u64", -1))
        if recomputed != observed:
            fail_v18("NONDETERMINISTIC")
        recomputed_rows.append(dict(row))
    recomputed_total = int(derive_total_work_units(recomputed_rows))
    if recomputed_total != int(payload.get("total_work_units_u64", -1)):
        fail_v18("NONDETERMINISTIC")


def _frontier_attempt_evidence_satisfied(
    *,
    state_root: Path,
    snapshot: dict[str, Any],
    tick_outcome: dict[str, Any],
    declared_class_tick: str,
    lane_name: str | None,
    candidate_bundle_present_b: bool,
) -> bool:
    action_kind = str(tick_outcome.get("action_kind", "")).strip()
    if action_kind not in {"RUN_CAMPAIGN", "RUN_GOAL_TASK", "SAFE_HALT"}:
        return False
    is_frontier_lane = str(lane_name or "").strip().upper() == "FRONTIER"
    if str(declared_class_tick).strip() not in _HEAVY_DECLARED_CLASSES and not is_frontier_lane:
        return False

    dispatch_hash = snapshot.get("dispatch_receipt_hash")
    subverifier_hash = snapshot.get("subverifier_receipt_hash")
    if not _is_sha256(dispatch_hash) or not _is_sha256(subverifier_hash):
        return False

    dispatch_path = _find_nested_hash(state_root, str(dispatch_hash), "omega_dispatch_receipt_v1.json")
    dispatch_payload = _load_canon_json(dispatch_path)
    if canon_hash_obj(dispatch_payload) != str(dispatch_hash):
        fail_v18("NONDETERMINISTIC")
    validate_schema_v18(dispatch_payload, "omega_dispatch_receipt_v1")

    subverifier_path = _find_nested_hash(state_root, str(subverifier_hash), "omega_subverifier_receipt_v1.json")
    subverifier_payload = _load_canon_json(subverifier_path)
    if canon_hash_obj(subverifier_payload) != str(subverifier_hash):
        fail_v18("NONDETERMINISTIC")
    validate_schema_v18(subverifier_payload, "omega_subverifier_receipt_v1")

    dispatch_tick = int(max(0, int(dispatch_payload.get("tick_u64", -1))))
    sub_tick = int(max(0, int(subverifier_payload.get("tick_u64", -1))))
    if dispatch_tick != sub_tick:
        return False

    dispatch_campaign = str(dispatch_payload.get("campaign_id", "")).strip()
    sub_campaign = str(subverifier_payload.get("campaign_id", "")).strip()
    if not dispatch_campaign or not sub_campaign or dispatch_campaign != sub_campaign:
        return False

    sub_status = str(((subverifier_payload.get("result") or {}).get("status", ""))).strip().upper()
    if sub_status not in {"VALID", "INVALID"}:
        return False
    return True


def _expected_routing_selector_id(
    *,
    forced_frontier_attempt_b: bool,
    reason_codes: list[str],
    market_selection_in_play_b: bool,
) -> str:
    reason_set = {str(row).strip() for row in reason_codes if str(row).strip()}
    if bool(forced_frontier_attempt_b):
        return "HARD_LOCK_OVERRIDE"
    if "SCAFFOLDING_ALLOWED" in reason_set:
        return "SCAFFOLD_OVERRIDE"
    if bool(market_selection_in_play_b):
        return "MARKET"
    return "NON_MARKET"


def _verify_candidate_precheck_for_dispatch(*, state_root: Path, dispatch_payload: dict[str, Any]) -> None:
    campaign_id = str(dispatch_payload.get("campaign_id", "")).strip()
    if campaign_id != _GE_SH1_CAMPAIGN_ID:
        return
    # Failed campaign invocations can terminate before candidate precheck emission.
    # Only require precheck receipts for successful dispatch executions.
    try:
        return_code = int(dispatch_payload.get("return_code"))
    except Exception:
        fail_v18("SCHEMA_FAIL")
    if return_code != 0:
        return
    subrun = dispatch_payload.get("subrun")
    if not isinstance(subrun, dict):
        fail_v18("SCHEMA_FAIL")
    subrun_root_rel = str(subrun.get("subrun_root_rel", "")).strip()
    if not subrun_root_rel:
        fail_v18("SCHEMA_FAIL")
    rel = Path(subrun_root_rel)
    if rel.is_absolute() or ".." in rel.parts:
        fail_v18("SCHEMA_FAIL")
    axis_gate_decision_payload = _load_axis_gate_decision_for_dispatch(
        state_root=state_root,
        subrun_root_rel=subrun_root_rel,
    )
    precheck_dir = state_root / rel / "precheck"
    rows = sorted(precheck_dir.glob("sha256_*.candidate_precheck_receipt_v1.json"), key=lambda row: row.as_posix())
    if not rows:
        fail_v18("MISSING_STATE_INPUT")
    payload = _load_canon_json(rows[-1])

    digest = canon_hash_obj(payload)
    expected_name = f"sha256_{digest.split(':', 1)[1]}.candidate_precheck_receipt_v1.json"
    if rows[-1].name != expected_name:
        fail_v18("NONDETERMINISTIC")

    receipt_id = _require_sha256(payload.get("receipt_id"), reason="NONDETERMINISTIC")
    payload_no_id = dict(payload)
    payload_no_id.pop("receipt_id", None)
    if canon_hash_obj(payload_no_id) != receipt_id:
        fail_v18("NONDETERMINISTIC")

    # Backward compatibility: older receipts may not carry archetype/cert fields.
    payload_for_validation = dict(payload)
    normalized_candidates: list[Any] = []
    raw_candidates = payload_for_validation.get("candidates")
    if isinstance(raw_candidates, list):
        for row in raw_candidates:
            if isinstance(row, dict):
                row_norm = dict(row)
                row_norm.setdefault("archetype_id", None)
                row_norm.setdefault("nontriviality_cert_v1", None)
                normalized_candidates.append(row_norm)
            else:
                normalized_candidates.append(row)
        payload_for_validation["candidates"] = normalized_candidates
    forced_heavy_context = payload_for_validation.get("forced_heavy_context_v1")
    forced_heavy_wiring_locus_relpath: str | None = None
    if isinstance(forced_heavy_context, dict):
        context_norm = dict(forced_heavy_context)
        wiring_locus_raw = context_norm.get("wiring_locus_relpath")
        if isinstance(wiring_locus_raw, str) and wiring_locus_raw.strip():
            forced_heavy_wiring_locus_relpath = _canonical_axis_gate_relpath(wiring_locus_raw)
        context_norm.setdefault(
            "expected_wiring_delta_v1",
            {"require_call_edges": False, "require_control_flow": False, "require_data_flow": False},
        )
        final_rows = context_norm.get("final_candidate_rows_v1")
        normalized_final_rows: list[Any] = []
        if isinstance(final_rows, list):
            for row in final_rows:
                if isinstance(row, dict):
                    row_norm = dict(row)
                    row_norm.setdefault(
                        "expected_wiring_delta_v1",
                        {"require_call_edges": False, "require_control_flow": False, "require_data_flow": False},
                    )
                    row_norm.setdefault(
                        "observed_wiring_delta_v1",
                        {
                            "wiring_class_ok_b": None,
                            "call_edges_changed_b": None,
                            "control_flow_changed_b": None,
                            "data_flow_changed_b": None,
                            "failed_threshold_code": None,
                        },
                    )
                    row_norm.setdefault("predicted_hard_task_delta_q32", None)
                    row_norm.setdefault("predicted_hard_task_baseline_score_q32", None)
                    row_norm.setdefault("predicted_hard_task_patched_score_q32", None)
                    normalized_final_rows.append(row_norm)
                else:
                    normalized_final_rows.append(row)
            context_norm["final_candidate_rows_v1"] = normalized_final_rows
        payload_for_validation["forced_heavy_context_v1"] = context_norm
    validate_schema_v19(payload_for_validation, "candidate_precheck_receipt_v1")

    if not bool(payload.get("dispatch_happened_b", False)):
        fail_v18("NONDETERMINISTIC")

    invocation = dispatch_payload.get("invocation")
    if not isinstance(invocation, dict):
        fail_v18("SCHEMA_FAIL")
    raw_env_overrides = invocation.get("env_overrides")
    env_overrides: dict[str, str] = {}
    if raw_env_overrides is not None:
        if not isinstance(raw_env_overrides, dict):
            fail_v18("SCHEMA_FAIL")
        env_overrides = {str(k): str(v) for k, v in raw_env_overrides.items()}
    forced_heavy_claimed_b = str(env_overrides.get("OMEGA_SH1_FORCED_HEAVY_B", "")).strip() == "1"

    candidates = payload_for_validation.get("candidates")
    if not isinstance(candidates, list):
        fail_v18("SCHEMA_FAIL")
    if int(payload_for_validation.get("candidate_count_u32", -1)) != len(candidates):
        fail_v18("NONDETERMINISTIC")
    selected_for_ccap_touched_relpaths: list[str] = []
    for row in candidates:
        if not isinstance(row, dict):
            fail_v18("SCHEMA_FAIL")
        selected_for_ccap_b = bool(row.get("selected_for_ccap_b", False))
        decision = str(row.get("precheck_decision_code", "")).strip()
        if selected_for_ccap_b and decision != "SELECTED_FOR_CCAP":
            fail_v18("NONDETERMINISTIC")
        if (not selected_for_ccap_b) and decision == "SELECTED_FOR_CCAP":
            fail_v18("NONDETERMINISTIC")
        cert = row.get("nontriviality_cert_v1")
        cert_required_decisions = {
            "SELECTED_FOR_CCAP",
            "DROPPED_INSUFFICIENT_WIRING_DELTA",
            "DROPPED_FORCED_HEAVY_NO_WIRING_EVIDENCE",
            "DROPPED_FORCED_HEAVY_NONEXEMPT_TOUCH",
            "DROPPED_FORCED_HEAVY_PREDICTED_NO_HARD_GAIN",
            "DROPPED_REPEATED_FAILED_PATCH",
            "DROPPED_REPEATED_FAILED_SHAPE",
        }
        if decision in cert_required_decisions and not isinstance(cert, dict):
            fail_v18("NONDETERMINISTIC")
        if decision == "DROPPED_REPEATED_FAILED_SHAPE":
            shape_id = None if not isinstance(cert, dict) else cert.get("shape_id")
            if not _is_sha256(shape_id):
                fail_v18("NONDETERMINISTIC")
        if decision == "DROPPED_INSUFFICIENT_WIRING_DELTA" and isinstance(cert, dict):
            wiring_ok_b = bool(cert.get("wiring_class_ok_b", False))
            archetype_pass = cert.get("archetype_pass_b")
            if wiring_ok_b and (archetype_pass is not False):
                fail_v18("NONDETERMINISTIC")
        if decision == "DROPPED_FORCED_HEAVY_NO_WIRING_EVIDENCE" and isinstance(cert, dict):
            wiring_ok_b = bool(cert.get("wiring_class_ok_b", False))
            structural_present_b = bool(
                bool(cert.get("call_edges_changed_b", False))
                or bool(cert.get("control_flow_changed_b", False))
                or bool(cert.get("data_flow_changed_b", False))
            )
            if wiring_ok_b and structural_present_b:
                fail_v18("NONDETERMINISTIC")
        if decision == "DROPPED_FORCED_HEAVY_PREDICTED_NO_HARD_GAIN" and not forced_heavy_claimed_b:
            fail_v18("NONDETERMINISTIC")
        if decision == "DROPPED_FORCED_HEAVY_NONEXEMPT_TOUCH":
            if not forced_heavy_claimed_b:
                fail_v18("NONDETERMINISTIC")
            if forced_heavy_wiring_locus_relpath is None:
                fail_v18("NONDETERMINISTIC")
            touched_rows = _canonical_axis_gate_relpaths((cert or {}).get("touched_relpaths_v1"))
            if touched_rows and all(rel == forced_heavy_wiring_locus_relpath for rel in touched_rows):
                fail_v18("NONDETERMINISTIC")
        if forced_heavy_claimed_b and bool(row.get("selected_for_ccap_b", False)):
            target_relpaths = row.get("target_relpaths")
            if isinstance(target_relpaths, list):
                targets = [str(item).strip() for item in target_relpaths if str(item).strip()]
            else:
                targets = [str(row.get("target_relpath", "")).strip()]
            if not any(target.endswith(".py") for target in targets):
                fail_v18("FORCED_HEAVY_NONPY_TARGET")
            if forced_heavy_wiring_locus_relpath is not None:
                targets_canon = [_canonical_axis_gate_relpath(target) for target in targets]
                if any(target != forced_heavy_wiring_locus_relpath for target in targets_canon):
                    fail_v18("NONDETERMINISTIC")
        if forced_heavy_claimed_b and isinstance(cert, dict):
            touched_rows = _canonical_axis_gate_relpaths(cert.get("touched_relpaths_v1"))
            if touched_rows:
                if not any(rel.endswith(".py") for rel in touched_rows):
                    fail_v18("FORCED_HEAVY_NONPY_TOUCH")
                if selected_for_ccap_b:
                    selected_for_ccap_touched_relpaths = list(touched_rows)
                if selected_for_ccap_b and forced_heavy_wiring_locus_relpath is not None:
                    if any(rel != forced_heavy_wiring_locus_relpath for rel in touched_rows):
                        fail_v18("NONDETERMINISTIC")
            elif selected_for_ccap_b and forced_heavy_wiring_locus_relpath is not None:
                fail_v18("NONDETERMINISTIC")

    if forced_heavy_claimed_b and isinstance(axis_gate_decision_payload, dict):
        if bool(axis_gate_decision_payload.get("axis_gate_exempted_b", False)):
            exempt_set = _load_axis_gate_exemptions_set()
            checked_relpaths = _canonical_axis_gate_relpaths(axis_gate_decision_payload.get("axis_gate_checked_relpaths_v1"))
            if not checked_relpaths:
                checked_relpaths = list(selected_for_ccap_touched_relpaths)
            if any(rel not in exempt_set for rel in checked_relpaths):
                fail_v18("NONDETERMINISTIC")


def _verify_hardening_bindings(
    *,
    state_root: Path,
    config_dir: Path,
    snapshot: dict[str, Any],
    bandit_enabled_b: bool = False,
) -> None:
    utility_policy = _load_optional_utility_policy(config_dir=config_dir)
    _verify_runtime_stats_derivation(state_root=state_root, utility_policy=utility_policy)

    tick_outcome = _latest_tick_outcome_or_fail(state_root / "perf")

    promotion_payload: dict[str, Any] | None = None
    promo_hash = snapshot.get("promotion_receipt_hash")
    if _is_sha256(promo_hash):
        promotion_path = _find_nested_hash(state_root, str(promo_hash), "omega_promotion_receipt_v1.json")
        promotion_payload = _load_canon_json(promotion_path)
        if canon_hash_obj(promotion_payload) != str(promo_hash):
            fail_v18("NONDETERMINISTIC")

    utility_hash_snap = snapshot.get("utility_proof_hash")
    if utility_hash_snap is not None and not _is_sha256(utility_hash_snap):
        fail_v18("SCHEMA_FAIL")
    utility_hash_promo = None if promotion_payload is None else promotion_payload.get("utility_proof_hash")
    if utility_hash_promo is not None and not _is_sha256(utility_hash_promo):
        fail_v18("SCHEMA_FAIL")
    if utility_hash_snap != utility_hash_promo:
        if not (utility_hash_snap is None and utility_hash_promo is None):
            fail_v18("NONDETERMINISTIC")

    utility_payload: dict[str, Any] | None = None
    if _is_sha256(utility_hash_snap):
        utility_path = _find_nested_hash(state_root, str(utility_hash_snap), "utility_proof_receipt_v1.json")
        utility_payload = _load_canon_json(utility_path)
        if canon_hash_obj(utility_payload) != str(utility_hash_snap):
            fail_v18("NONDETERMINISTIC")
        validate_schema_v19(utility_payload, "utility_proof_receipt_v1")

    promotion_status = str(((promotion_payload or {}).get("result") or {}).get("status", "")).strip().upper()
    promotion_result_kind = str((promotion_payload or {}).get("result_kind", "")).strip().upper()
    promoted_ext_queued_b = promotion_status == "PROMOTED" and promotion_result_kind == "PROMOTED_EXT_QUEUED"
    bundle_hash = str((promotion_payload or {}).get("promotion_bundle_hash", "")).strip()
    candidate_bundle_present_b = False
    if (not promoted_ext_queued_b) and _is_sha256(bundle_hash) and bundle_hash != ("sha256:" + ("0" * 64)):
        bundle_path = _load_promotion_bundle_by_hash(state_root, bundle_hash)
        if bundle_path is None:
            fail_v18("MISSING_STATE_INPUT")
        bundle_payload = _load_canon_json(bundle_path)
        if canon_hash_obj(bundle_payload) != bundle_hash:
            fail_v18("NONDETERMINISTIC")
        candidate_bundle_present_b = True

    probe_executed_b = False
    if isinstance(utility_payload, dict):
        primary = utility_payload.get("primary_probe")
        stress = utility_payload.get("stress_probe")
        if (
            isinstance(primary, dict)
            and isinstance(stress, dict)
            and _is_sha256(primary.get("input_hash"))
            and _is_sha256(primary.get("output_hash"))
            and _is_sha256(stress.get("input_hash"))
            and _is_sha256(stress.get("output_hash"))
            and _is_sha256(utility_payload.get("baseline_ref_hash"))
            and _is_sha256(utility_payload.get("candidate_bundle_hash"))
            and str(utility_payload.get("probe_suite_id", "")).strip()
            and str(utility_payload.get("stress_probe_suite_id", "")).strip()
        ):
            probe_executed_b = True
        if bool(utility_payload.get("candidate_bundle_present_b", False)) != bool(candidate_bundle_present_b):
            fail_v18("NONDETERMINISTIC")
        if bool(utility_payload.get("probe_executed_b", False)) != bool(probe_executed_b):
            fail_v18("NONDETERMINISTIC")

    if bool(tick_outcome.get("candidate_bundle_present_b", False)) != bool(candidate_bundle_present_b):
        fail_v18("NONDETERMINISTIC")
    if bool(tick_outcome.get("probe_executed_b", False)) != bool(probe_executed_b):
        fail_v18("NONDETERMINISTIC")

    declared_class_tick = str(tick_outcome.get("declared_class", "")).strip()
    effect_class_tick = str(tick_outcome.get("effect_class", "")).strip()
    declared_class_promo = str((promotion_payload or {}).get("declared_class", "")).strip()
    effect_class_promo = str((promotion_payload or {}).get("effect_class", "")).strip()
    if declared_class_promo and declared_class_tick != declared_class_promo:
        fail_v18("NONDETERMINISTIC")
    if effect_class_promo and effect_class_tick != effect_class_promo:
        fail_v18("NONDETERMINISTIC")
    if isinstance(promotion_payload, dict):
        result = promotion_payload.get("result")
        if not isinstance(result, dict):
            fail_v18("SCHEMA_FAIL")
        if effect_class_promo == "EFFECT_HEAVY_NO_UTILITY":
            if str(result.get("status", "")).strip() != "SKIPPED":
                fail_v18("NONDETERMINISTIC")
            route = str(result.get("route", "")).strip()
            reason = str(result.get("reason_code", "")).strip()
            if route not in {"SHADOW", "NONE"}:
                fail_v18("NONDETERMINISTIC")
            if route == "NONE" and reason != "NO_PROMOTION_BUNDLE":
                fail_v18("NONDETERMINISTIC")

    lane_name_for_frontier: str | None = None
    lane_hash = snapshot.get("lane_decision_receipt_hash")
    if lane_hash is not None:
        if not _is_sha256(lane_hash):
            fail_v18("SCHEMA_FAIL")
        lane_payload = _load_hash_bound_payload(
            dir_path=state_root / "long_run" / "lane",
            digest=str(lane_hash),
            suffix="lane_decision_receipt_v1.json",
            schema_version="v19_0",
        )
        if str(lane_payload.get("schema_name", "")).strip() != "lane_decision_receipt_v1":
            fail_v18("SCHEMA_FAIL")
        lane_backend = str(lane_payload.get("resolved_orch_llm_backend", "")).strip().lower()
        lane_model_id = str(lane_payload.get("resolved_orch_model_id", "")).strip()
        if lane_backend or lane_model_id:
            runtime_backend, runtime_model_id = _resolve_orch_runtime_provenance()
            if lane_backend != runtime_backend or lane_model_id != runtime_model_id:
                fail_v18("NONDETERMINISTIC")
        lane_name_for_frontier = str(lane_payload.get("lane_name", "")).strip().upper() or None

    frontier_attempt_counted_b = bool(
        _frontier_attempt_evidence_satisfied(
            state_root=state_root,
            snapshot=snapshot,
            tick_outcome=tick_outcome,
            declared_class_tick=declared_class_tick,
            lane_name=lane_name_for_frontier,
            candidate_bundle_present_b=bool(candidate_bundle_present_b),
        )
    )
    if bool(tick_outcome.get("frontier_attempt_counted_b", False)) != bool(frontier_attempt_counted_b):
        fail_v18("NONDETERMINISTIC")

    dispatch_hash = snapshot.get("dispatch_receipt_hash")
    dispatch_payload_for_hardening: dict[str, Any] | None = None
    if dispatch_hash is not None:
        if not _is_sha256(dispatch_hash):
            fail_v18("SCHEMA_FAIL")
        dispatch_path = _find_nested_hash(
            state_root,
            str(dispatch_hash),
            "omega_dispatch_receipt_v1.json",
        )
        dispatch_payload = _load_canon_json(dispatch_path)
        if canon_hash_obj(dispatch_payload) != str(dispatch_hash):
            fail_v18("NONDETERMINISTIC")
        if str(dispatch_payload.get("schema_version", "")).strip() != "omega_dispatch_receipt_v1":
            fail_v18("SCHEMA_FAIL")
        validate_schema_v18(dispatch_payload, "omega_dispatch_receipt_v1")
        dispatch_payload_for_hardening = dispatch_payload
        _verify_candidate_precheck_for_dispatch(state_root=state_root, dispatch_payload=dispatch_payload)

    routing_hash = snapshot.get("dependency_routing_receipt_hash")
    if routing_hash is not None:
        if not _is_sha256(routing_hash):
            fail_v18("SCHEMA_FAIL")
        routing_payload = _load_hash_bound_payload(
            dir_path=state_root / "long_run" / "debt",
            digest=str(routing_hash),
            suffix="dependency_routing_receipt_v1.json",
            schema_version="v19_0",
        )
        if str(routing_payload.get("schema_name", "")) != "dependency_routing_receipt_v1":
            fail_v18("SCHEMA_FAIL")
        routing_payload.setdefault("blocks_debt_key", None)
        routing_payload.setdefault("forced_frontier_debt_key", None)
        routing_payload.setdefault("orch_policy_bundle_id_used", None)
        routing_payload.setdefault("orch_policy_row_hit_b", False)
        routing_payload.setdefault("orch_policy_selected_bonus_q32", 0)
        validate_schema_v19(routing_payload, "dependency_routing_receipt_v1")
        market_selection_in_play_b = bool(
            (snapshot.get("bid_selection_receipt_hash") is not None)
            or (snapshot.get("policy_market_selection_hash") is not None)
        )
        reason_codes = routing_payload.get("reason_codes")
        if not isinstance(reason_codes, list):
            fail_v18("SCHEMA_FAIL")
        observed_selector_id = str(routing_payload.get("routing_selector_id", "")).strip()
        if bool(bandit_enabled_b):
            if not _is_sha256(observed_selector_id):
                fail_v18("NONDETERMINISTIC")
        else:
            expected_selector_id = _expected_routing_selector_id(
                forced_frontier_attempt_b=bool(routing_payload.get("forced_frontier_attempt_b", False)),
                reason_codes=[str(row) for row in reason_codes],
                market_selection_in_play_b=market_selection_in_play_b,
            )
            if observed_selector_id != expected_selector_id:
                fail_v18("NONDETERMINISTIC")
        observed_market_used_for_selection_b = bool(routing_payload.get("market_used_for_selection_b", False))
        if observed_market_used_for_selection_b != (observed_selector_id == "MARKET"):
            fail_v18("NONDETERMINISTIC")
        if bool(routing_payload.get("market_frozen_b", False)) and observed_market_used_for_selection_b:
            fail_v18("NONDETERMINISTIC")
        forced_heavy_sh1_b = bool(
            (bool(routing_payload.get("forced_frontier_attempt_b", False)) or observed_selector_id == "HARD_LOCK_OVERRIDE")
            and str(routing_payload.get("selected_capability_id", "")).strip() == "RSI_GE_SH1_OPTIMIZER"
        )
        if forced_heavy_sh1_b:
            if dispatch_payload_for_hardening is None:
                fail_v18("NONDETERMINISTIC")
            dispatch_campaign_id = str(dispatch_payload_for_hardening.get("campaign_id", "")).strip()
            if dispatch_campaign_id != _GE_SH1_CAMPAIGN_ID:
                fail_v18("NONDETERMINISTIC")
            invocation = dispatch_payload_for_hardening.get("invocation")
            if not isinstance(invocation, dict):
                fail_v18("SCHEMA_FAIL")
            env_overrides = invocation.get("env_overrides")
            if not isinstance(env_overrides, dict):
                fail_v18("NONDETERMINISTIC")
            if str(env_overrides.get("OMEGA_SH1_FORCED_HEAVY_B", "")).strip() != "1":
                fail_v18("NONDETERMINISTIC")

    debt_hash = snapshot.get("dependency_debt_snapshot_hash")
    if debt_hash is not None:
        if not _is_sha256(debt_hash):
            fail_v18("SCHEMA_FAIL")
        debt_payload = _load_hash_bound_payload(
            dir_path=state_root / "long_run" / "debt",
            digest=str(debt_hash),
            suffix="dependency_debt_state_v1.json",
            schema_version="v19_0",
        )
        if str(debt_payload.get("schema_name", "")) != "dependency_debt_state_v1":
            fail_v18("SCHEMA_FAIL")
        debt_payload.setdefault("debt_by_key", {})
        debt_payload.setdefault("ticks_without_frontier_attempt_by_key", {})
        debt_payload.setdefault("first_debt_tick_by_key", {})
        debt_payload.setdefault("last_frontier_attempt_debt_key", None)
        debt_payload.setdefault("hard_lock_debt_key", None)
        debt_payload.setdefault("scaffold_inflight_ccap_id", None)
        debt_payload.setdefault("scaffold_inflight_started_tick_u64", None)
        debt_payload.setdefault("max_inflight_ccap_ids_u32", 1)
        debt_payload.setdefault("failed_patch_ban_by_debt_key_target", {})
        debt_payload.setdefault("failed_shape_ban_by_debt_key_target", {})
        debt_payload.setdefault("last_failure_nontriviality_cert_by_debt_key", {})
        debt_payload.setdefault("last_failure_failed_threshold_by_debt_key", {})
        validate_schema_v19(debt_payload, "dependency_debt_state_v1")
        if int(debt_payload.get("max_inflight_ccap_ids_u32", 0)) != 1:
            fail_v18("NONDETERMINISTIC")
        inflight_ccap_id = debt_payload.get("scaffold_inflight_ccap_id")
        inflight_started_tick_u64 = debt_payload.get("scaffold_inflight_started_tick_u64")
        if inflight_ccap_id is None and inflight_started_tick_u64 is not None:
            fail_v18("NONDETERMINISTIC")
        if inflight_ccap_id is not None:
            inflight_ccap_id = _require_sha256(inflight_ccap_id, reason="NONDETERMINISTIC")
            if not isinstance(inflight_started_tick_u64, int) or int(inflight_started_tick_u64) < 0:
                fail_v18("NONDETERMINISTIC")
            ccap_path = _find_nested_hash(state_root, inflight_ccap_id, "ccap_v1.json")
            ccap_payload = _load_canon_json(ccap_path)
            if canon_hash_obj(ccap_payload) != inflight_ccap_id:
                fail_v18("NONDETERMINISTIC")
            validate_schema_v18(ccap_payload, "ccap_v1")


def _verify_orch_policy_update_activation(
    *,
    state_root: Path,
    snapshot: dict[str, Any],
    promotion_payload: dict[str, Any],
) -> None:
    activation_hash = snapshot.get("activation_receipt_hash")
    if not _is_sha256(activation_hash):
        fail_v18("MISSING_STATE_INPUT")
    activation_path = _find_nested_hash(state_root, str(activation_hash), "omega_activation_receipt_v1.json")
    activation_payload = _load_canon_json(activation_path)
    if canon_hash_obj(activation_payload) != str(activation_hash):
        fail_v18("NONDETERMINISTIC")
    validate_schema_v18(activation_payload, "omega_activation_receipt_v1")
    activation_kind = str(
        activation_payload.get("activation_kind")
        or activation_payload.get("activation_method")
        or ""
    ).strip()
    if activation_kind != "ACTIVATION_KIND_ORCH_POLICY_UPDATE":
        fail_v18("SCHEMA_FAIL")
    if not bool(activation_payload.get("activation_success", False)):
        fail_v18("DOWNSTREAM_META_CORE_FAIL")

    orch_policy_activation_hash = str(activation_payload.get("orch_policy_activation_receipt_hash", "")).strip()
    if not _is_sha256(orch_policy_activation_hash):
        fail_v18("MISSING_STATE_INPUT")
    orch_policy_activation_path = _find_nested_hash(
        state_root,
        orch_policy_activation_hash,
        "orch_policy_activation_receipt_v1.json",
    )
    orch_policy_activation_payload = _load_canon_json(orch_policy_activation_path)
    if canon_hash_obj(orch_policy_activation_payload) != orch_policy_activation_hash:
        fail_v18("NONDETERMINISTIC")
    validate_schema_v19(orch_policy_activation_payload, "orch_policy_activation_receipt_v1")
    if str(orch_policy_activation_payload.get("status", "")).strip() != "OK":
        fail_v18("DOWNSTREAM_META_CORE_FAIL")

    promotion_bundle_hash = _require_sha256(promotion_payload.get("promotion_bundle_hash"), reason="SCHEMA_FAIL")
    if str(orch_policy_activation_payload.get("policy_bundle_id", "")).strip() != str(promotion_bundle_hash):
        fail_v18("NONDETERMINISTIC")

    pointer_rel = str(orch_policy_activation_payload.get("pointer_path", "")).strip()
    pointer_rel_path = Path(pointer_rel)
    if not pointer_rel or pointer_rel_path.is_absolute() or ".." in pointer_rel_path.parts:
        fail_v18("SCHEMA_FAIL")
    try:
        daemon_root = state_root.parents[1]
    except Exception:
        fail_v18("MISSING_STATE_INPUT")
    pointer_path = (daemon_root / pointer_rel_path).resolve()
    if not pointer_path.exists() or not pointer_path.is_file():
        fail_v18("MISSING_STATE_INPUT")
    pointer_payload = _load_canon_json(pointer_path)
    validate_schema_v19(pointer_payload, "orch_policy_pointer_v1")
    if str(pointer_payload.get("active_policy_bundle_id", "")).strip() != str(promotion_bundle_hash):
        fail_v18("NONDETERMINISTIC")
    if int(max(0, int(pointer_payload.get("updated_tick_u64", 0)))) != int(max(0, int(snapshot.get("tick_u64", 0)))):
        fail_v18("NONDETERMINISTIC")

    ledger_path = state_root / "ledger" / "omega_ledger_v1.jsonl"
    if not ledger_path.exists() or not ledger_path.is_file():
        fail_v18("MISSING_STATE_INPUT")
    rows = [line.strip() for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    event_rows: list[dict[str, Any]] = []
    for line in rows:
        try:
            payload = json.loads(line)
        except Exception:
            fail_v18("SCHEMA_FAIL")
        if not isinstance(payload, dict):
            fail_v18("SCHEMA_FAIL")
        validate_schema_v18(payload, "omega_ledger_event_v1")
        if int(max(0, int(payload.get("tick_u64", -1)))) != int(max(0, int(snapshot.get("tick_u64", 0)))):
            continue
        if str(payload.get("event_type", "")).strip() == "ORCH_POLICY_UPDATE":
            event_rows.append(payload)
    if len(event_rows) != 1:
        fail_v18("NONDETERMINISTIC")
    if str(event_rows[0].get("artifact_hash", "")).strip() != str(orch_policy_activation_hash):
        fail_v18("NONDETERMINISTIC")


def verify(state_dir: Path, *, mode: str = "full") -> str:
    # Verifier replay is pinned-only; force network off regardless of caller env.
    os.environ["OMEGA_NET_LIVE_OK"] = "0"
    verify_v18(state_dir, mode=mode)

    state_root = _resolve_state_dir(state_dir)
    snapshot = _latest_snapshot_or_fail(state_root / "snapshot")
    _verify_policy_path(state_root, snapshot)
    config_candidates = [
        state_root.parent / "config",
        state_root / "config",
    ]
    config_dir = next((path for path in config_candidates if path.exists() and path.is_dir()), None)
    if config_dir is None:
        fail_v18("MISSING_STATE_INPUT")
    pack_payload = _load_pack(config_dir)
    bandit_enabled_b = bool(str(pack_payload.get("orch_bandit_config_rel", "")).strip())
    _verify_shadow_path(state_root=state_root, config_dir=config_dir, snapshot=snapshot)
    _verify_epistemic_path(state_root, snapshot)

    long_run_fields = (
        "launch_manifest_hash",
        "stop_receipt_hash",
        "mission_goal_ingest_receipt_hash",
        "dependency_routing_receipt_hash",
        "dependency_debt_snapshot_hash",
    )
    long_run_enabled_b = (
        (state_root / "long_run").exists()
        or (config_dir / "long_run_profile_v1.json").exists()
        or any(snapshot.get(field) is not None for field in long_run_fields)
    )
    if long_run_enabled_b:
        _verify_long_run_ledger_bindings(state_root)
        _verify_hardening_bindings(
            state_root=state_root,
            config_dir=config_dir,
            snapshot=snapshot,
            bandit_enabled_b=bandit_enabled_b,
        )

    if bandit_enabled_b:
        verify_orch_bandit_v1(
            state_root=state_root,
            config_dir=config_dir,
            snapshot=snapshot,
            pack_payload=pack_payload,
        )

    promo_hash = snapshot.get("promotion_receipt_hash")
    if promo_hash is None:
        return "VALID"

    promotion_path = _find_nested_hash(state_root, str(promo_hash), "omega_promotion_receipt_v1.json")
    promotion_payload = _load_canon_json(promotion_path)
    status = str((promotion_payload.get("result") or {}).get("status", ""))
    if status != "PROMOTED":
        return "VALID"

    result_kind = str(promotion_payload.get("result_kind", "")).strip().upper()
    if result_kind == "PROMOTED_EXT_QUEUED":
        return "VALID"
    if result_kind == "PROMOTED_POLICY_UPDATE":
        _verify_orch_policy_update_activation(
            state_root=state_root,
            snapshot=snapshot,
            promotion_payload=promotion_payload,
        )
        return "VALID"

    bundle_hash = str(promotion_payload.get("promotion_bundle_hash", ""))
    bundle_path = _load_promotion_bundle_by_hash(state_root, bundle_hash)
    if bundle_path is None:
        fail_v18("MISSING_STATE_INPUT")

    bundle_obj = _load_canon_json(bundle_path)
    try:
        _verify_axis_bundle_gate(
            bundle_obj=bundle_obj,
            bundle_path=bundle_path,
            promotion_dir=promotion_path.parent,
        )
    except Exception:
        fail_v18("NONDETERMINISTIC")

    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_omega_daemon_v1_v19")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        print(verify(Path(args.state_dir), mode=args.mode))
    except OmegaV18Error as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        reason_code = msg.split("INVALID:", 1)[1].strip() if msg.startswith("INVALID:") else msg.strip()
        reason_upper = str(reason_code).upper()
        if reason_upper.startswith("SUBVERIFIER_REPLAY_FAIL"):
            detail_hash = _write_state_verifier_replay_fail_detail(
                state_dir=Path(args.state_dir),
                exc=exc,
            )
            if isinstance(detail_hash, str) and detail_hash.startswith("sha256:"):
                print(f"SUBVERIFIER_REPLAY_FAIL_DETAIL_HASH:{detail_hash}")
        elif reason_upper.startswith("NONDETERMINISTIC"):
            detail_hash = _write_state_verifier_failure_detail(
                state_dir=Path(args.state_dir),
                reason_code="NONDETERMINISTIC",
                exc=exc,
            )
            if isinstance(detail_hash, str) and detail_hash.startswith("sha256:"):
                print(f"FAILURE_DETAIL_HASH:{detail_hash}")
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
