"""Client wrapper for persistent sealed evaluator worker."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


class SealedEvalClientError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise SealedEvalClientError(reason)


@dataclass
class SealedEvalClient:
    _proc: subprocess.Popen[str]
    _closed: bool = False

    def _stderr_text(self) -> str:
        if self._proc.stderr is None:
            return ""
        try:
            return self._proc.stderr.read().strip()
        except Exception:
            return ""

    def _ensure_running(self) -> None:
        rc = self._proc.poll()
        if rc is None:
            return
        detail = self._stderr_text()
        if detail:
            _fail(f"worker_exit_{rc}:{detail}")
        _fail(f"worker_exit_{rc}")

    def run_jobs(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._closed:
            _fail("worker_closed")
        if not jobs:
            return []
        if self._proc.stdin is None or self._proc.stdout is None:
            _fail("worker_pipe_missing")

        out: list[dict[str, Any]] = []
        for job in jobs:
            self._ensure_running()
            try:
                line = json.dumps(job, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            except Exception as exc:
                raise SealedEvalClientError("job_serialize_fail") from exc
            try:
                self._proc.stdin.write(line + "\n")
                self._proc.stdin.flush()
            except Exception as exc:
                raise SealedEvalClientError("worker_write_fail") from exc

            response_line = self._proc.stdout.readline()
            if response_line == "":
                self._ensure_running()
                _fail("worker_eof")
            try:
                payload = json.loads(response_line)
            except json.JSONDecodeError as exc:
                raise SealedEvalClientError("worker_json_fail") from exc
            if not isinstance(payload, dict):
                _fail("worker_schema_fail")
            out.append(payload)

            rc = self._proc.poll()
            if rc is not None and rc != 0:
                detail = self._stderr_text()
                if detail:
                    _fail(f"worker_exit_{rc}:{detail}")
                _fail(f"worker_exit_{rc}")

        if len(out) != len(jobs):
            _fail("worker_row_mismatch")
        return out

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._proc.stdin is not None and not self._proc.stdin.closed:
                self._proc.stdin.close()
        except Exception:
            pass

        try:
            rc = self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired as exc:
            try:
                self._proc.kill()
            except Exception:
                pass
            raise SealedEvalClientError("worker_close_timeout") from exc

        if rc != 0:
            detail = self._stderr_text()
            if detail:
                _fail(f"worker_exit_{rc}:{detail}")
            _fail(f"worker_exit_{rc}")


def start(python_exe: str, env: dict[str, str]) -> SealedEvalClient:
    cmd = [
        str(python_exe),
        "-m",
        "cdel.v13_0.sealed_science_eval_worker_v1",
        "--mode",
        "worker",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=dict(env),
        )
    except Exception as exc:
        raise SealedEvalClientError("worker_start_fail") from exc
    return SealedEvalClient(_proc=proc)


__all__ = ["SealedEvalClient", "SealedEvalClientError", "start"]
