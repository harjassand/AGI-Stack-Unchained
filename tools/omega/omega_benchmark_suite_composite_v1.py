#!/usr/bin/env python3
"""Deterministic composite benchmark suite runner for evaluation_kernel_v2."""

from __future__ import annotations

import argparse
import json
import os
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
        out.append(
            EffectiveSuite(
                suite_id=suite_id,
                suite_name=suite_name,
                suite_set_id=_ensure_sha256(suite_set.get("suite_set_id"), field="suite_set_id"),
                suite_source=suite_source,
                ledger_ordinal_u64=int(max(0, ledger_ordinal_u64)),
                suite_runner_relpath=runner_relpath,
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
        executed_suites.append(
            {
                "suite_id": suite.suite_id,
                "suite_name": suite.suite_name,
                "suite_set_id": suite.suite_set_id,
                "suite_source": suite.suite_source,
                "ledger_ordinal_u64": int(suite.ledger_ordinal_u64),
                "suite_outcome": str(outcome),
                "metrics": dict(metrics),
                "gate_results": list(gate_results),
                "budget_outcome": _suite_budget_outcome(wall_ms_u64=wall_ms, cpu_ms_u64=cpu_ms),
            }
        )

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
