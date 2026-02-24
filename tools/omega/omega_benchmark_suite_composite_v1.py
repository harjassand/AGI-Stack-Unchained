#!/usr/bin/env python3
"""Deterministic composite benchmark suite runner for evaluation_kernel_v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.ccap_runtime_v1 import compute_workspace_tree_id, tracked_files
from cdel.v18_0.omega_common_v1 import canon_hash_obj

_Q32_ONE = 1 << 32


class CompositeRunnerError(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = str(code).strip() or "EVAL_STAGE_FAIL"
        self.detail = str(detail).strip() or "composite benchmark failure"
        super().__init__(f"{self.code}:{self.detail}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class EffectiveSuite:
    suite_id: str
    suite_name: str
    suite_set_id: str
    suite_source: str
    ledger_ordinal_u64: int
    suite_runner_relpath: str
    suite_visibility: str
    inputs_pack_id: str | None
    labels_pack_id: str | None
    hidden_tests_pack_id: str | None
    io_contract: dict[str, Any] | None


def _ensure_sha256(value: Any, *, field: str) -> str:
    text = str(value).strip()
    if len(text) != 71 or not text.startswith("sha256:"):
        raise CompositeRunnerError("SCHEMA_FAIL", f"{field} is not sha256:<hex64>")
    hex_part = text.split(":", 1)[1]
    if any(ch not in "0123456789abcdef" for ch in hex_part):
        raise CompositeRunnerError("SCHEMA_FAIL", f"{field} is not sha256:<hex64>")
    return text


def _normalize_relpath(path_value: Any) -> str:
    rel = str(path_value).strip().replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    path = Path(rel)
    if not rel or path.is_absolute() or ".." in path.parts:
        raise CompositeRunnerError("SCHEMA_FAIL", f"invalid relpath: {path_value!r}")
    return rel


def _prefix_match(path_rel: str, prefix: str) -> bool:
    normalized_path = _normalize_relpath(path_rel)
    normalized_prefix = _normalize_relpath(prefix)
    if normalized_prefix.endswith("/"):
        normalized_prefix = normalized_prefix[:-1]
    if not normalized_prefix:
        return False
    return normalized_path == normalized_prefix or normalized_path.startswith(f"{normalized_prefix}/")


def _load_canon_dict(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise CompositeRunnerError("SCHEMA_FAIL", f"failed to parse json: {path}") from exc
    if not isinstance(payload, dict):
        raise CompositeRunnerError("SCHEMA_FAIL", f"json payload is not object: {path}")
    observed = canon_hash_obj(payload)
    if path.name.startswith("sha256_"):
        expected = "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]
        if observed != expected:
            raise CompositeRunnerError("NONDETERMINISM_DETECTED", f"hash mismatch for {path}")
    return payload


def _verify_declared_id(payload: dict[str, Any], *, id_field: str) -> str:
    declared = _ensure_sha256(payload.get(id_field), field=id_field)
    no_id = dict(payload)
    no_id.pop(id_field, None)
    observed = canon_hash_obj(no_id)
    if observed != declared:
        raise CompositeRunnerError("NONDETERMINISM_DETECTED", f"declared id mismatch for {id_field}")
    return declared


def _sha256_hex(sha256_id: str) -> str:
    return _ensure_sha256(sha256_id, field="sha256_id").split(":", 1)[1]


def _load_object_by_id(
    *,
    root: Path,
    schema_version: str,
    id_field: str,
    object_id: str,
) -> tuple[dict[str, Any], Path]:
    obj_id = _ensure_sha256(object_id, field=id_field)
    matches: list[tuple[dict[str, Any], Path]] = []
    for path in sorted(root.glob("*.json"), key=lambda row: row.as_posix()):
        payload = _load_canon_dict(path)
        if str(payload.get("schema_version", "")).strip() != schema_version:
            continue
        if str(payload.get(id_field, "")).strip() != obj_id:
            continue
        _verify_declared_id(payload, id_field=id_field)
        matches.append((payload, path))
    if not matches:
        raise CompositeRunnerError("MISSING_STATE_INPUT", f"{schema_version} not found for {obj_id}")
    if len(matches) != 1:
        raise CompositeRunnerError("NONDETERMINISM_DETECTED", f"multiple {schema_version} rows for {obj_id}")
    return matches[0]


def _resolve_within_authority(*, repo_root: Path, relpath: str) -> Path:
    authority_root = (repo_root / "authority").resolve()
    candidate = (repo_root / _normalize_relpath(relpath)).resolve()
    try:
        candidate.relative_to(authority_root)
    except Exception as exc:  # noqa: BLE001
        raise CompositeRunnerError("SCHEMA_FAIL", f"path escapes authority root: {relpath}") from exc
    return candidate


def _load_suite_manifest_from_relpath(
    *,
    repo_root: Path,
    relpath: str,
    expected_suite_id: str,
    expected_manifest_id: str,
) -> dict[str, Any]:
    path = _resolve_within_authority(repo_root=repo_root, relpath=relpath)
    if not path.exists() or not path.is_file():
        raise CompositeRunnerError("MISSING_STATE_INPUT", f"suite manifest missing: {relpath}")
    payload = _load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != "benchmark_suite_manifest_v1":
        raise CompositeRunnerError("SCHEMA_FAIL", f"suite manifest schema mismatch: {relpath}")
    suite_id = _verify_declared_id(payload, id_field="suite_id")
    manifest_id = canon_hash_obj(payload)
    if suite_id != _ensure_sha256(expected_suite_id, field="suite_id"):
        raise CompositeRunnerError("SCHEMA_FAIL", f"suite id mismatch in manifest: {relpath}")
    if manifest_id != _ensure_sha256(expected_manifest_id, field="suite_manifest_id"):
        raise CompositeRunnerError("SCHEMA_FAIL", f"suite manifest hash mismatch: {relpath}")
    return payload


def _load_suite_set_from_relpath(
    *,
    repo_root: Path,
    relpath: str,
    expected_suite_set_id: str,
) -> dict[str, Any]:
    path = _resolve_within_authority(repo_root=repo_root, relpath=relpath)
    if not path.exists() or not path.is_file():
        raise CompositeRunnerError("MISSING_STATE_INPUT", f"suite set missing: {relpath}")
    payload = _load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != "benchmark_suite_set_v1":
        raise CompositeRunnerError("SCHEMA_FAIL", f"suite set schema mismatch: {relpath}")
    suite_set_id = _verify_declared_id(payload, id_field="suite_set_id")
    if suite_set_id != _ensure_sha256(expected_suite_set_id, field="suite_set_id"):
        raise CompositeRunnerError("SCHEMA_FAIL", f"suite set id mismatch: {relpath}")
    return payload


def _optional_sha256(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return _ensure_sha256(text, field=field)


def _ensure_q32_int(value: Any, *, field: str) -> int:
    out = int(value)
    if out < 0 or out > _Q32_ONE:
        raise CompositeRunnerError("SCHEMA_FAIL", f"{field} must be in [0, Q32_ONE]")
    return out


def _normalize_io_contract(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    predictions_relpath_raw = value.get("predictions_relpath")
    if not isinstance(predictions_relpath_raw, str) or not predictions_relpath_raw.strip():
        raise CompositeRunnerError("SCHEMA_FAIL", "io_contract.predictions_relpath is required")
    predictions_relpath = _normalize_relpath(predictions_relpath_raw)
    output_root_relpath_raw = value.get("output_root_relpath")
    output_root_relpath = (
        _normalize_relpath(output_root_relpath_raw)
        if isinstance(output_root_relpath_raw, str) and output_root_relpath_raw.strip()
        else "holdout_out"
    )
    allowed_output_files_raw = value.get("allowed_output_files")
    if not isinstance(allowed_output_files_raw, list) or not allowed_output_files_raw:
        raise CompositeRunnerError("SCHEMA_FAIL", "io_contract.allowed_output_files must be a non-empty array")
    allowed_output_files = sorted({_normalize_relpath(row) for row in allowed_output_files_raw})
    if predictions_relpath not in set(allowed_output_files):
        raise CompositeRunnerError(
            "SCHEMA_FAIL",
            "io_contract.allowed_output_files must include io_contract.predictions_relpath",
        )

    stdout_relpath_raw = value.get("stdout_relpath")
    stderr_relpath_raw = value.get("stderr_relpath")
    stdout_relpath = _normalize_relpath(stdout_relpath_raw) if isinstance(stdout_relpath_raw, str) and stdout_relpath_raw.strip() else None
    stderr_relpath = _normalize_relpath(stderr_relpath_raw) if isinstance(stderr_relpath_raw, str) and stderr_relpath_raw.strip() else None

    required_output_files_raw = value.get("required_output_files")
    required_output_files: list[str]
    if isinstance(required_output_files_raw, list):
        required_output_files = sorted({_normalize_relpath(row) for row in required_output_files_raw})
    else:
        required_output_files = [predictions_relpath]
    if predictions_relpath not in required_output_files:
        required_output_files = sorted(set(required_output_files) | {predictions_relpath})

    forbidden_output_prefixes_raw = value.get("forbidden_output_prefixes")
    forbidden_output_prefixes = (
        sorted({_normalize_relpath(row) for row in forbidden_output_prefixes_raw})
        if isinstance(forbidden_output_prefixes_raw, list)
        else []
    )

    max_output_files_u64 = int(value.get("max_output_files_u64", 16))
    max_output_bytes_u64 = int(value.get("max_output_bytes_u64", 16_777_216))
    max_single_output_bytes_u64 = int(value.get("max_single_output_bytes_u64", 4_194_304))
    if max_output_files_u64 <= 0 or max_output_bytes_u64 <= 0 or max_single_output_bytes_u64 <= 0:
        raise CompositeRunnerError("SCHEMA_FAIL", "io_contract max output limits must be positive")

    candidate_mode_raw = value.get("candidate_mode")
    candidate_mode = str(candidate_mode_raw).strip() if isinstance(candidate_mode_raw, str) and candidate_mode_raw.strip() else "holdout_candidate"

    min_accuracy_q32 = _ensure_q32_int(value.get("min_accuracy_q32", 0), field="io_contract.min_accuracy_q32")
    min_coverage_q32 = _ensure_q32_int(value.get("min_coverage_q32", 0), field="io_contract.min_coverage_q32")

    return {
        "output_root_relpath": output_root_relpath,
        "predictions_relpath": predictions_relpath,
        "stdout_relpath": stdout_relpath,
        "stderr_relpath": stderr_relpath,
        "allowed_output_files": allowed_output_files,
        "required_output_files": required_output_files,
        "forbidden_output_prefixes": forbidden_output_prefixes,
        "max_output_files_u64": int(max_output_files_u64),
        "max_output_bytes_u64": int(max_output_bytes_u64),
        "max_single_output_bytes_u64": int(max_single_output_bytes_u64),
        "candidate_mode": candidate_mode,
        "min_accuracy_q32": int(min_accuracy_q32),
        "min_coverage_q32": int(min_coverage_q32),
    }


def _load_holdout_policy(
    *,
    repo_root: Path,
    holdout_policy_id: str,
) -> dict[str, Any]:
    target = _ensure_sha256(holdout_policy_id, field="holdout_policy_id")
    root = (repo_root / "authority" / "holdout_policies").resolve()
    if not root.exists() or not root.is_dir():
        raise CompositeRunnerError("MISSING_STATE_INPUT", "authority/holdout_policies is missing")
    matches: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json"), key=lambda row: row.as_posix()):
        payload = _load_canon_dict(path)
        if str(payload.get("schema_version", "")).strip() != "holdout_policy_v1":
            continue
        try:
            declared = _verify_declared_id(payload, id_field="holdout_policy_id")
        except Exception as exc:  # noqa: BLE001
            raise CompositeRunnerError("NONDETERMINISM_DETECTED", f"holdout policy id mismatch: {path.as_posix()}") from exc
        if declared == target:
            matches.append(payload)
    if not matches:
        raise CompositeRunnerError("HOLDOUT_POLICY_PIN_MISMATCH", f"holdout policy not found for {target}")
    if len(matches) != 1:
        raise CompositeRunnerError("NONDETERMINISM_DETECTED", f"multiple holdout policy rows for {target}")
    payload = matches[0]
    harness_only_prefixes = payload.get("harness_only_prefixes")
    candidate_output_policy = payload.get("candidate_output_policy")
    candidate_execution_policy = payload.get("candidate_execution_policy")
    if not isinstance(harness_only_prefixes, list):
        raise CompositeRunnerError("SCHEMA_FAIL", "holdout policy harness_only_prefixes must be a list")
    if not isinstance(candidate_output_policy, dict):
        raise CompositeRunnerError("SCHEMA_FAIL", "holdout policy candidate_output_policy must be an object")
    if not isinstance(candidate_execution_policy, dict):
        raise CompositeRunnerError("SCHEMA_FAIL", "holdout policy candidate_execution_policy must be an object")
    return payload


def _load_holdout_pack(
    *,
    repo_root: Path,
    pack_id: str,
    field: str,
) -> tuple[dict[str, Any], Path]:
    normalized_id = _ensure_sha256(pack_id, field=field)
    path = (repo_root / "authority" / "holdouts" / "packs" / f"sha256_{_sha256_hex(normalized_id)}.json").resolve()
    if not path.exists() or not path.is_file():
        raise CompositeRunnerError("MISSING_STATE_INPUT", f"{field} is missing from holdout pack store")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise CompositeRunnerError("SCHEMA_FAIL", f"failed to parse holdout pack json: {path.as_posix()}") from exc
    if not isinstance(payload, dict):
        raise CompositeRunnerError("SCHEMA_FAIL", f"holdout pack payload must be object: {path.as_posix()}")
    pack_id_raw = payload.get("pack_id")
    if pack_id_raw is None:
        observed = canon_hash_obj(payload)
    else:
        observed = _verify_declared_id(payload, id_field="pack_id")
    if observed != normalized_id:
        raise CompositeRunnerError("NONDETERMINISM_DETECTED", f"{field} hash mismatch in holdout pack")
    return payload, path


def _normalize_suite_rows(
    *,
    suite_set: dict[str, Any],
    suite_source: str,
    ledger_ordinal_u64: int,
    repo_root: Path,
) -> list[EffectiveSuite]:
    suites = suite_set.get("suites")
    if not isinstance(suites, list) or not suites:
        raise CompositeRunnerError("SCHEMA_FAIL", "suite set has no suites")
    out: list[EffectiveSuite] = []
    for row in suites:
        if not isinstance(row, dict):
            raise CompositeRunnerError("SCHEMA_FAIL", "suite row must be object")
        suite_id = _ensure_sha256(row.get("suite_id"), field="suite_id")
        suite_manifest_id = _ensure_sha256(row.get("suite_manifest_id"), field="suite_manifest_id")
        suite_manifest_relpath = _normalize_relpath(row.get("suite_manifest_relpath"))
        manifest = _load_suite_manifest_from_relpath(
            repo_root=repo_root,
            relpath=suite_manifest_relpath,
            expected_suite_id=suite_id,
            expected_manifest_id=suite_manifest_id,
        )
        suite_name = str(manifest.get("suite_name", "")).strip()
        if not suite_name:
            raise CompositeRunnerError("SCHEMA_FAIL", f"suite_name missing for {suite_id}")
        runner_relpath = _normalize_relpath(manifest.get("suite_runner_relpath"))
        suite_visibility = str(manifest.get("visibility", "")).strip().upper()
        if suite_visibility not in {"PUBLIC", "HIDDEN", "HOLDOUT"}:
            raise CompositeRunnerError("SCHEMA_FAIL", f"suite visibility is invalid for {suite_id}")
        inputs_pack_id = _optional_sha256(manifest.get("inputs_pack_id"), field="inputs_pack_id")
        labels_pack_id = _optional_sha256(manifest.get("labels_pack_id"), field="labels_pack_id")
        hidden_tests_pack_id = _optional_sha256(manifest.get("hidden_tests_pack_id"), field="hidden_tests_pack_id")
        io_contract = _normalize_io_contract(manifest.get("io_contract"))
        if suite_visibility == "HOLDOUT":
            if inputs_pack_id is None:
                raise CompositeRunnerError("SCHEMA_FAIL", f"holdout suite is missing inputs_pack_id: {suite_id}")
            if labels_pack_id is None and hidden_tests_pack_id is None:
                raise CompositeRunnerError("SCHEMA_FAIL", f"holdout suite must specify labels_pack_id or hidden_tests_pack_id: {suite_id}")
            if not isinstance(io_contract, dict):
                raise CompositeRunnerError("SCHEMA_FAIL", f"holdout suite is missing io_contract: {suite_id}")
        out.append(
            EffectiveSuite(
                suite_id=suite_id,
                suite_name=suite_name,
                suite_set_id=_ensure_sha256(suite_set.get("suite_set_id"), field="suite_set_id"),
                suite_source=suite_source,
                ledger_ordinal_u64=int(max(0, ledger_ordinal_u64)),
                suite_runner_relpath=runner_relpath,
                suite_visibility=suite_visibility,
                inputs_pack_id=inputs_pack_id,
                labels_pack_id=labels_pack_id,
                hidden_tests_pack_id=hidden_tests_pack_id,
                io_contract=dict(io_contract) if isinstance(io_contract, dict) else None,
            )
        )
    return out


def _load_ledger_chain(
    *,
    repo_root: Path,
    ledger_id: str,
    expected_anchor_ek_id: str,
) -> list[dict[str, Any]]:
    ledgers_root = repo_root / "authority" / "eval_kernel_ledgers"
    chain: list[dict[str, Any]] = []
    visited: set[str] = set()
    current_id = _ensure_sha256(ledger_id, field="ledger_id")
    while current_id:
        if current_id in visited:
            raise CompositeRunnerError("SCHEMA_FAIL", "kernel extension ledger chain has cycle")
        visited.add(current_id)
        ledger, _path = _load_object_by_id(
            root=ledgers_root,
            schema_version="kernel_extension_ledger_v1",
            id_field="ledger_id",
            object_id=current_id,
        )
        anchor_ek_id = _ensure_sha256(ledger.get("anchor_ek_id"), field="anchor_ek_id")
        if anchor_ek_id != expected_anchor_ek_id:
            raise CompositeRunnerError("SCHEMA_FAIL", "kernel extension ledger anchor_ek_id mismatch")
        chain.append(ledger)
        parent = str(ledger.get("parent_ledger_id", "")).strip()
        if not parent:
            break
        current_id = _ensure_sha256(parent, field="parent_ledger_id")
    chain.reverse()

    prior_entries: list[dict[str, Any]] | None = None
    prior_ledger_id = ""
    for ledger in chain:
        if prior_ledger_id and str(ledger.get("parent_ledger_id", "")).strip() != prior_ledger_id:
            raise CompositeRunnerError("SCHEMA_FAIL", "kernel extension ledger parent linkage mismatch")
        entries = ledger.get("entries")
        if not isinstance(entries, list):
            raise CompositeRunnerError("SCHEMA_FAIL", "kernel extension ledger entries must be list")
        ordinals: list[int] = []
        for row in entries:
            if not isinstance(row, dict):
                raise CompositeRunnerError("SCHEMA_FAIL", "kernel extension ledger entry must be object")
            ordinals.append(int(max(0, int(row.get("ordinal_u64", 0)))))
        if ordinals != list(range(len(ordinals))):
            raise CompositeRunnerError("SCHEMA_FAIL", "kernel extension ledger ordinals must be contiguous")
        if prior_entries is not None:
            if len(entries) < len(prior_entries):
                raise CompositeRunnerError("SCHEMA_FAIL", "kernel extension ledger is not append-only")
            for idx, prev in enumerate(prior_entries):
                if canon_hash_obj(entries[idx]) != canon_hash_obj(prev):
                    raise CompositeRunnerError("SCHEMA_FAIL", "kernel extension ledger append-only check failed")
        prior_entries = [dict(row) for row in entries]
        prior_ledger_id = _ensure_sha256(ledger.get("ledger_id"), field="ledger_id")

    return chain


def resolve_effective_suites(
    *,
    repo_root: Path,
    ek_id: str,
    anchor_suite_set_id: str,
    extensions_ledger_id: str,
) -> list[EffectiveSuite]:
    authority_root = repo_root / "authority"
    suite_sets_root = authority_root / "benchmark_suite_sets"

    anchor_suite_set, _anchor_path = _load_object_by_id(
        root=suite_sets_root,
        schema_version="benchmark_suite_set_v1",
        id_field="suite_set_id",
        object_id=anchor_suite_set_id,
    )
    if str(anchor_suite_set.get("suite_set_kind", "")).strip() != "ANCHOR":
        raise CompositeRunnerError("SCHEMA_FAIL", "anchor suite set must have suite_set_kind=ANCHOR")

    effective: list[EffectiveSuite] = []
    effective.extend(
        _normalize_suite_rows(
            suite_set=anchor_suite_set,
            suite_source="ANCHOR",
            ledger_ordinal_u64=0,
            repo_root=repo_root,
        )
    )

    ledger_chain = _load_ledger_chain(
        repo_root=repo_root,
        ledger_id=extensions_ledger_id,
        expected_anchor_ek_id=_ensure_sha256(ek_id, field="ek_id"),
    )
    latest_ledger = ledger_chain[-1]
    latest_entries = latest_ledger.get("entries")
    if not isinstance(latest_entries, list):
        raise CompositeRunnerError("SCHEMA_FAIL", "kernel extension ledger entries missing")

    for entry in latest_entries:
        if not isinstance(entry, dict):
            raise CompositeRunnerError("SCHEMA_FAIL", "kernel extension ledger entry must be object")
        ordinal_u64 = int(max(0, int(entry.get("ordinal_u64", 0))))
        extension_spec_id = _ensure_sha256(entry.get("extension_spec_id"), field="extension_spec_id")
        extension_spec_relpath = _normalize_relpath(entry.get("extension_spec_relpath"))
        suite_set_id = _ensure_sha256(entry.get("suite_set_id"), field="suite_set_id")
        suite_set_relpath = _normalize_relpath(entry.get("suite_set_relpath"))

        spec_path = _resolve_within_authority(repo_root=repo_root, relpath=extension_spec_relpath)
        if not spec_path.exists() or not spec_path.is_file():
            raise CompositeRunnerError("MISSING_STATE_INPUT", f"extension spec missing: {extension_spec_relpath}")
        spec = _load_canon_dict(spec_path)
        if str(spec.get("schema_version", "")).strip() != "kernel_extension_spec_v1":
            raise CompositeRunnerError("SCHEMA_FAIL", f"extension spec schema mismatch: {extension_spec_relpath}")
        spec_declared_id = _verify_declared_id(spec, id_field="extension_spec_id")
        if spec_declared_id != extension_spec_id:
            raise CompositeRunnerError("SCHEMA_FAIL", f"extension spec id mismatch: {extension_spec_relpath}")
        if _ensure_sha256(spec.get("anchor_ek_id"), field="anchor_ek_id") != _ensure_sha256(ek_id, field="ek_id"):
            raise CompositeRunnerError("SCHEMA_FAIL", "extension spec anchor_ek_id mismatch")
        if not bool(spec.get("additive_only_b", False)):
            raise CompositeRunnerError("SCHEMA_FAIL", "kernel extension must be additive_only_b=true")
        if _ensure_sha256(spec.get("suite_set_id"), field="suite_set_id") != suite_set_id:
            raise CompositeRunnerError("SCHEMA_FAIL", "extension spec suite_set_id mismatch")
        if _normalize_relpath(spec.get("suite_set_relpath")) != suite_set_relpath:
            raise CompositeRunnerError("SCHEMA_FAIL", "extension spec suite_set_relpath mismatch")

        suite_set = _load_suite_set_from_relpath(
            repo_root=repo_root,
            relpath=suite_set_relpath,
            expected_suite_set_id=suite_set_id,
        )
        if str(suite_set.get("suite_set_kind", "")).strip() != "EXTENSION":
            raise CompositeRunnerError("SCHEMA_FAIL", "extension suite set must have suite_set_kind=EXTENSION")
        anchor_ek = str(suite_set.get("anchor_ek_id", "")).strip()
        if anchor_ek and _ensure_sha256(anchor_ek, field="anchor_ek_id") != _ensure_sha256(ek_id, field="ek_id"):
            raise CompositeRunnerError("SCHEMA_FAIL", "extension suite set anchor_ek_id mismatch")
        effective.extend(
            _normalize_suite_rows(
                suite_set=suite_set,
                suite_source="EXTENSION",
                ledger_ordinal_u64=ordinal_u64,
                repo_root=repo_root,
            )
        )

    seen: set[str] = set()
    for suite in effective:
        if suite.suite_id in seen:
            raise CompositeRunnerError("EK_SUITE_LIST_MISMATCH", f"duplicate suite_id: {suite.suite_id}")
        seen.add(suite.suite_id)
    return effective


def _suite_budget_outcome(*, wall_ms_u64: int, cpu_ms_u64: int) -> dict[str, Any]:
    return {
        "within_budget_b": True,
        "cpu_ms_u64": int(max(0, cpu_ms_u64)),
        "wall_ms_u64": int(max(0, wall_ms_u64)),
        "disk_mb_u64": 0,
    }


def _scorecard_path_for_series(*, runs_root: Path, series_prefix: str) -> Path:
    return runs_root / series_prefix / "OMEGA_RUN_SCORECARD_v1.json"


def _metrics_from_scorecard(scorecard: dict[str, Any]) -> dict[str, dict[str, int]]:
    median_stps_q32 = int(max(0, int(scorecard.get("median_stps_non_noop_q32", 0))))
    tpm = float(scorecard.get("non_noop_ticks_per_min", 0.0) or 0.0)
    tpm_q32 = int(max(0, int(round(tpm * float(_Q32_ONE)))))
    promotions_q32 = int(max(0, int(scorecard.get("promotions_u64", 0)))) << 32
    activation_q32 = int(max(0, int(scorecard.get("activation_success_u64", 0)))) << 32
    return {
        "median_stps_non_noop_q32": {"q": int(median_stps_q32)},
        "non_noop_ticks_per_min_q32": {"q": int(tpm_q32)},
        "promotions_u64_q32": {"q": int(promotions_q32)},
        "activation_success_u64_q32": {"q": int(activation_q32)},
    }


def _run_legacy_suite(
    *,
    repo_root: Path,
    suite: EffectiveSuite,
    suite_runs_root: Path,
    suite_series_prefix: str,
    ticks_u64: int,
    seed_u64: int,
) -> tuple[str, dict[str, dict[str, int]], list[dict[str, Any]]]:
    runner_path = (repo_root / suite.suite_runner_relpath).resolve()
    if not runner_path.exists() or not runner_path.is_file():
        raise CompositeRunnerError("MISSING_STATE_INPUT", f"suite runner missing: {suite.suite_runner_relpath}")

    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["OMEGA_RUN_SEED_U64"] = str(int(seed_u64))
    env["PYTHONPATH"] = f"{repo_root}:{repo_root / 'CDEL-v2'}:{env.get('PYTHONPATH', '')}".rstrip(":")

    suite_out_path = suite_runs_root / "suite_outcome_v1.json"
    cmd_suite_once = [
        sys.executable,
        str(runner_path),
        "--mode",
        "suite_once",
        "--suite_id",
        suite.suite_id,
        "--ticks",
        str(int(max(1, ticks_u64))),
        "--seed_u64",
        str(int(max(0, seed_u64))),
        "--series_prefix",
        suite_series_prefix,
        "--runs_root",
        str(suite_runs_root),
        "--out",
        str(suite_out_path),
    ]
    started = time.time()
    proc = subprocess.run(
        cmd_suite_once,
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    wall_ms_suite_once = int(max(0, round((time.time() - started) * 1000.0)))

    if proc.returncode == 0 and suite_out_path.exists() and suite_out_path.is_file():
        payload = _load_canon_dict(suite_out_path)
        outcome = str(payload.get("suite_outcome", "PASS")).strip().upper() or "PASS"
        metrics = payload.get("metrics")
        gate_results = payload.get("gate_results")
        if not isinstance(metrics, dict):
            metrics = {}
        if not isinstance(gate_results, list):
            gate_results = []
        normalized_metrics: dict[str, dict[str, int]] = {}
        for key in sorted(metrics.keys()):
            value = metrics.get(key)
            if isinstance(value, dict) and set(value.keys()) == {"q"}:
                normalized_metrics[str(key)] = {"q": int(value.get("q", 0))}
        return outcome, normalized_metrics, [
            {
                "gate_id": "SUITE_ONCE_EXIT_ZERO",
                "passed_b": True,
                "detail": f"wall_ms={wall_ms_suite_once}",
            }
        ] + list(gate_results)

    cmd_legacy = [
        sys.executable,
        str(runner_path),
        "--ticks",
        str(int(max(1, ticks_u64))),
        "--seed_u64",
        str(int(max(0, seed_u64))),
        "--series_prefix",
        suite_series_prefix,
        "--runs_root",
        str(suite_runs_root),
    ]
    started = time.time()
    legacy = subprocess.run(
        cmd_legacy,
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    wall_ms_legacy = int(max(0, round((time.time() - started) * 1000.0)))
    if legacy.returncode != 0:
        return (
            "FAIL",
            {},
            [
                {
                    "gate_id": "LEGACY_RUNNER_EXIT_ZERO",
                    "passed_b": False,
                    "detail": f"suite_once_rc={proc.returncode} legacy_rc={legacy.returncode}",
                }
            ],
        )

    scorecard_path = _scorecard_path_for_series(runs_root=suite_runs_root, series_prefix=suite_series_prefix)
    if not scorecard_path.exists() or not scorecard_path.is_file():
        return (
            "FAIL",
            {},
            [
                {
                    "gate_id": "LEGACY_SCORECARD_PRESENT",
                    "passed_b": False,
                    "detail": "legacy runner did not produce scorecard",
                }
            ],
        )
    scorecard = _load_canon_dict(scorecard_path)
    metrics = _metrics_from_scorecard(scorecard)
    return (
        "PASS",
        metrics,
        [
            {
                "gate_id": "LEGACY_RUNNER_EXIT_ZERO",
                "passed_b": True,
                "detail": f"wall_ms={wall_ms_legacy}",
            }
        ],
    )


def _env_truthy(name: str, *, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _sandbox_available_for_holdout() -> bool:
    return False


def _workspace_file_hashes(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for path in sorted(root.rglob("*"), key=lambda row: row.as_posix()):
        if not path.exists() or not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        out[rel] = f"sha256:{digest}"
    return out


def _jsonl_dict_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    line_u64 = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line_u64 += 1
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise CompositeRunnerError("PREDICTIONS_MISSING_OR_MALFORMED", f"invalid JSONL row at line {line_u64}") from exc
        if not isinstance(row, dict):
            raise CompositeRunnerError("PREDICTIONS_MISSING_OR_MALFORMED", f"prediction row at line {line_u64} must be an object")
        rows.append(row)
    return rows


def _prediction_value(row: dict[str, Any]) -> str:
    for key in ("prediction", "label", "value", "answer"):
        if key in row:
            value = row.get(key)
            return str(value).strip()
    raise CompositeRunnerError("PREDICTIONS_MISSING_OR_MALFORMED", "prediction row is missing prediction field")


def _truth_value(row: dict[str, Any]) -> str:
    for key in ("label", "expected", "truth", "answer"):
        if key in row:
            value = row.get(key)
            return str(value).strip()
    raise CompositeRunnerError("SCHEMA_FAIL", "truth row is missing label/expected/truth/answer")


def _run_holdout_suite(
    *,
    repo_root: Path,
    suite: EffectiveSuite,
    suite_runs_root: Path,
    suite_series_prefix: str,
    ticks_u64: int,
    seed_u64: int,
    holdout_policy: dict[str, Any],
) -> tuple[str, dict[str, dict[str, int]], list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(suite.io_contract, dict):
        raise CompositeRunnerError("SCHEMA_FAIL", "holdout suite is missing io_contract")
    if not suite.inputs_pack_id:
        raise CompositeRunnerError("SCHEMA_FAIL", "holdout suite is missing inputs_pack_id")

    io_contract = dict(suite.io_contract)
    policy_output = holdout_policy.get("candidate_output_policy")
    policy_exec = holdout_policy.get("candidate_execution_policy")
    policy_harness_only = holdout_policy.get("harness_only_prefixes")
    policy_candidate_visible = holdout_policy.get("candidate_visible_prefixes")
    if (
        not isinstance(policy_output, dict)
        or not isinstance(policy_exec, dict)
        or not isinstance(policy_harness_only, list)
        or not isinstance(policy_candidate_visible, list)
    ):
        raise CompositeRunnerError("SCHEMA_FAIL", "holdout policy is malformed")

    policy_holdout_id = str(holdout_policy.get("holdout_policy_id", "")).strip()
    if not policy_holdout_id.startswith("sha256:"):
        raise CompositeRunnerError("SCHEMA_FAIL", "holdout policy id is invalid")

    inputs_pack, inputs_pack_path = _load_holdout_pack(
        repo_root=repo_root,
        pack_id=suite.inputs_pack_id,
        field="inputs_pack_id",
    )
    labels_pack: dict[str, Any] | None = None
    labels_pack_path: Path | None = None
    if suite.labels_pack_id:
        labels_pack, labels_pack_path = _load_holdout_pack(
            repo_root=repo_root,
            pack_id=suite.labels_pack_id,
            field="labels_pack_id",
        )
    hidden_pack: dict[str, Any] | None = None
    hidden_pack_path: Path | None = None
    if suite.hidden_tests_pack_id:
        hidden_pack, hidden_pack_path = _load_holdout_pack(
            repo_root=repo_root,
            pack_id=suite.hidden_tests_pack_id,
            field="hidden_tests_pack_id",
        )

    suite_root = suite_runs_root / suite_series_prefix
    candidate_workspace = suite_root / "candidate_workspace"
    output_root_relpath = str(io_contract.get("output_root_relpath", "holdout_out"))
    candidate_output_root = candidate_workspace / output_root_relpath
    candidate_output_root.mkdir(parents=True, exist_ok=True)
    policy_forbidden_prefixes = policy_output.get("forbidden_output_prefixes")
    if not isinstance(policy_forbidden_prefixes, list):
        raise CompositeRunnerError("SCHEMA_FAIL", "holdout policy forbidden_output_prefixes must be a list")

    max_output_files_u64 = min(
        int(policy_output.get("max_output_files_u64", 16)),
        int(io_contract.get("max_output_files_u64", int(policy_output.get("max_output_files_u64", 16)))),
    )
    max_output_bytes_u64 = min(
        int(policy_output.get("max_output_bytes_u64", 16_777_216)),
        int(io_contract.get("max_output_bytes_u64", int(policy_output.get("max_output_bytes_u64", 16_777_216)))),
    )
    max_single_output_bytes_u64 = min(
        int(policy_output.get("max_single_output_bytes_u64", 4_194_304)),
        int(io_contract.get("max_single_output_bytes_u64", int(policy_output.get("max_single_output_bytes_u64", 4_194_304)))),
    )
    if max_output_files_u64 <= 0 or max_output_bytes_u64 <= 0 or max_single_output_bytes_u64 <= 0:
        raise CompositeRunnerError("SCHEMA_FAIL", "holdout output limits must be positive")

    required_output_files = sorted({_normalize_relpath(row) for row in io_contract.get("required_output_files", [])})
    predictions_relpath = _normalize_relpath(io_contract.get("predictions_relpath"))
    if predictions_relpath not in required_output_files:
        required_output_files.append(predictions_relpath)
    allowed_output_files = sorted({_normalize_relpath(row) for row in io_contract.get("allowed_output_files", [])})
    if not allowed_output_files:
        raise CompositeRunnerError("SCHEMA_FAIL", "io_contract.allowed_output_files must be non-empty")

    forbidden_output_prefixes = sorted(
        {_normalize_relpath(row) for row in list(policy_forbidden_prefixes) + list(io_contract.get("forbidden_output_prefixes", []))}
    )

    visible_prefixes = sorted({_normalize_relpath(row) for row in policy_candidate_visible})
    excluded_prefixes = sorted({_normalize_relpath(row) for row in policy_harness_only})
    excluded_paths: list[str] = []
    for source_path in (labels_pack_path, hidden_pack_path):
        if source_path is None:
            continue
        rel = source_path.resolve().relative_to(repo_root.resolve()).as_posix()
        excluded_paths.append(_normalize_relpath(rel))

    if candidate_workspace.exists():
        shutil.rmtree(candidate_workspace)
    candidate_workspace.mkdir(parents=True, exist_ok=True)

    materialized_paths: list[str] = []
    for rel in tracked_files(repo_root):
        rel_norm = _normalize_relpath(rel)
        if visible_prefixes and not any(_prefix_match(rel_norm, prefix) for prefix in visible_prefixes):
            continue
        if rel_norm in set(excluded_paths):
            continue
        if any(_prefix_match(rel_norm, prefix) for prefix in excluded_prefixes):
            continue
        src = (repo_root / rel_norm).resolve()
        dst = (candidate_workspace / rel_norm).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        materialized_paths.append(rel_norm)

    for rel in materialized_paths:
        if rel in set(excluded_paths) or any(_prefix_match(rel, prefix) for prefix in excluded_prefixes):
            raise CompositeRunnerError("HOLDOUT_PACK_MATERIALIZED", f"harness-only path was materialized: {rel}")

    inputs_workspace_path = candidate_workspace / "holdout" / "inputs_pack.json"
    inputs_workspace_path.parent.mkdir(parents=True, exist_ok=True)
    inputs_workspace_path.write_text(json.dumps(inputs_pack, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    baseline_hashes = _workspace_file_hashes(candidate_workspace)
    runner_path = (candidate_workspace / suite.suite_runner_relpath).resolve()
    if not runner_path.exists() or not runner_path.is_file():
        raise CompositeRunnerError("MISSING_STATE_INPUT", f"suite runner missing: {suite.suite_runner_relpath}")

    sandbox_available_b = _sandbox_available_for_holdout()
    sandbox_enforced_b = False
    require_sandbox_for_live_autonomy_b = bool(policy_exec.get("require_sandbox_for_live_autonomy_b", False))
    if require_sandbox_for_live_autonomy_b and _env_truthy("OMEGA_LIVE_AUTONOMY_B", default=False) and not sandbox_available_b:
        raise CompositeRunnerError(
            "HOLDOUT_ACCESS_VIOLATION",
            "sandbox is unavailable and holdout policy requires it for live autonomy",
        )

    candidate_mode = str(io_contract.get("candidate_mode", "holdout_candidate")).strip() or "holdout_candidate"
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["OMEGA_RUN_SEED_U64"] = str(int(max(0, seed_u64)))
    env["OMEGA_HOLDOUT_NETWORK"] = "forbidden"
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    env["HTTP_PROXY"] = ""
    env["HTTPS_PROXY"] = ""
    env["http_proxy"] = ""
    env["https_proxy"] = ""
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = f"{candidate_workspace}:{candidate_workspace / 'CDEL-v2'}:{env.get('PYTHONPATH', '')}".rstrip(":")

    candidate_cmd = [
        sys.executable,
        str(runner_path),
        "--mode",
        candidate_mode,
        "--suite_id",
        suite.suite_id,
        "--inputs_pack_path",
        str(inputs_workspace_path),
        "--out_dir",
        str(candidate_output_root),
        "--ticks",
        str(int(max(1, ticks_u64))),
        "--seed_u64",
        str(int(max(0, seed_u64))),
    ]
    candidate_proc = subprocess.run(
        candidate_cmd,
        cwd=candidate_workspace,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    stdout_relpath_raw = io_contract.get("stdout_relpath")
    stderr_relpath_raw = io_contract.get("stderr_relpath")
    if isinstance(stdout_relpath_raw, str) and stdout_relpath_raw.strip():
        stdout_relpath = _normalize_relpath(stdout_relpath_raw)
        stdout_path = candidate_output_root / stdout_relpath
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_path.write_text(str(candidate_proc.stdout or ""), encoding="utf-8")
    if isinstance(stderr_relpath_raw, str) and stderr_relpath_raw.strip():
        stderr_relpath = _normalize_relpath(stderr_relpath_raw)
        stderr_path = candidate_output_root / stderr_relpath
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.write_text(str(candidate_proc.stderr or ""), encoding="utf-8")

    after_hashes = _workspace_file_hashes(candidate_workspace)
    changed_paths = sorted(
        rel for rel in sorted(set(baseline_hashes.keys()) | set(after_hashes.keys())) if baseline_hashes.get(rel) != after_hashes.get(rel)
    )
    outside_output_changes = [row for row in changed_paths if not _prefix_match(row, output_root_relpath)]
    if outside_output_changes:
        raise CompositeRunnerError(
            "SUITE_IO_CONTRACT_VIOLATION",
            f"candidate wrote outside output root: {outside_output_changes[0]}",
        )

    output_files: list[dict[str, Any]] = []
    total_output_bytes_u64 = 0
    if candidate_output_root.exists() and candidate_output_root.is_dir():
        for path in sorted(candidate_output_root.rglob("*"), key=lambda row: row.as_posix()):
            if not path.exists() or not path.is_file():
                continue
            rel = _normalize_relpath(path.relative_to(candidate_output_root).as_posix())
            size_u64 = int(path.stat().st_size)
            digest = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
            total_output_bytes_u64 += int(size_u64)
            output_files.append({"path": rel, "sha256": digest, "bytes_u64": int(size_u64)})
    if len(output_files) > int(max_output_files_u64):
        raise CompositeRunnerError("SUITE_IO_CONTRACT_VIOLATION", "candidate output file count exceeded io contract")
    if int(total_output_bytes_u64) > int(max_output_bytes_u64):
        raise CompositeRunnerError("SUITE_IO_CONTRACT_VIOLATION", "candidate output size exceeded io contract")

    observed_output_paths = [str(row["path"]) for row in output_files]
    for rel in observed_output_paths:
        if rel not in set(allowed_output_files):
            raise CompositeRunnerError("SUITE_IO_CONTRACT_VIOLATION", f"unexpected output file: {rel}")
        if any(_prefix_match(rel, prefix) for prefix in forbidden_output_prefixes):
            raise CompositeRunnerError("SUITE_IO_CONTRACT_VIOLATION", f"forbidden output path: {rel}")
    for rel in required_output_files:
        if rel not in set(observed_output_paths):
            raise CompositeRunnerError("PREDICTIONS_MISSING_OR_MALFORMED", f"missing required output file: {rel}")
    for row in output_files:
        if int(row["bytes_u64"]) > int(max_single_output_bytes_u64):
            raise CompositeRunnerError(
                "SUITE_IO_CONTRACT_VIOLATION",
                f"output file exceeds max_single_output_bytes_u64: {row['path']}",
            )

    predictions_path = candidate_output_root / predictions_relpath
    if not predictions_path.exists() or not predictions_path.is_file():
        raise CompositeRunnerError("PREDICTIONS_MISSING_OR_MALFORMED", "predictions file is missing")
    prediction_rows = _jsonl_dict_rows(predictions_path)
    if not prediction_rows:
        raise CompositeRunnerError("PREDICTIONS_MISSING_OR_MALFORMED", "predictions file is empty")
    predictions_map: dict[str, str] = {}
    for row in prediction_rows:
        pred_id = str(row.get("id", "")).strip()
        if not pred_id:
            raise CompositeRunnerError("PREDICTIONS_MISSING_OR_MALFORMED", "prediction row is missing id")
        if pred_id in predictions_map:
            raise CompositeRunnerError("PREDICTIONS_MISSING_OR_MALFORMED", f"duplicate prediction id: {pred_id}")
        predictions_map[pred_id] = _prediction_value(row)

    truth_pack_id = suite.labels_pack_id or suite.hidden_tests_pack_id or ""
    truth_pack = labels_pack if labels_pack is not None else hidden_pack
    if not isinstance(truth_pack, dict):
        raise CompositeRunnerError("MISSING_STATE_INPUT", "holdout suite is missing labels/hidden truth pack")
    truth_rows_raw = truth_pack.get("rows")
    if not isinstance(truth_rows_raw, list) or not truth_rows_raw:
        raise CompositeRunnerError("SCHEMA_FAIL", "truth holdout pack rows are missing")
    truth_map: dict[str, str] = {}
    for row in truth_rows_raw:
        if not isinstance(row, dict):
            raise CompositeRunnerError("SCHEMA_FAIL", "truth row must be an object")
        row_id = str(row.get("id", "")).strip()
        if not row_id:
            raise CompositeRunnerError("SCHEMA_FAIL", "truth row id is missing")
        if row_id in truth_map:
            raise CompositeRunnerError("SCHEMA_FAIL", f"duplicate truth id: {row_id}")
        truth_map[row_id] = _truth_value(row)

    truth_total_u64 = int(len(truth_map))
    predicted_truth_u64 = int(sum(1 for row_id in truth_map if row_id in predictions_map))
    correct_u64 = int(sum(1 for row_id, truth_value in truth_map.items() if predictions_map.get(row_id) == truth_value))
    accuracy_q32 = int((correct_u64 * _Q32_ONE) // truth_total_u64) if truth_total_u64 > 0 else 0
    coverage_q32 = int((predicted_truth_u64 * _Q32_ONE) // truth_total_u64) if truth_total_u64 > 0 else 0

    min_accuracy_q32 = int(io_contract.get("min_accuracy_q32", 0))
    min_coverage_q32 = int(io_contract.get("min_coverage_q32", 0))
    candidate_exit_ok_b = candidate_proc.returncode == 0
    accuracy_pass_b = int(accuracy_q32) >= int(min_accuracy_q32)
    coverage_pass_b = int(coverage_q32) >= int(min_coverage_q32)

    gates = [
        {
            "gate_id": "CANDIDATE_EXIT_ZERO",
            "passed_b": bool(candidate_exit_ok_b),
            "detail": f"rc={int(candidate_proc.returncode)}",
        },
        {
            "gate_id": "IO_CONTRACT_ENFORCED",
            "passed_b": True,
            "detail": f"files={len(output_files)} total_bytes_u64={int(total_output_bytes_u64)}",
        },
        {
            "gate_id": "HOLDOUT_ACCURACY_MIN_Q32",
            "passed_b": bool(accuracy_pass_b),
            "detail": f"observed_q32={int(accuracy_q32)} threshold_q32={int(min_accuracy_q32)}",
        },
        {
            "gate_id": "HOLDOUT_COVERAGE_MIN_Q32",
            "passed_b": bool(coverage_pass_b),
            "detail": f"observed_q32={int(coverage_q32)} threshold_q32={int(min_coverage_q32)}",
        },
    ]
    suite_outcome = "PASS" if candidate_exit_ok_b and accuracy_pass_b and coverage_pass_b else "FAIL"
    metrics = {
        "holdout_accuracy_q32": {"q": int(accuracy_q32)},
        "holdout_coverage_q32": {"q": int(coverage_q32)},
    }
    candidate_outputs_hash = canon_hash_obj(
        {
            "schema_version": "holdout_candidate_outputs_v1",
            "files": output_files,
            "total_bytes_u64": int(total_output_bytes_u64),
        }
    )
    holdout_execution = {
        "holdout_policy_id": policy_holdout_id,
        "inputs_pack_id": str(suite.inputs_pack_id),
        "labels_pack_id": str(suite.labels_pack_id) if suite.labels_pack_id else None,
        "hidden_tests_pack_id": str(suite.hidden_tests_pack_id) if suite.hidden_tests_pack_id else None,
        "harness_truth_pack_id": str(truth_pack_id),
        "candidate_workspace_tree_id": compute_workspace_tree_id(candidate_workspace),
        "candidate_outputs_hash": str(candidate_outputs_hash),
        "candidate_outputs_bytes_u64": int(total_output_bytes_u64),
        "candidate_output_files": output_files,
        "predictions_relpath": predictions_relpath,
        "predictions_rows_u64": int(len(prediction_rows)),
        "harness_truth_rows_u64": int(truth_total_u64),
        "io_contract_enforced_b": True,
        "sandbox_available_b": bool(sandbox_available_b),
        "sandbox_enforced_b": bool(sandbox_enforced_b),
        "candidate_stage_status": "PASS" if candidate_exit_ok_b else "FAIL",
        "harness_stage_status": "PASS" if accuracy_pass_b and coverage_pass_b else "FAIL",
        "gates": gates,
    }
    holdout_execution = {key: value for key, value in holdout_execution.items() if value is not None}
    return suite_outcome, metrics, gates, holdout_execution


def _aggregate_metrics(executed_suites: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    buckets: dict[str, list[int]] = {}
    for row in executed_suites:
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            continue
        for metric_id, metric_value in sorted(metrics.items(), key=lambda kv: str(kv[0])):
            if not isinstance(metric_value, dict) or set(metric_value.keys()) != {"q"}:
                continue
            buckets.setdefault(str(metric_id), []).append(int(metric_value.get("q", 0)))
    out: dict[str, dict[str, int]] = {}
    for metric_id in sorted(buckets.keys()):
        values = buckets[metric_id]
        if not values:
            continue
        out[metric_id] = {"q": int(sum(values) // len(values))}
    return out


def run_composite_once(
    *,
    repo_root: Path,
    runs_root: Path,
    series_prefix: str,
    ek_id: str,
    anchor_suite_set_id: str,
    extensions_ledger_id: str,
    suite_runner_id: str,
    holdout_policy_id: str | None = None,
    ticks_u64: int,
    seed_u64: int,
) -> dict[str, Any]:
    resolved_repo_root = Path(repo_root).resolve()
    effective_suites = resolve_effective_suites(
        repo_root=resolved_repo_root,
        ek_id=ek_id,
        anchor_suite_set_id=anchor_suite_set_id,
        extensions_ledger_id=extensions_ledger_id,
    )
    if not effective_suites:
        raise CompositeRunnerError("EK_SUITE_LIST_MISMATCH", "effective suite list is empty")
    has_holdout_suites = any(str(row.suite_visibility).upper() == "HOLDOUT" for row in effective_suites)
    resolved_holdout_policy_id = ""
    holdout_policy: dict[str, Any] | None = None
    if has_holdout_suites:
        if not isinstance(holdout_policy_id, str) or not holdout_policy_id.strip():
            raise CompositeRunnerError("HOLDOUT_POLICY_PIN_MISMATCH", "holdout suites require holdout_policy_id")
        resolved_holdout_policy_id = _ensure_sha256(holdout_policy_id, field="holdout_policy_id")
        holdout_policy = _load_holdout_policy(
            repo_root=resolved_repo_root,
            holdout_policy_id=resolved_holdout_policy_id,
        )

    run_dir = Path(runs_root).resolve() / str(series_prefix)
    run_dir.mkdir(parents=True, exist_ok=True)
    suite_runs_root = run_dir / "suite_runs"
    suite_runs_root.mkdir(parents=True, exist_ok=True)

    executed_suites: list[dict[str, Any]] = []
    total_wall_ms = 0
    total_cpu_ms = 0
    for idx, suite in enumerate(effective_suites):
        suite_series_prefix = f"suite_{idx:03d}"
        suite_root = suite_runs_root / suite_series_prefix
        suite_root.mkdir(parents=True, exist_ok=True)
        suite_start_cpu = time.process_time()
        suite_start_wall = time.time()
        holdout_execution: dict[str, Any] | None = None
        if str(suite.suite_visibility).upper() == "HOLDOUT":
            if not isinstance(holdout_policy, dict):
                raise CompositeRunnerError("HOLDOUT_POLICY_PIN_MISMATCH", "holdout suites require a loaded holdout policy")
            try:
                outcome, metrics, gate_results, holdout_execution = _run_holdout_suite(
                    repo_root=resolved_repo_root,
                    suite=suite,
                    suite_runs_root=suite_root,
                    suite_series_prefix=suite_series_prefix,
                    ticks_u64=ticks_u64,
                    seed_u64=seed_u64,
                    holdout_policy=holdout_policy,
                )
            except CompositeRunnerError as exc:
                zero_sha = "sha256:" + ("0" * 64)
                outcome = "FAIL"
                metrics = {}
                gate_results = [
                    {
                        "gate_id": "HOLDOUT_FAIL_CLOSED",
                        "passed_b": False,
                        "detail": f"{exc.code}:{exc.detail}",
                    }
                ]
                holdout_execution = {
                    "holdout_policy_id": resolved_holdout_policy_id or zero_sha,
                    "inputs_pack_id": str(suite.inputs_pack_id or zero_sha),
                    "labels_pack_id": str(suite.labels_pack_id) if suite.labels_pack_id else None,
                    "hidden_tests_pack_id": str(suite.hidden_tests_pack_id) if suite.hidden_tests_pack_id else None,
                    "harness_truth_pack_id": str(suite.labels_pack_id or suite.hidden_tests_pack_id or zero_sha),
                    "candidate_workspace_tree_id": zero_sha,
                    "candidate_outputs_hash": zero_sha,
                    "candidate_outputs_bytes_u64": 0,
                    "candidate_output_files": [],
                    "predictions_relpath": (
                        str((suite.io_contract or {}).get("predictions_relpath", "predictions.jsonl"))
                        if isinstance(suite.io_contract, dict)
                        else "predictions.jsonl"
                    ),
                    "predictions_rows_u64": 0,
                    "harness_truth_rows_u64": 0,
                    "io_contract_enforced_b": False,
                    "sandbox_available_b": _sandbox_available_for_holdout(),
                    "sandbox_enforced_b": False,
                    "candidate_stage_status": "FAIL",
                    "harness_stage_status": "SKIPPED",
                    "gates": list(gate_results),
                }
                holdout_execution = {key: value for key, value in holdout_execution.items() if value is not None}
        else:
            outcome, metrics, gate_results = _run_legacy_suite(
                repo_root=resolved_repo_root,
                suite=suite,
                suite_runs_root=suite_root,
                suite_series_prefix=suite_series_prefix,
                ticks_u64=ticks_u64,
                seed_u64=seed_u64,
            )
        wall_ms = int(max(0, round((time.time() - suite_start_wall) * 1000.0)))
        cpu_ms = int(max(0, round((time.process_time() - suite_start_cpu) * 1000.0)))
        total_wall_ms += wall_ms
        total_cpu_ms += cpu_ms
        suite_row: dict[str, Any] = {
            "suite_id": suite.suite_id,
            "suite_name": suite.suite_name,
            "suite_set_id": suite.suite_set_id,
            "suite_source": suite.suite_source,
            "suite_visibility": suite.suite_visibility,
            "ledger_ordinal_u64": int(suite.ledger_ordinal_u64),
            "suite_outcome": str(outcome),
            "metrics": dict(metrics),
            "gate_results": list(gate_results),
            "budget_outcome": _suite_budget_outcome(wall_ms_u64=wall_ms, cpu_ms_u64=cpu_ms),
        }
        if isinstance(holdout_execution, dict):
            suite_row["holdout_execution"] = dict(holdout_execution)
        executed_suites.append(suite_row)

    executed_suite_ids = [str(row["suite_id"]) for row in executed_suites]
    effective_suite_ids = [row.suite_id for row in effective_suites]
    if executed_suite_ids != effective_suite_ids:
        raise CompositeRunnerError("EK_SUITE_LIST_MISMATCH", "executed suite order does not match effective suite order")

    aggregate_metrics = _aggregate_metrics(executed_suites)
    all_pass_b = all(str(row.get("suite_outcome", "")).strip().upper() == "PASS" for row in executed_suites)

    payload_no_id = {
        "schema_version": "benchmark_run_receipt_v2",
        "receipt_id": "sha256:" + ("0" * 64),
        "ek_id": _ensure_sha256(ek_id, field="ek_id"),
        "anchor_suite_set_id": _ensure_sha256(anchor_suite_set_id, field="anchor_suite_set_id"),
        "extensions_ledger_id": _ensure_sha256(extensions_ledger_id, field="extensions_ledger_id"),
        "suite_runner_id": _ensure_sha256(suite_runner_id, field="suite_runner_id"),
        "executed_suites": executed_suites,
        "effective_suite_ids": effective_suite_ids,
        "aggregate_metrics": aggregate_metrics,
        "gate_results": [
            {
                "gate_id": "ALL_SUITES_PASS",
                "passed_b": bool(all_pass_b),
                "detail": f"executed={len(executed_suites)}",
            }
        ],
        "budget_outcome": {
            "within_budget_b": True,
            "cpu_ms_u64": int(max(0, total_cpu_ms)),
            "wall_ms_u64": int(max(0, total_wall_ms)),
            "disk_mb_u64": 0,
        },
    }
    if resolved_holdout_policy_id:
        payload_no_id["holdout_policy_id"] = resolved_holdout_policy_id
    payload = dict(payload_no_id)
    payload_no_receipt_id = dict(payload_no_id)
    payload_no_receipt_id.pop("receipt_id", None)
    payload["receipt_id"] = canon_hash_obj(payload_no_receipt_id)

    write_canon_json(run_dir / "BENCHMARK_RUN_RECEIPT_v2.json", payload)

    median_stps_non_noop_q32 = int((aggregate_metrics.get("median_stps_non_noop_q32") or {}).get("q", 0))
    non_noop_ticks_per_min_q32 = int((aggregate_metrics.get("non_noop_ticks_per_min_q32") or {}).get("q", 0))
    promotions_u64 = int(sum(1 for row in executed_suites if str(row.get("suite_outcome", "")).strip().upper() == "PASS"))
    scorecard_payload = {
        "median_stps_non_noop_q32": int(max(0, median_stps_non_noop_q32)),
        "non_noop_ticks_per_min": float(max(0.0, float(non_noop_ticks_per_min_q32) / float(_Q32_ONE))),
        "promotions_u64": int(max(0, promotions_u64)),
        "activation_success_u64": int(max(0, promotions_u64)),
    }
    _write_json(run_dir / "OMEGA_RUN_SCORECARD_v1.json", scorecard_payload)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="omega_benchmark_suite_composite_v1")
    parser.add_argument("--mode", default="composite_once")
    parser.add_argument("--repo_root", default=str(_REPO_ROOT))
    parser.add_argument("--ticks", type=int, required=True)
    parser.add_argument("--seed_u64", type=int, required=True)
    parser.add_argument("--series_prefix", required=True)
    parser.add_argument("--runs_root", required=True)
    parser.add_argument("--ek_id", required=True)
    parser.add_argument("--anchor_suite_set_id", required=True)
    parser.add_argument("--extensions_ledger_id", required=True)
    parser.add_argument("--suite_runner_id", required=True)
    parser.add_argument("--holdout_policy_id", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if str(args.mode).strip() != "composite_once":
        print("INVALID:MODE_UNSUPPORTED")
        return 1
    try:
        receipt = run_composite_once(
            repo_root=Path(str(args.repo_root)),
            runs_root=Path(str(args.runs_root)),
            series_prefix=str(args.series_prefix),
            ek_id=str(args.ek_id),
            anchor_suite_set_id=str(args.anchor_suite_set_id),
            extensions_ledger_id=str(args.extensions_ledger_id),
            suite_runner_id=str(args.suite_runner_id),
            holdout_policy_id=str(args.holdout_policy_id).strip() or None,
            ticks_u64=int(max(1, int(args.ticks))),
            seed_u64=int(max(0, int(args.seed_u64))),
        )
    except CompositeRunnerError as exc:
        print(f"INVALID:{exc.code}")
        print(f"DETAIL:{exc.detail}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print("INVALID:EVAL_STAGE_FAIL")
        print(f"DETAIL:{str(exc) or 'composite runner failed'}")
        return 1

    all_pass = all(str(row.get("suite_outcome", "")).strip().upper() == "PASS" for row in receipt.get("executed_suites", []))
    print("VALID" if all_pass else "INVALID:SUITE_FAILURE")
    return 0 if all_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
