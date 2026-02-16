from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    repo_root = Path(__file__).resolve().parents[1]
    env_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{repo_root}{os.pathsep}{env_path}" if env_path else str(repo_root)
    return subprocess.run(
        [sys.executable, "-m", "cdel.cli", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


def test_cli_help_contract(tmp_path: Path) -> None:
    result = _run_cli(["--help"], tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip()


def test_cli_failure_has_stderr(tmp_path: Path) -> None:
    result = _run_cli(["--root", str(tmp_path), "--config", "missing.toml", "config", "show"], tmp_path)
    assert result.returncode != 0
    assert result.stderr.strip()


def test_cli_config_show_uses_path(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[spec]\nint_min = -9\nint_max = 9\nlist_max_len = 3\n",
        encoding="utf-8",
    )
    result = _run_cli(
        ["--root", str(tmp_path), "--config", "config.toml", "config", "show"],
        tmp_path,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload.get("spec", {}).get("int_min") == -9
