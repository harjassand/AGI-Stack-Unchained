"""Python unit-test harness for sealed evaluation."""

from __future__ import annotations

import json
import math
import os
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from blake3 import blake3

from cdel.kernel.eval import Evaluator, FunVal, IntVal, ListVal
from cdel.sealed.suites import compute_suite_hash_bytes

HARNESS_ID = "pyut-harness-v1"
HARNESS_HASH = "pyut-harness-v1-hash-2"

_TEST_TIMEOUT_S = 0.2
_CPU_TIME_LIMIT_S = max(1, int(math.ceil(_TEST_TIMEOUT_S)))
_MEMORY_LIMIT_BYTES = 256 * 1024 * 1024
_FILE_SIZE_LIMIT_BYTES = 1024 * 1024
_FD_LIMIT = 32
_PROC_LIMIT = 16
_MAX_STDOUT_BYTES = 4096
_MAX_STDERR_BYTES = 4096

_RUNNER_SRC = """\
import ast
import json
import sys

_ALLOWED_BUILTINS = {
    "abs": abs,
    "bool": bool,
    "Exception": Exception,
    "int": int,
    "min": min,
    "max": max,
    "len": len,
    "range": range,
}

_BANNED_NAMES = {
    "__builtins__",
    "__import__",
    "compile",
    "eval",
    "exec",
    "input",
    "open",
}

_CPU_TIME_LIMIT_S = __CPU_TIME_LIMIT_S__
_MEMORY_LIMIT_BYTES = __MEMORY_LIMIT_BYTES__
_FILE_SIZE_LIMIT_BYTES = __FILE_SIZE_LIMIT_BYTES__
_FD_LIMIT = __FD_LIMIT__
_PROC_LIMIT = __PROC_LIMIT__


def _apply_limits():
    try:
        import resource  # type: ignore
    except Exception:
        return False
    ok = True
    try:
        resource.setrlimit(resource.RLIMIT_AS, (_MEMORY_LIMIT_BYTES, _MEMORY_LIMIT_BYTES))
    except Exception:
        ok = False
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (_CPU_TIME_LIMIT_S, _CPU_TIME_LIMIT_S))
    except Exception:
        ok = False
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (_FILE_SIZE_LIMIT_BYTES, _FILE_SIZE_LIMIT_BYTES))
    except Exception:
        ok = False
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (_FD_LIMIT, _FD_LIMIT))
    except Exception:
        ok = False
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (_PROC_LIMIT, _PROC_LIMIT))
    except Exception:
        ok = False
    return ok


def _validate_source(src):
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return {"ok": False, "error": "SyntaxError", "message": str(exc)}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return {"ok": False, "error": "ImportBlocked", "message": "imports not allowed"}
        if isinstance(node, ast.Name) and node.id in _BANNED_NAMES:
            return {"ok": False, "error": "SecurityViolation", "message": f"blocked name: {node.id}"}
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return {"ok": False, "error": "SecurityViolation", "message": "dunder access blocked"}
    return None


def main():
    payload = json.load(sys.stdin)
    source = payload.get("source")
    fn_name = payload.get("fn_name")
    args = payload.get("args")
    expected = payload.get("expected")
    if not isinstance(source, str) or not isinstance(fn_name, str):
        print(json.dumps({"ok": False, "error": "BadInput"}))
        return
    if not isinstance(args, list):
        print(json.dumps({"ok": False, "error": "BadInput"}))
        return
    err = _validate_source(source)
    limits_applied = _apply_limits()
    if err:
        err["limits_applied"] = limits_applied
        print(json.dumps(err))
        return
    globals_dict = {"__builtins__": _ALLOWED_BUILTINS, "__name__": "__pyut__"}
    locals_dict = {}
    try:
        exec(compile(source, "<candidate>", "exec"), globals_dict, locals_dict)
        fn = globals_dict.get(fn_name) or locals_dict.get(fn_name)
        if not callable(fn):
            print(json.dumps({"ok": False, "error": "MissingFunction", "limits_applied": limits_applied}))
            return
        result = fn(*args)
        ok = result == expected
        out = {"ok": ok, "limits_applied": limits_applied}
        if not ok:
            out["error"] = "Mismatch"
            out["result_repr"] = repr(result)
        print(json.dumps(out))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": exc.__class__.__name__,
                    "message": str(exc),
                    "limits_applied": limits_applied,
                }
            )
        )


if __name__ == "__main__":
    main()
"""

_RUNNER_RENDERED = (
    _RUNNER_SRC.replace("__MEMORY_LIMIT_BYTES__", str(_MEMORY_LIMIT_BYTES))
    .replace("__CPU_TIME_LIMIT_S__", str(_CPU_TIME_LIMIT_S))
    .replace("__FILE_SIZE_LIMIT_BYTES__", str(_FILE_SIZE_LIMIT_BYTES))
    .replace("__FD_LIMIT__", str(_FD_LIMIT))
    .replace("__PROC_LIMIT__", str(_PROC_LIMIT))
)


@dataclass
class _LimitedRunResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool


class PyUTHarness:
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
        episodes = eval_cfg["episodes"]
        eval_suite_hash = eval_cfg["eval_suite_hash"]
        max_steps = eval_cfg["max_steps"]

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

        baseline_source, baseline_error = _eval_source_symbol(baseline_symbol, defs_env, max_steps)
        candidate_source, candidate_error = _eval_source_symbol(candidate_symbol, defs_env, max_steps)

        baseline_successes = 0
        candidate_successes = 0
        diffs: list[int] = []
        artifact_rows: list[dict] | None = [] if artifact_dir is not None else None

        for episode in range(episodes):
            spec = rows[episode]
            baseline_success, baseline_info = _run_episode(
                baseline_source,
                baseline_error,
                spec,
            )
            candidate_success, candidate_info = _run_episode(
                candidate_source,
                candidate_error,
                spec,
            )
            if baseline_success:
                baseline_successes += 1
            if candidate_success:
                candidate_successes += 1
            diff = int(candidate_success) - int(baseline_success)
            diffs.append(diff)
            if artifact_rows is not None:
                artifact_rows.append(
                    {
                        "episode": episode,
                        "task_id": spec["task_id"],
                        "baseline_success": baseline_success,
                        "candidate_success": candidate_success,
                        "baseline_failed_test": baseline_info.get("failed_test"),
                        "candidate_failed_test": candidate_info.get("failed_test"),
                        "baseline_timeout": baseline_info.get("timeout", False),
                        "candidate_timeout": candidate_info.get("timeout", False),
                        "baseline_error": baseline_info.get("error"),
                        "baseline_error_detail": baseline_info.get("detail"),
                        "baseline_message": baseline_info.get("message"),
                        "baseline_limits_applied": baseline_info.get("limits_applied"),
                        "baseline_output_truncated": baseline_info.get("output_truncated"),
                        "candidate_error": candidate_info.get("error"),
                        "candidate_error_detail": candidate_info.get("detail"),
                        "candidate_message": candidate_info.get("message"),
                        "candidate_limits_applied": candidate_info.get("limits_applied"),
                        "candidate_output_truncated": candidate_info.get("output_truncated"),
                        "diff": diff,
                    }
                )

        transcript_bytes = _encode_transcript(eval_suite_hash, episodes, diffs)
        if artifact_dir is not None:
            transcript_hash = blake3(transcript_bytes).hexdigest()
            _write_artifact(artifact_dir, transcript_hash, artifact_rows or [])

        return diffs, baseline_successes, candidate_successes, transcript_bytes


def _parse_suite_rows(suite_bytes: bytes) -> list[dict]:
    rows: list[dict] = []
    for line in suite_bytes.splitlines():
        if not line:
            continue
        payload = json.loads(line.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("suite row must be object")
        task_id = payload.get("task_id")
        fn_name = payload.get("fn_name")
        signature = payload.get("signature")
        tests = payload.get("tests")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("suite task_id must be string")
        if not isinstance(fn_name, str) or not fn_name or not fn_name.isidentifier():
            raise ValueError("suite fn_name must be identifier")
        if not isinstance(signature, str) or not signature:
            raise ValueError("suite signature must be string")
        if not isinstance(tests, list) or not tests:
            raise ValueError("suite tests must be non-empty list")
        parsed_tests: list[dict] = []
        for case in tests:
            if not isinstance(case, dict):
                raise ValueError("suite test case must be object")
            args = case.get("args")
            expected = case.get("expected")
            if not isinstance(args, list):
                raise ValueError("suite test args must be list")
            for arg in args:
                _validate_py_value(arg)
            _validate_py_value(expected)
            parsed_tests.append({"args": args, "expected": expected})
        rows.append(
            {
                "task_id": task_id,
                "fn_name": fn_name,
                "signature": signature,
                "tests": parsed_tests,
            }
        )
    return rows


def _validate_py_value(value: object) -> None:
    if value is None:
        raise ValueError("suite values must not be null")
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        raise ValueError("suite values must not be float")
    if isinstance(value, str):
        return
    if isinstance(value, list):
        for item in value:
            _validate_py_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("suite dict keys must be strings")
            _validate_py_value(item)
        return
    raise ValueError("suite values must be JSON primitives")


def _eval_source_symbol(symbol: str, defs: dict[str, object], max_steps: int) -> tuple[str | None, str | None]:
    evaluator = Evaluator(max_steps)
    try:
        value = evaluator._apply(FunVal(symbol), [], defs)
    except Exception as exc:
        return None, f"eval_error:{exc}"
    if not isinstance(value, ListVal):
        return None, "code must be list"
    chars: list[int] = []
    for item in value.items:
        if not isinstance(item, IntVal):
            return None, "code list must contain ints"
        if item.value < 0 or item.value > 127:
            return None, "code byte out of range"
        chars.append(item.value)
    try:
        source = bytes(chars).decode("ascii")
    except UnicodeDecodeError:
        return None, "code decode failed"
    if not source.strip():
        return None, "code empty"
    return source, None


def _run_episode(source: str | None, source_error: str | None, spec: dict) -> tuple[bool, dict]:
    if source is None:
        return False, {"ok": False, "error": source_error or "missing_source"}
    tests = spec["tests"]
    fn_name = spec["fn_name"]
    for idx, case in enumerate(tests):
        result = _run_test_case(source, fn_name, case["args"], case["expected"])
        if not result.get("ok"):
            result["failed_test"] = idx
            return False, result
    return True, {"ok": True}


def _sandbox_env(tmpdir: Path) -> dict[str, str]:
    return {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "PYTHONHASHSEED": "0",
        "PYTHONIOENCODING": "utf-8",
        "HOME": str(tmpdir),
    }


def _preexec_set_limits() -> None:
    try:
        import resource  # type: ignore
    except Exception:
        return
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (_CPU_TIME_LIMIT_S, _CPU_TIME_LIMIT_S))
    except Exception:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_AS, (_MEMORY_LIMIT_BYTES, _MEMORY_LIMIT_BYTES))
    except Exception:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (_FILE_SIZE_LIMIT_BYTES, _FILE_SIZE_LIMIT_BYTES))
    except Exception:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (_FD_LIMIT, _FD_LIMIT))
    except Exception:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (_PROC_LIMIT, _PROC_LIMIT))
    except Exception:
        pass


def _run_subprocess_limited(
    args: list[str],
    *,
    payload: bytes,
    env: dict[str, str],
    cwd: Path,
) -> _LimitedRunResult:
    preexec_fn = _preexec_set_limits if os.name == "posix" else None
    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=cwd,
        preexec_fn=preexec_fn,
    )
    assert proc.stdin is not None
    proc.stdin.write(payload)
    proc.stdin.close()
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    stdout_len = 0
    stderr_len = 0
    stdout_truncated = False
    stderr_truncated = False
    selector = selectors.DefaultSelector()
    assert proc.stdout is not None
    assert proc.stderr is not None
    selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
    selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
    start = time.monotonic()
    while selector.get_map():
        remaining = _TEST_TIMEOUT_S - (time.monotonic() - start)
        if remaining <= 0:
            proc.kill()
            raise subprocess.TimeoutExpired(args, _TEST_TIMEOUT_S)
        for key, _ in selector.select(timeout=remaining):
            data = key.fileobj.read(1024)
            if not data:
                selector.unregister(key.fileobj)
                continue
            if key.data == "stdout":
                if stdout_len < _MAX_STDOUT_BYTES:
                    keep = _MAX_STDOUT_BYTES - stdout_len
                    stdout_chunks.append(data[:keep])
                stdout_len += len(data)
                if stdout_len > _MAX_STDOUT_BYTES:
                    stdout_truncated = True
            else:
                if stderr_len < _MAX_STDERR_BYTES:
                    keep = _MAX_STDERR_BYTES - stderr_len
                    stderr_chunks.append(data[:keep])
                stderr_len += len(data)
                if stderr_len > _MAX_STDERR_BYTES:
                    stderr_truncated = True
    remaining = _TEST_TIMEOUT_S - (time.monotonic() - start)
    try:
        proc.wait(timeout=max(0.0, remaining))
    except subprocess.TimeoutExpired:
        proc.kill()
        raise
    return _LimitedRunResult(
        returncode=proc.returncode or 0,
        stdout=b"".join(stdout_chunks),
        stderr=b"".join(stderr_chunks),
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


def _classify_error(raw_error: str | None, returncode: int | None, timed_out: bool) -> tuple[str, str | None]:
    if timed_out:
        return "timeout", raw_error
    if raw_error in {"SyntaxError"}:
        return "syntax_error", raw_error
    if raw_error in {"ImportBlocked", "SecurityViolation"}:
        return "security_violation", raw_error
    if raw_error in {"MemoryError"}:
        return "mem_limit", raw_error
    if returncode is not None and returncode < 0:
        sig = -returncode
        sigx_cpu = getattr(signal, "SIGXCPU", None)
        sigx_fsz = getattr(signal, "SIGXFSZ", None)
        if sigx_cpu is not None and sig == sigx_cpu:
            return "timeout", raw_error
        if sig == signal.SIGKILL:
            return "mem_limit", raw_error
        if sigx_fsz is not None and sig == sigx_fsz:
            return "security_violation", raw_error
    return "runtime_error", raw_error


def _run_test_case(source: str, fn_name: str, args: list, expected: object) -> dict:
    payload = {
        "source": source,
        "fn_name": fn_name,
        "args": args,
        "expected": expected,
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        try:
            result = _run_subprocess_limited(
                [sys.executable, "-I", "-S", "-E", "-B", "-c", _RUNNER_RENDERED],
                payload=payload_bytes,
                env=_sandbox_env(tmp_path),
                cwd=tmp_path,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "timeout": True, "error": "timeout", "limits_applied": False}
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode != 0:
        category, detail = _classify_error(None, result.returncode, False)
        return {
            "ok": False,
            "error": category,
            "detail": detail,
            "message": (stderr or stdout)[:200],
            "output_truncated": result.stdout_truncated or result.stderr_truncated,
            "limits_applied": False,
        }
    try:
        out = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "runtime_error",
            "detail": "RunnerBadOutput",
            "message": (stderr or stdout)[:200],
            "output_truncated": result.stdout_truncated or result.stderr_truncated,
            "limits_applied": False,
        }
    if not isinstance(out, dict) or "ok" not in out:
        return {
            "ok": False,
            "error": "runtime_error",
            "detail": "RunnerBadOutput",
            "message": (stderr or stdout)[:200],
            "output_truncated": result.stdout_truncated or result.stderr_truncated,
            "limits_applied": False,
        }
    limits_applied = bool(out.get("limits_applied"))
    if out.get("ok"):
        out["limits_applied"] = limits_applied
        out["output_truncated"] = result.stdout_truncated or result.stderr_truncated
        return out
    raw_error = out.get("error")
    message = out.get("message") or out.get("result_repr")
    category, detail = _classify_error(raw_error, result.returncode, False)
    return {
        "ok": False,
        "error": category,
        "detail": detail,
        "message": message[:200] if isinstance(message, str) else None,
        "output_truncated": result.stdout_truncated or result.stderr_truncated,
        "limits_applied": limits_applied,
    }


def _encode_transcript(suite_hash: str, episodes: int, diffs: list[int]) -> bytes:
    payload = {
        "harness_id": HARNESS_ID,
        "suite_hash": suite_hash,
        "episodes": episodes,
        "diffs": diffs,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_artifact(artifact_dir: Path, transcript_hash: str, rows: list[dict]) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{transcript_hash}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
