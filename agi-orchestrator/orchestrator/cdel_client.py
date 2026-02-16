"""Subprocess wrapper for CDEL CLI."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CommandRecord:
    argv: list[str]
    env: dict[str, str]
    env_overrides: dict[str, str]
    env_unset: list[str]
    cwd: str
    returncode: int
    stdout_preview: str
    stderr_preview: str
    expected_files: list[str]
    expected_files_ok: bool
    expected_files_errors: list[str]


class CDELClient:
    def __init__(self) -> None:
        self.command_log: list[CommandRecord] = []

    def init_workspace(self, root_dir: Path) -> None:
        root_dir.mkdir(parents=True, exist_ok=True)
        cfg_path = root_dir / "config.toml"
        if not cfg_path.exists():
            cfg_path.write_text("\n", encoding="utf-8")
        self._run(["init"], root_dir=root_dir, config=cfg_path, env_unset=["CDEL_SUITES_DIR"])

    def commit_module(self, root_dir: Path, module_path: Path, config: Path) -> str:
        result = self._run_json(
            ["commit", str(module_path)],
            root_dir=root_dir,
            config=config,
            env_unset=["CDEL_SUITES_DIR"],
        )
        return str(result.get("hash"))

    def adopt(self, root_dir: Path, adoption_path: Path, config: Path) -> str:
        result = self._run_json(
            ["adopt", str(adoption_path)],
            root_dir=root_dir,
            config=config,
            env_unset=["CDEL_SUITES_DIR"],
        )
        return str(result.get("hash"))

    def issue_stat_cert(
        self,
        root_dir: Path,
        request_path: Path,
        out_path: Path,
        config: Path,
        seed_key: str,
        suites_dir: Path | None,
        candidate_module: Path | None = None,
    ) -> None:
        args = [
            "sealed",
            "worker",
            "--request",
            str(request_path),
            "--out",
            str(out_path),
            "--seed-key",
            seed_key,
        ]
        if candidate_module is not None:
            args.extend(["--candidate-module", str(candidate_module)])
        env_overrides = {}
        env_unset: list[str] = []
        if suites_dir is None:
            env_unset.append("CDEL_SUITES_DIR")
        else:
            env_overrides["CDEL_SUITES_DIR"] = str(suites_dir)
        self._run(
            args,
            root_dir=root_dir,
            config=config,
            env_overrides=env_overrides,
            env_unset=env_unset,
            expected_files=[out_path],
        )
        self._require_cert_fields(out_path)

    def resolve_concept(self, root_dir: Path, concept: str, config: Path) -> str:
        result = self._run_json(
            ["resolve", "--concept", concept],
            root_dir=root_dir,
            config=config,
            env_unset=["CDEL_SUITES_DIR"],
        )
        chosen = result.get("chosen_symbol") or result.get("symbol")
        return "" if chosen is None else str(chosen)

    def _run_json(
        self,
        args: list[str],
        *,
        root_dir: Path,
        config: Path,
        env_overrides: dict[str, str] | None = None,
        env_unset: Iterable[str] | None = None,
        expected_files: list[Path] | None = None,
    ) -> dict:
        result = self._run(
            args,
            root_dir=root_dir,
            config=config,
            env_overrides=env_overrides,
            env_unset=env_unset,
            expected_files=expected_files,
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("cdel cli returned non-json output") from exc

    def _run(
        self,
        args: list[str],
        *,
        root_dir: Path,
        config: Path,
        env_overrides: dict[str, str] | None = None,
        env_unset: Iterable[str] | None = None,
        expected_files: list[Path] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        argv = [sys.executable, "-m", "cdel.cli", "--root", str(root_dir), "--config", str(config), *args]
        env = dict(os.environ)
        env_overrides = env_overrides or {}
        env_unset = list(env_unset or [])
        for key in env_unset:
            env.pop(key, None)
        env.update(env_overrides)
        _inject_cdel_pythonpath(env)
        result = subprocess.run(argv, check=False, capture_output=True, text=True, cwd=root_dir, env=env)
        expected_files_list = [str(path) for path in (expected_files or [])]
        expected_ok, expected_errors = self._validate_expected_files(expected_files or [])
        redacted_env = _redact_env(env)
        redacted_overrides = _redact_env(env_overrides)
        stdout_preview = _redact_text(_preview(result.stdout))
        stderr_preview = _redact_text(_preview(result.stderr))
        self.command_log.append(
            CommandRecord(
                argv=argv,
                env=redacted_env,
                env_overrides=redacted_overrides,
                env_unset=list(env_unset),
                cwd=str(root_dir),
                returncode=result.returncode,
                stdout_preview=stdout_preview,
                stderr_preview=stderr_preview,
                expected_files=expected_files_list,
                expected_files_ok=expected_ok,
                expected_files_errors=expected_errors,
            )
        )
        if result.returncode != 0:
            raise RuntimeError(f"cdel cli failed with exit code {result.returncode}")
        if expected_files and not expected_ok:
            detail = "; ".join(expected_errors) or "expected files missing or invalid"
            raise RuntimeError(f"cdel cli missing expected output files: {detail}")
        if not expected_files and result.stdout.strip() == "" and result.stderr.strip() == "":
            raise RuntimeError("cdel cli returned empty output")
        return result

    def _validate_expected_files(self, expected_files: Iterable[Path]) -> tuple[bool, list[str]]:
        errors: list[str] = []
        for path in expected_files:
            if not path.exists():
                errors.append(f"missing:{path}")
                continue
            if path.stat().st_size <= 0:
                errors.append(f"empty:{path}")
                continue
            if path.suffix == ".json":
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    errors.append(f"invalid_json:{path}")
        return (len(errors) == 0), errors

    def _require_cert_fields(self, cert_path: Path) -> None:
        try:
            payload = json.loads(cert_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("heldout cert is not valid json") from exc
        cert = payload.get("certificate")
        if not isinstance(cert, dict):
            raise RuntimeError("heldout cert missing certificate payload")
        for field in ("transcript_hash", "signature", "evalue"):
            if field not in cert:
                raise RuntimeError(f"heldout cert missing certificate.{field}")


def _inject_cdel_pythonpath(env: dict[str, str]) -> None:
    try:
        import cdel
    except Exception:
        return
    package_root = Path(cdel.__file__).resolve().parents[1]
    existing = env.get("PYTHONPATH", "")
    parts = [part for part in existing.split(os.pathsep) if part]
    if str(package_root) not in parts:
        parts.insert(0, str(package_root))
        env["PYTHONPATH"] = os.pathsep.join(parts)


def _preview(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


_REDACT_KEYS = ("TOKEN", "SECRET", "KEY", "PASS", "PWD", "COOKIE", "AUTH", "BEARER")
_GITHUB_TOKEN_RE = re.compile(r"(ghp_[A-Za-z0-9]{10,})")
_GITHUB_PAT_RE = re.compile(r"(github_pat_[A-Za-z0-9_]{10,})")


def _redact_env(env: dict[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in env.items():
        upper = key.upper()
        if any(marker in upper for marker in _REDACT_KEYS):
            redacted[key] = "**REDACTED**"
        else:
            redacted[key] = value
    return redacted


def _redact_text(text: str) -> str:
    text = _GITHUB_TOKEN_RE.sub("**REDACTED**", text)
    return _GITHUB_PAT_RE.sub("**REDACTED**", text)
