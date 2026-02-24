"""Deterministic hard-task suite for omega daemon v18.0."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re

from .omega_common_v1 import canon_hash_obj, rat_q32

_Q32_ONE = 1 << 32

HARD_TASK_SUITE_SCHEMA_NAME = "hard_task_suite_v1"
HARD_TASK_SUITE_SCHEMA_VERSION = "v1"
HARD_TASK_SUITE_TARGET_RELPATH = "orchestrator/omega_v18_0/goal_synthesizer_v1.py"
HARD_TASK_SUITE_NATIVE_TARGET_RELPATH = "CDEL-v2/cdel/v18_0/campaign_omega_native_module_v0_1.py"

HARD_TASK_METRIC_IDS: tuple[str, ...] = (
    "hard_task_code_correctness_q32",
    "hard_task_performance_q32",
    "hard_task_reasoning_q32",
    "hard_task_suite_score_q32",
)


@dataclass(frozen=True)
class _PatchHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class _PatchFile:
    relpath: str
    hunks: tuple[_PatchHunk, ...]


_DIFF_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


_SLUG_CASES: tuple[tuple[str, str], ...] = (
    ("Alpha  Beta", "alpha_beta"),
    ("A__B", "a_b"),
    ("A___B___C", "a_b_c"),
    ("___", "x"),
    ("A--B", "a_b"),
)

_GOAL_ID_CASES: tuple[dict[str, Any], ...] = (
    {
        "args": {
            "priority_prefix": "00",
            "reason_slug": "A__B",
            "capability_id": "RSI__OMEGA",
            "tick_u64": 7,
            "suffix_u64": 0,
        },
        "expected": "goal_auto_00_issue_a_b_rsi_omega_000007",
    },
    {
        "args": {
            "priority_prefix": "90",
            "reason_slug": "queue__floor",
            "capability_id": "RSI__CAP",
            "tick_u64": 42,
            "suffix_u64": 0,
        },
        "expected": "goal_auto_90_queue_floor_rsi_cap_000042",
    },
    {
        "args": {
            "priority_prefix": "CORE",
            "reason_slug": "hot__stage",
            "capability_id": "RSI_IGNORED",
            "tick_u64": 11,
            "suffix_u64": 0,
        },
        "expected": "goal_self_optimize_core_00_hot_stage_000011",
    },
)

_GOAL_ID_SUFFIX_CASES: tuple[dict[str, Any], ...] = (
    {
        "args": {
            "priority_prefix": "20",
            "reason_slug": "Kernel__Loop",
            "capability_id": "RSI__SAS__KERNEL",
            "tick_u64": 5,
            "suffix_u64": 2,
        },
        "expected": "goal_explore_20_family_kernel_loop_rsi_sas_kernel_000005_02",
    },
    {
        "args": {
            "priority_prefix": "10",
            "reason_slug": "runaway__blocked",
            "capability_id": "RSI__SAS__SYSTEM",
            "tick_u64": 13,
            "suffix_u64": 3,
        },
        "expected": "goal_auto_10_runaway_blocked_rsi_sas_system_000013_03",
    },
)

_NATIVE_PLATFORM_CASES: tuple[tuple[str, str], ...] = (
    ("Darwin", ".dylib"),
    ("Linux", ".so"),
    ("FreeBSD", ".so"),
)

_TASK_DEFINITIONS_V1: tuple[dict[str, Any], ...] = (
    {
        "task_id": "slug_canonicalization_accuracy",
        "target_relpath": HARD_TASK_SUITE_TARGET_RELPATH,
        "cases": [
            {"input": text, "expected": expected}
            for text, expected in _SLUG_CASES
        ],
    },
    {
        "task_id": "goal_id_route_quality",
        "target_relpath": HARD_TASK_SUITE_TARGET_RELPATH,
        "cases": [
            {
                "args": dict(row["args"]),
                "expected": str(row["expected"]),
            }
            for row in _GOAL_ID_CASES
        ],
    },
    {
        "task_id": "goal_id_suffix_consistency",
        "target_relpath": HARD_TASK_SUITE_TARGET_RELPATH,
        "cases": [
            {
                "args": dict(row["args"]),
                "expected": str(row["expected"]),
            }
            for row in _GOAL_ID_SUFFIX_CASES
        ],
    },
    {
        "task_id": "native_module_platform_portability",
        "target_relpath": HARD_TASK_SUITE_NATIVE_TARGET_RELPATH,
        "cases": [
            {"sysname": sysname, "expected": expected}
            for sysname, expected in _NATIVE_PLATFORM_CASES
        ],
    },
)

_TASK_ID_TO_METRIC_ID: dict[str, str] = {
    "slug_canonicalization_accuracy": HARD_TASK_METRIC_IDS[0],
    "goal_id_route_quality": HARD_TASK_METRIC_IDS[1],
    "native_module_platform_portability": HARD_TASK_METRIC_IDS[2],
}


def _normalize_relpath(path_value: str) -> str:
    rel = str(path_value).strip().replace("\\", "/").lstrip("./")
    path = Path(rel)
    if not rel or path.is_absolute() or ".." in path.parts:
        raise RuntimeError("SCHEMA_FAIL")
    return rel


def _parse_diff_relpath(raw: str) -> str:
    value = str(raw).strip()
    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        value = value[1:-1]
    return _normalize_relpath(value)


def _parse_unified_patch(patch_bytes: bytes) -> list[_PatchFile]:
    lines = patch_bytes.decode("utf-8", errors="replace").splitlines()
    rows: list[_PatchFile] = []
    current_relpath: str | None = None
    current_hunks: list[_PatchHunk] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if line.startswith("--- "):
            if idx + 1 >= len(lines) or not lines[idx + 1].startswith("+++ "):
                raise RuntimeError("PATCH_PARSE_FAILED")
            if current_relpath is not None:
                rows.append(_PatchFile(relpath=current_relpath, hunks=tuple(current_hunks)))
            current_hunks = []
            plus_line = lines[idx + 1][4:]
            if plus_line.strip() == "/dev/null":
                raise RuntimeError("PATCH_PARSE_FAILED")
            current_relpath = _parse_diff_relpath(plus_line)
            idx += 2
            continue
        if line.startswith("@@ "):
            if current_relpath is None:
                raise RuntimeError("PATCH_PARSE_FAILED")
            match = _DIFF_HUNK_RE.match(line)
            if match is None:
                raise RuntimeError("PATCH_PARSE_FAILED")
            old_start = int(match.group(1))
            old_count = int(match.group(2) or "1")
            new_start = int(match.group(3))
            new_count = int(match.group(4) or "1")
            hunk_lines: list[str] = []
            idx += 1
            while idx < len(lines):
                inner = lines[idx]
                if inner.startswith("@@ ") or inner.startswith("--- "):
                    break
                if inner.startswith("\\ No newline at end of file"):
                    idx += 1
                    continue
                if not inner or inner[0] not in {" ", "+", "-"}:
                    raise RuntimeError("PATCH_PARSE_FAILED")
                hunk_lines.append(inner)
                idx += 1
            current_hunks.append(
                _PatchHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=tuple(hunk_lines),
                )
            )
            continue
        idx += 1
    if current_relpath is not None:
        rows.append(_PatchFile(relpath=current_relpath, hunks=tuple(current_hunks)))
    if not rows:
        raise RuntimeError("PATCH_PARSE_FAILED")
    return rows


def _apply_patch_to_text(*, before_text: str, file_patch: _PatchFile) -> str:
    before_lines = before_text.splitlines(keepends=True)
    out: list[str] = []
    cursor = 0
    for hunk in file_patch.hunks:
        start_idx = max(0, int(hunk.old_start) - 1)
        if start_idx < cursor or start_idx > len(before_lines):
            raise RuntimeError("PATCH_APPLY_FAIL")
        out.extend(before_lines[cursor:start_idx])
        cursor = start_idx
        for raw in hunk.lines:
            prefix = raw[0]
            body = raw[1:]
            if prefix == " ":
                if cursor >= len(before_lines):
                    raise RuntimeError("PATCH_APPLY_FAIL")
                observed = before_lines[cursor].rstrip("\n")
                if observed != body:
                    raise RuntimeError("PATCH_APPLY_FAIL")
                out.append(before_lines[cursor])
                cursor += 1
            elif prefix == "-":
                if cursor >= len(before_lines):
                    raise RuntimeError("PATCH_APPLY_FAIL")
                observed = before_lines[cursor].rstrip("\n")
                if observed != body:
                    raise RuntimeError("PATCH_APPLY_FAIL")
                cursor += 1
            elif prefix == "+":
                out.append(body + "\n")
            else:
                raise RuntimeError("PATCH_PARSE_FAILED")
    out.extend(before_lines[cursor:])
    return "".join(out)


def hard_task_suite_definition_v1() -> dict[str, Any]:
    return {
        "schema_name": HARD_TASK_SUITE_SCHEMA_NAME,
        "schema_version": HARD_TASK_SUITE_SCHEMA_VERSION,
        "target_relpath": HARD_TASK_SUITE_TARGET_RELPATH,
        "tasks": [dict(task) for task in _TASK_DEFINITIONS_V1],
    }


def hard_task_suite_hash_v1() -> str:
    return canon_hash_obj(hard_task_suite_definition_v1())


def _source_text_with_patch(*, repo_root: Path, target_relpath: str, patch_bytes: bytes | None) -> str:
    target_relpath_norm = _normalize_relpath(target_relpath)
    target_path = (Path(repo_root).resolve() / target_relpath_norm).resolve()
    if not target_path.exists() or not target_path.is_file():
        raise RuntimeError("MISSING_STATE_INPUT")
    before_text = target_path.read_text(encoding="utf-8")
    if patch_bytes is None:
        return before_text
    file_patches = _parse_unified_patch(patch_bytes)
    after_text = before_text
    for file_patch in file_patches:
        if str(file_patch.relpath) != target_relpath_norm:
            continue
        after_text = _apply_patch_to_text(before_text=before_text, file_patch=file_patch)
        break
    return after_text


def _score_task_slug_canonicalization(namespace: dict[str, Any]) -> dict[str, Any]:
    task_id = "slug_canonicalization_accuracy"
    fn = namespace.get("_slug")
    if not callable(fn):
        return {
            "task_id": task_id,
            "score_q32": 0,
            "passed_u64": 0,
            "total_u64": int(len(_SLUG_CASES)),
            "error_code": "MISSING_SYMBOL:_slug",
        }
    passed = 0
    for text, expected in _SLUG_CASES:
        try:
            observed = str(fn(text))
        except Exception:
            observed = "<error>"
        if observed == expected:
            passed += 1
    total = max(1, len(_SLUG_CASES))
    return {
        "task_id": task_id,
        "score_q32": int(rat_q32(passed, total)),
        "passed_u64": int(passed),
        "total_u64": int(total),
    }


def _score_task_goal_id_route_quality(namespace: dict[str, Any]) -> dict[str, Any]:
    task_id = "goal_id_route_quality"
    fn = namespace.get("_goal_id_for")
    if not callable(fn):
        return {
            "task_id": task_id,
            "score_q32": 0,
            "passed_u64": 0,
            "total_u64": int(len(_GOAL_ID_CASES)),
            "error_code": "MISSING_SYMBOL:_goal_id_for",
        }
    passed = 0
    for row in _GOAL_ID_CASES:
        args = dict(row["args"])
        expected = str(row["expected"])
        try:
            observed = str(fn(**args))
        except Exception:
            observed = "<error>"
        if observed == expected:
            passed += 1
    total = max(1, len(_GOAL_ID_CASES))
    return {
        "task_id": task_id,
        "score_q32": int(rat_q32(passed, total)),
        "passed_u64": int(passed),
        "total_u64": int(total),
    }


def _score_task_goal_id_suffix_consistency(namespace: dict[str, Any]) -> dict[str, Any]:
    task_id = "goal_id_suffix_consistency"
    fn = namespace.get("_goal_id_for")
    if not callable(fn):
        return {
            "task_id": task_id,
            "score_q32": 0,
            "passed_u64": 0,
            "total_u64": int(len(_GOAL_ID_SUFFIX_CASES)),
            "error_code": "MISSING_SYMBOL:_goal_id_for",
        }
    passed = 0
    for row in _GOAL_ID_SUFFIX_CASES:
        args = dict(row["args"])
        expected = str(row["expected"])
        try:
            observed = str(fn(**args))
        except Exception:
            observed = "<error>"
        if observed == expected:
            passed += 1
    total = max(1, len(_GOAL_ID_SUFFIX_CASES))
    return {
        "task_id": task_id,
        "score_q32": int(rat_q32(passed, total)),
        "passed_u64": int(passed),
        "total_u64": int(total),
    }


def _score_task_native_module_platform_portability(namespace: dict[str, Any]) -> dict[str, Any]:
    task_id = "native_module_platform_portability"
    fn = namespace.get("_platform_ext")
    if not callable(fn):
        return {
            "task_id": task_id,
            "score_q32": 0,
            "passed_u64": 0,
            "total_u64": int(len(_NATIVE_PLATFORM_CASES)),
            "error_code": "MISSING_SYMBOL:_platform_ext",
        }

    class _FakeOS:
        def __init__(self, sysname: str) -> None:
            self._sysname = str(sysname)

        def uname(self) -> Any:
            return type("_UName", (), {"sysname": str(self._sysname)})()

    original_os = namespace.get("os")
    passed = 0
    try:
        for sysname, expected in _NATIVE_PLATFORM_CASES:
            namespace["os"] = _FakeOS(sysname)
            try:
                observed = str(fn())
            except Exception:
                observed = "<error>"
            if observed == expected:
                passed += 1
    finally:
        if original_os is None:
            namespace.pop("os", None)
        else:
            namespace["os"] = original_os

    total = max(1, len(_NATIVE_PLATFORM_CASES))
    return {
        "task_id": task_id,
        "score_q32": int(rat_q32(passed, total)),
        "passed_u64": int(passed),
        "total_u64": int(total),
    }


def evaluate_hard_task_suite_v1(*, repo_root: Path, patch_bytes: bytes | None = None) -> dict[str, Any]:
    suite_hash = hard_task_suite_hash_v1()
    try:
        goal_source_text = _source_text_with_patch(
            repo_root=repo_root,
            target_relpath=HARD_TASK_SUITE_TARGET_RELPATH,
            patch_bytes=patch_bytes,
        )
        native_source_text = _source_text_with_patch(
            repo_root=repo_root,
            target_relpath=HARD_TASK_SUITE_NATIVE_TARGET_RELPATH,
            patch_bytes=patch_bytes,
        )
        goal_namespace: dict[str, Any] = {"__name__": "hard_task_suite_goal_synth_eval"}
        native_namespace: dict[str, Any] = {"__name__": "hard_task_suite_native_module_eval"}
        exec(compile(goal_source_text, HARD_TASK_SUITE_TARGET_RELPATH, "exec"), goal_namespace, goal_namespace)
        exec(
            compile(native_source_text, HARD_TASK_SUITE_NATIVE_TARGET_RELPATH, "exec"),
            native_namespace,
            native_namespace,
        )
        task_rows = [
            _score_task_slug_canonicalization(goal_namespace),
            _score_task_goal_id_route_quality(goal_namespace),
            _score_task_goal_id_suffix_consistency(goal_namespace),
            _score_task_native_module_platform_portability(native_namespace),
        ]
        total_score_q32 = int(
            sum(int(row.get("score_q32", 0)) for row in task_rows) // max(1, len(task_rows))
        )
        status = "OK"
        error_code = None
    except Exception as exc:  # noqa: BLE001
        task_rows = [
            {
                "task_id": str(task["task_id"]),
                "score_q32": 0,
                "passed_u64": 0,
                "total_u64": int(len(task.get("cases", []))),
                "error_code": f"EVAL_ERROR:{type(exc).__name__}",
            }
            for task in _TASK_DEFINITIONS_V1
        ]
        total_score_q32 = 0
        status = "ERROR"
        error_code = f"EVAL_ERROR:{type(exc).__name__}"

    payload: dict[str, Any] = {
        "schema_name": HARD_TASK_SUITE_SCHEMA_NAME,
        "schema_version": HARD_TASK_SUITE_SCHEMA_VERSION,
        "suite_hash": suite_hash,
        "target_relpath": HARD_TASK_SUITE_TARGET_RELPATH,
        "status": status,
        "error_code": error_code,
        "task_count_u32": int(len(task_rows)),
        "tasks": task_rows,
        "total_score_q32": int(max(0, int(total_score_q32))),
    }
    return payload


def hard_task_metric_q32_by_id_from_suite(*, suite_eval: dict[str, Any]) -> dict[str, int]:
    rows = suite_eval.get("tasks")
    by_task: dict[str, int] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            task_id = str(row.get("task_id", "")).strip()
            if not task_id:
                continue
            by_task[task_id] = max(0, int(row.get("score_q32", 0)))
    out: dict[str, int] = {}
    for task_id, metric_id in sorted(_TASK_ID_TO_METRIC_ID.items(), key=lambda kv: str(kv[0])):
        out[metric_id] = int(max(0, by_task.get(task_id, 0)))
    out[HARD_TASK_METRIC_IDS[3]] = int(max(0, int(suite_eval.get("total_score_q32", 0))))
    return out


def evaluate_hard_task_patch_delta_v1(*, repo_root: Path, patch_bytes: bytes) -> dict[str, Any]:
    baseline = evaluate_hard_task_suite_v1(repo_root=repo_root)
    patched = evaluate_hard_task_suite_v1(repo_root=repo_root, patch_bytes=patch_bytes)
    baseline_score = int(max(0, int(baseline.get("total_score_q32", 0))))
    patched_score = int(max(0, int(patched.get("total_score_q32", 0))))

    baseline_metrics = hard_task_metric_q32_by_id_from_suite(suite_eval=baseline)
    patched_metrics = hard_task_metric_q32_by_id_from_suite(suite_eval=patched)
    delta_by_metric = {
        metric_id: int(patched_metrics.get(metric_id, 0)) - int(baseline_metrics.get(metric_id, 0))
        for metric_id in HARD_TASK_METRIC_IDS
    }

    return {
        "schema_name": "hard_task_patch_delta_v1",
        "suite_hash": str(baseline.get("suite_hash", "")),
        "baseline_total_score_q32": int(baseline_score),
        "patched_total_score_q32": int(patched_score),
        "predicted_delta_total_q32": int(patched_score - baseline_score),
        "predicted_delta_by_metric_q32": delta_by_metric,
        "baseline_suite_v1": baseline,
        "patched_suite_v1": patched,
    }


__all__ = [
    "HARD_TASK_METRIC_IDS",
    "HARD_TASK_SUITE_SCHEMA_NAME",
    "HARD_TASK_SUITE_SCHEMA_VERSION",
    "HARD_TASK_SUITE_TARGET_RELPATH",
    "evaluate_hard_task_patch_delta_v1",
    "evaluate_hard_task_suite_v1",
    "hard_task_metric_q32_by_id_from_suite",
    "hard_task_suite_definition_v1",
    "hard_task_suite_hash_v1",
]
