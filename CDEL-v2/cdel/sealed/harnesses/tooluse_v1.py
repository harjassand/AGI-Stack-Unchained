"""Tool-use harness for sealed evaluation."""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from blake3 import blake3

from cdel.kernel.eval import Evaluator, EvalError, FunVal, IntVal, Value
from cdel.sealed.suites import compute_suite_hash_bytes

HARNESS_ID = "tooluse-harness-v1"
HARNESS_HASH = "tooluse-harness-v1-hash"

_LAST_TOKEN = "$LAST"
_FILE_SIZE_LIMIT_BYTES = 1024 * 1024

_TOOL_NAMES = {
    "read_file",
    "write_file",
    "list_dir",
    "regex_search",
    "json_parse",
}


@dataclass(frozen=True)
class _ToolCall:
    tool: str
    args: list[str]


@dataclass(frozen=True)
class _EpisodeSpec:
    task_id: str
    max_steps: int
    allowed_tools: list[str]
    initial_fs: list[dict]
    tool_calls: list[_ToolCall]
    success: dict


class ToolUseHarness:
    harness_id = HARNESS_ID
    harness_hash = HARNESS_HASH

    def run_episodes(
        self,
        *,
        eval_cfg: dict,
        defs_env: dict[str, object],
        baseline_symbol: str,
        candidate_symbol: str,
        oracle_symbol: str,
        seed_key: bytes,
        project_root: Path,
        int_min: int,
        int_max: int,
        list_max_len: int,
        fun_symbols: list[str],
        artifact_dir: Path | None,
    ) -> tuple[list[int], int, int, bytes]:
        _ = (oracle_symbol, seed_key, int_min, int_max, list_max_len, fun_symbols)
        episodes = eval_cfg["episodes"]
        max_steps = eval_cfg["max_steps"]
        eval_suite_hash = eval_cfg["eval_suite_hash"]

        suites_dir = os.environ.get("CDEL_SUITES_DIR")
        if suites_dir:
            suite_path = Path(suites_dir) / f"{eval_suite_hash}.jsonl"
        else:
            suite_path = project_root / "sealed_suites" / f"{eval_suite_hash}.jsonl"
        try:
            suite_bytes = suite_path.read_bytes()
        except OSError as exc:
            raise ValueError(f"suite file not found: {suite_path}") from exc

        actual_hash = compute_suite_hash_bytes(suite_bytes)
        if actual_hash != eval_suite_hash:
            raise ValueError("suite hash mismatch")

        rows = _parse_suite_rows(suite_bytes)
        if len(rows) < episodes:
            raise ValueError("suite has fewer episodes than requested")

        baseline_successes = 0
        candidate_successes = 0
        diffs: list[int] = []
        artifact_rows: list[dict] | None = [] if artifact_dir is not None else None
        transcript_rows: list[dict] = []

        for episode in range(episodes):
            spec = rows[episode]
            baseline_success, baseline_info, baseline_trace = _run_policy(
                baseline_symbol,
                defs_env,
                spec,
                max_steps,
            )
            candidate_success, candidate_info, candidate_trace = _run_policy(
                candidate_symbol,
                defs_env,
                spec,
                max_steps,
            )
            if baseline_success:
                baseline_successes += 1
            if candidate_success:
                candidate_successes += 1
            diff = int(candidate_success) - int(baseline_success)
            diffs.append(diff)
            transcript_rows.append(
                {
                    "episode": episode,
                    "task_id": spec.task_id,
                    "diff": diff,
                    "baseline": baseline_trace,
                    "candidate": candidate_trace,
                }
            )
            if artifact_rows is not None:
                artifact_rows.append(
                    {
                        "episode": episode,
                        "task_id": spec.task_id,
                        "baseline_success": baseline_success,
                        "candidate_success": candidate_success,
                        "baseline_steps": baseline_info["steps"],
                        "candidate_steps": candidate_info["steps"],
                        "baseline_error": baseline_info.get("error"),
                        "candidate_error": candidate_info.get("error"),
                        "baseline_error_detail": baseline_info.get("detail"),
                        "candidate_error_detail": candidate_info.get("detail"),
                        "baseline_termination": baseline_info.get("termination"),
                        "candidate_termination": candidate_info.get("termination"),
                        "diff": diff,
                    }
                )

        transcript_bytes = _encode_transcript(eval_suite_hash, episodes, diffs, transcript_rows)
        if artifact_dir is not None:
            transcript_hash = blake3(transcript_bytes).hexdigest()
            _write_artifact(artifact_dir, transcript_hash, artifact_rows or [])

        return diffs, baseline_successes, candidate_successes, transcript_bytes


def _parse_suite_rows(suite_bytes: bytes) -> list[_EpisodeSpec]:
    rows: list[_EpisodeSpec] = []
    for line in suite_bytes.splitlines():
        if not line:
            continue
        payload = json.loads(line.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("suite row must be object")
        task_id = payload.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("suite task_id must be string")
        max_steps = payload.get("max_steps")
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps <= 0:
            raise ValueError("suite max_steps must be positive int")
        allowed_tools_raw = payload.get("allowed_tools")
        if not isinstance(allowed_tools_raw, list) or any(
            not isinstance(item, str) or item not in _TOOL_NAMES for item in allowed_tools_raw
        ):
            raise ValueError("suite allowed_tools must be list of tool names")
        initial_fs = payload.get("initial_fs", [])
        if not isinstance(initial_fs, list):
            raise ValueError("suite initial_fs must be list")
        tool_calls_raw = payload.get("tool_calls")
        if not isinstance(tool_calls_raw, list) or not tool_calls_raw:
            raise ValueError("suite tool_calls must be non-empty list")
        tool_calls: list[_ToolCall] = []
        for call in tool_calls_raw:
            if not isinstance(call, dict):
                raise ValueError("suite tool_call must be object")
            tool = call.get("tool")
            args = call.get("args", [])
            if not isinstance(tool, str) or tool not in allowed_tools_raw:
                raise ValueError("suite tool_call tool not allowed")
            if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
                raise ValueError("suite tool_call args must be list of strings")
            tool_calls.append(_ToolCall(tool=tool, args=list(args)))
        success = payload.get("success")
        if not isinstance(success, dict):
            raise ValueError("suite success must be object")
        rows.append(
            _EpisodeSpec(
                task_id=task_id,
                max_steps=max_steps,
                allowed_tools=list(allowed_tools_raw),
                initial_fs=list(initial_fs),
                tool_calls=tool_calls,
                success=success,
            )
        )
    return rows


def _run_policy(
    symbol: str,
    defs_env: dict[str, object],
    spec: _EpisodeSpec,
    max_steps_eval: int,
) -> tuple[bool, dict, list[dict]]:
    vm = _ToolVM.from_initial_fs(spec.initial_fs, allowed_tools=set(spec.allowed_tools))
    trace: list[dict] = []
    last_result = b""
    last_ok = True
    info: dict[str, object] = {"steps": 0, "termination": "stop"}

    for step in range(spec.max_steps):
        obs = {"step": step, "last_ok": 1 if last_ok else 0, "last_len": len(last_result)}
        obs_bytes = _canonical_bytes(obs)
        action = _safe_action(symbol, obs, defs_env, max_steps_eval)
        action_bytes = _canonical_bytes({"action": action})

        if action is None:
            info.update({"steps": step, "termination": "eval_error", "error": "eval_error"})
            trace.append(_step_record(obs_bytes, action_bytes, b"", b"", "eval_error"))
            return False, info, trace

        if action < 0:
            info.update({"steps": step, "termination": "stop"})
            trace.append(_step_record(obs_bytes, action_bytes, b"", b"", "stop"))
            break

        if action >= len(spec.tool_calls):
            info.update({"steps": step, "termination": "invalid_action", "error": "invalid_action"})
            trace.append(_step_record(obs_bytes, action_bytes, b"", b"", "invalid_action"))
            return False, info, trace

        call = spec.tool_calls[action]
        resolved_args = _resolve_args(call.args, last_result)
        tool_call_bytes = _canonical_bytes({"tool": call.tool, "args": resolved_args})
        ok, result_bytes, err_kind, err_detail = vm.call(call.tool, resolved_args)
        term = "ok" if ok else err_kind
        trace.append(_step_record(obs_bytes, action_bytes, tool_call_bytes, result_bytes, term))
        info["steps"] = step + 1
        if not ok:
            info.update({"termination": term, "error": err_kind, "detail": err_detail})
            return False, info, trace
        last_result = result_bytes
        last_ok = True
    else:
        info.update({"termination": "timeout", "error": "timeout"})
        timeout_obs = _canonical_bytes(
            {"step": spec.max_steps, "last_ok": 1 if last_ok else 0, "last_len": len(last_result)}
        )
        trace.append(_step_record(timeout_obs, _canonical_bytes({"action": None}), b"", b"", "timeout"))
        return False, info, trace

    success = _check_success(vm, spec.success)
    if not success:
        info.setdefault("termination", "stop")
    return bool(success), info, trace


def _safe_action(symbol: str, obs: dict, defs_env: dict, max_steps: int) -> int | None:
    evaluator = Evaluator(max_steps)
    args = [IntVal(int(obs["step"])), IntVal(int(obs["last_ok"])), IntVal(int(obs["last_len"]))]
    try:
        result = evaluator._apply(FunVal(symbol), args, defs_env)
    except EvalError:
        return None
    if not isinstance(result, IntVal):
        return None
    return int(result.value)


def _resolve_args(args: list[str], last_result: bytes) -> list[str]:
    if not args:
        return []
    last_text = last_result.decode("utf-8", errors="replace")
    resolved: list[str] = []
    for item in args:
        resolved.append(last_text if item == _LAST_TOKEN else item)
    return resolved


def _check_success(vm: "_ToolVM", success: dict) -> bool:
    kind = success.get("type")
    if kind == "file_equals":
        path = success.get("path")
        contents = success.get("contents")
        if not isinstance(path, str) or not isinstance(contents, str):
            return False
        data = vm.read_file(path)
        return data is not None and data.decode("utf-8", errors="replace") == contents
    if kind == "file_exists":
        path = success.get("path")
        if not isinstance(path, str):
            return False
        return vm.read_file(path) is not None
    if kind == "regex_match":
        path = success.get("path")
        pattern = success.get("pattern")
        if not isinstance(path, str) or not isinstance(pattern, str):
            return False
        data = vm.read_file(path)
        if data is None:
            return False
        return re.search(pattern, data.decode("utf-8", errors="replace")) is not None
    return False


class _ToolVM:
    def __init__(self, *, fs: dict[str, bytes], allowed_tools: set[str]) -> None:
        self.fs = fs
        self.allowed_tools = allowed_tools

    @classmethod
    def from_initial_fs(cls, rows: list[dict], *, allowed_tools: set[str]) -> "_ToolVM":
        fs: dict[str, bytes] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("initial_fs entries must be objects")
            path = row.get("path")
            contents = row.get("contents", "")
            if not isinstance(path, str) or not isinstance(contents, str):
                raise ValueError("initial_fs path/contents must be strings")
            rel = _sanitize_path(path)
            fs[rel] = contents.encode("utf-8")
        return cls(fs=fs, allowed_tools=allowed_tools)

    def call(self, tool: str, args: list[str]) -> tuple[bool, bytes, str, str | None]:
        if tool not in self.allowed_tools:
            return False, b"", "security_violation", "tool_not_allowed"
        if tool == "read_file":
            return self._read_file(args)
        if tool == "write_file":
            return self._write_file(args)
        if tool == "list_dir":
            return self._list_dir(args)
        if tool == "regex_search":
            return self._regex_search(args)
        if tool == "json_parse":
            return self._json_parse(args)
        return False, b"", "tool_error", "unknown_tool"

    def read_file(self, path: str) -> bytes | None:
        try:
            rel = _sanitize_path(path)
        except ValueError:
            return None
        return self.fs.get(rel)

    def _read_file(self, args: list[str]) -> tuple[bool, bytes, str, str | None]:
        if len(args) != 1:
            return False, b"", "tool_error", "read_file_bad_args"
        try:
            rel = _sanitize_path(args[0])
        except ValueError as exc:
            return False, b"", "security_violation", str(exc)
        data = self.fs.get(rel)
        if data is None:
            return False, b"", "tool_error", "missing_file"
        return True, data, "", None

    def _write_file(self, args: list[str]) -> tuple[bool, bytes, str, str | None]:
        if len(args) != 2:
            return False, b"", "tool_error", "write_file_bad_args"
        try:
            rel = _sanitize_path(args[0])
        except ValueError as exc:
            return False, b"", "security_violation", str(exc)
        data = args[1].encode("utf-8")
        if len(data) > _FILE_SIZE_LIMIT_BYTES:
            return False, b"", "tool_error", "file_too_large"
        self.fs[rel] = data
        return True, b"", "", None

    def _list_dir(self, args: list[str]) -> tuple[bool, bytes, str, str | None]:
        if len(args) != 1:
            return False, b"", "tool_error", "list_dir_bad_args"
        try:
            rel = _sanitize_path(args[0]) if args[0] else "."
        except ValueError as exc:
            return False, b"", "security_violation", str(exc)
        prefix = "" if rel in (".", "") else f"{rel}/"
        entries: set[str] = set()
        for path in self.fs:
            if not path.startswith(prefix):
                continue
            rest = path[len(prefix) :]
            if "/" in rest:
                entries.add(rest.split("/", 1)[0])
            elif rest:
                entries.add(rest)
        listing = "\n".join(sorted(entries)).encode("utf-8")
        return True, listing, "", None

    def _regex_search(self, args: list[str]) -> tuple[bool, bytes, str, str | None]:
        if len(args) != 2:
            return False, b"", "tool_error", "regex_bad_args"
        text, pattern = args
        try:
            match = re.search(pattern, text)
        except re.error as exc:
            return False, b"", "tool_error", str(exc)
        out = match.group(0) if match else ""
        return True, out.encode("utf-8"), "", None

    def _json_parse(self, args: list[str]) -> tuple[bool, bytes, str, str | None]:
        if len(args) != 1:
            return False, b"", "tool_error", "json_parse_bad_args"
        try:
            obj = json.loads(args[0])
        except json.JSONDecodeError as exc:
            return False, b"", "tool_error", str(exc)
        return True, _canonical_bytes(obj), "", None


def _sanitize_path(path: str) -> str:
    if not path or path.startswith("/") or path.startswith("~"):
        raise ValueError("absolute paths not allowed")
    parts = PurePosixPath(path).parts
    if ".." in parts:
        raise ValueError("parent traversal not allowed")
    return "/".join(parts)


def _encode_transcript(suite_hash: str, episodes: int, diffs: list[int], rows: list[dict]) -> bytes:
    payload = {
        "harness_id": HARNESS_ID,
        "suite_hash": suite_hash,
        "episodes": episodes,
        "diffs": diffs,
        "episodes_detail": rows,
    }
    return _canonical_bytes(payload)


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _step_record(
    obs_bytes: bytes,
    action_bytes: bytes,
    tool_call_bytes: bytes,
    result_bytes: bytes,
    termination: str,
) -> dict:
    return {
        "observation_b64": _b64(obs_bytes),
        "action_b64": _b64(action_bytes),
        "tool_call_b64": _b64(tool_call_bytes),
        "tool_result_b64": _b64(result_bytes),
        "termination": termination,
    }


def _b64(data: bytes) -> str:
    if not data:
        return ""
    return base64.b64encode(data).decode("ascii")


def _write_artifact(artifact_dir: Path, transcript_hash: str, rows: list[dict]) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{transcript_hash}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
