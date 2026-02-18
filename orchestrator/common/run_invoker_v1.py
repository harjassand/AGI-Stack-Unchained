"""Single subprocess runner utilities with sanitized env capture."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from cdel.v18_0.omega_common_v1 import canon_hash_obj, hash_file


_SANITIZED_ENV_KEYS = (
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PYTHONHASHSEED",
    "PYTHONPATH",
    "TMPDIR",
    "OMEGA_RUN_SEED_U64",
    "OMEGA_POLYMATH_STORE_ROOT",
    "OMEGA_NET_LIVE_OK",
    "OMEGA_GE_STATE_ROOT",
    # Drill-only CCAP overrides (safe to pass through; default is empty).
    "OMEGA_AUTHORITY_PINS_REL",
    "OMEGA_CCAP_PATCH_ALLOWLISTS_REL",
    "OMEGA_SURVIVAL_DRILL",
    "ORCH_LLM_BACKEND",
    "ORCH_LLM_REPLAY_PATH",
    "ORCH_LLM_MAX_CALLS",
    "ORCH_LLM_MAX_PROMPT_CHARS",
    "ORCH_LLM_MAX_RESPONSE_CHARS",
    "ORCH_LLM_TEMPERATURE",
    "ORCH_LLM_MAX_TOKENS",
    "ORCH_LLM_TOP_P",
    "ORCH_LLM_MOCK_RESPONSE",
    "ORCH_LLM_MOCK_MODE",
    "ORCH_OPENAI_MODEL",
    "ORCH_GEMINI_MODEL",
    "ORCH_ANTHROPIC_MODEL",
    "ORCH_ANTHROPIC_VERSION",
    "ORCH_LLM_LIVE_OK",
    "ORCH_LLM_RETRY_429_MAX_ATTEMPTS",
    "ORCH_LLM_RETRY_429_BASE_DELAY_S",
    "OMEGA_WILD_MODE",
)


def _env_fingerprint(env_map: dict[str, str]) -> str:
    rows = [{"k": k, "v": env_map[k]} for k in sorted(env_map.keys())]
    return canon_hash_obj({"schema_version": "env_fingerprint_v1", "entries": rows})


def _build_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {key: os.environ.get(key, "") for key in _SANITIZED_ENV_KEYS}
    env["PYTHONHASHSEED"] = "0"
    if extra:
        for key, value in extra.items():
            env[str(key)] = str(value)
    return env


def run_module(
    *,
    py_module: str,
    argv: list[str],
    cwd: Path,
    output_dir: Path,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / "stdout.log"
    stderr_path = output_dir / "stderr.log"

    cmd = [sys.executable, "-m", py_module, *argv]
    env = _build_env(extra_env)

    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")

    return {
        "return_code": int(proc.returncode),
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "stdout_hash": hash_file(stdout_path),
        "stderr_hash": hash_file(stderr_path),
        "env_fingerprint_hash": _env_fingerprint(env),
        "py_module": py_module,
        "argv": list(argv),
    }


def run_command(
    *,
    cmd: list[str],
    cwd: Path,
    output_dir: Path,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / "stdout.log"
    stderr_path = output_dir / "stderr.log"

    env = _build_env(extra_env)
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")

    return {
        "return_code": int(proc.returncode),
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "stdout_hash": hash_file(stdout_path),
        "stderr_hash": hash_file(stderr_path),
        "env_fingerprint_hash": _env_fingerprint(env),
        "cmd": list(cmd),
    }


__all__ = ["run_command", "run_module"]
