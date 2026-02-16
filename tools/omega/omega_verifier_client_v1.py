"""Client wrapper for persistent omega verifier worker."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


class OmegaVerifierClient:
    """JSONL client for ``cdel.v18_0.omega_verifier_worker_v1``."""

    def __init__(self, *, repo_root: Path) -> None:
        self._repo_root = repo_root.resolve()
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{self._repo_root}:{self._repo_root / 'CDEL-v2'}:{env.get('PYTHONPATH', '')}".rstrip(":")
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "cdel.v18_0.omega_verifier_worker_v1"],
            cwd=self._repo_root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def verify(self, state_dir: Path, *, mode: str = "full") -> tuple[bool, str, str]:
        proc = self._proc
        if proc.stdin is None or proc.stdout is None:
            return False, "VERIFY_ERROR", "worker stdio unavailable"
        if proc.poll() is not None:
            detail = ""
            if proc.stderr is not None:
                try:
                    detail = proc.stderr.read().strip()
                except Exception:  # noqa: BLE001
                    detail = ""
            return False, "VERIFY_ERROR", detail or "worker exited"

        request = {
            "op": "VERIFY",
            "state_dir": str(Path(state_dir).resolve()),
            "mode": str(mode),
        }
        proc.stdin.write(json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n")
        proc.stdin.flush()

        line = proc.stdout.readline()
        if not line:
            detail = ""
            if proc.stderr is not None:
                try:
                    detail = proc.stderr.read().strip()
                except Exception:  # noqa: BLE001
                    detail = ""
            return False, "VERIFY_ERROR", detail or "worker produced no response"

        try:
            response = json.loads(line)
        except Exception as exc:  # noqa: BLE001
            return False, "VERIFY_ERROR", f"invalid worker response: {exc}"
        if not isinstance(response, dict):
            return False, "VERIFY_ERROR", "invalid worker response type"

        ok = bool(response.get("ok", False))
        if ok:
            verdict = str(response.get("verdict", "VALID")).strip() or "VALID"
            detail = str(response.get("detail", verdict)).strip() or verdict
            return True, verdict, detail

        reason = str(response.get("reason", "VERIFY_ERROR")).strip() or "VERIFY_ERROR"
        detail = str(response.get("detail", reason)).strip() or reason
        return False, reason, detail

    def close(self) -> None:
        proc = self._proc
        if proc.poll() is not None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except Exception:  # noqa: BLE001
            proc.kill()
            proc.wait(timeout=2.0)

    def __enter__(self) -> "OmegaVerifierClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


__all__ = ["OmegaVerifierClient"]
