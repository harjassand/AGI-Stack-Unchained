#!/usr/bin/env python3
"""Validate suite pointers and sealed config references."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
import tomllib

from blake3 import blake3
from cdel.sealed.harnesses import get_harness


DEFAULT_POINTERS = [
    Path("suites") / "agent_reliability_dev_current.json",
    Path("suites") / "env_dev_current.json",
    Path("suites") / "env_hard_dev_current.json",
    Path("suites") / "io_dev_current.json",
    Path("suites") / "pyut_dev_current.json",
    Path("suites") / "pyut_transfer_dev_current.json",
    Path("suites") / "tooluse_dev_current.json",
]

DEFAULT_CONFIGS = [
    Path("configs") / "sealed_io_dev.toml",
    Path("configs") / "sealed_io_heldout.toml",
    Path("configs") / "sealed_env_dev.toml",
    Path("configs") / "sealed_env_heldout.toml",
    Path("configs") / "sealed_env_hard_dev.toml",
    Path("configs") / "sealed_env_hard_heldout.toml",
    Path("configs") / "sealed_env_safety_dev.toml",
    Path("configs") / "sealed_env_safety_heldout.toml",
    Path("configs") / "sealed_pyut_dev.toml",
    Path("configs") / "sealed_pyut_heldout.toml",
    Path("configs") / "sealed_pyut_transfer_dev.toml",
    Path("configs") / "sealed_pyut_transfer_heldout.toml",
    Path("configs") / "sealed_tooluse_dev.toml",
    Path("configs") / "sealed_tooluse_heldout.toml",
    Path("configs") / "sealed_tooluse_safety_dev.toml",
    Path("configs") / "sealed_tooluse_safety_heldout.toml",
    Path("configs") / "sealed_agent_reliability_dev.toml",
    Path("configs") / "sealed_agent_reliability_heldout.toml",
]

REQUIRED_FIELDS = {
    "io-harness-v1": ("episode", "args", "target"),
    "env-harness-v1": ("episode", "env", "start", "goal", "max_steps"),
    "pyut-harness-v1": ("episode", "task_id", "fn_name", "signature", "tests"),
    "tooluse-harness-v1": ("episode", "task_id", "max_steps", "allowed_tools", "tool_calls", "success"),
}

DOMAIN_TO_HARNESS = {
    "agent-reliability-v1": "tooluse-harness-v1",
    "env-gridworld-hard-v1": "env-harness-v1",
    "env-gridworld-v1": "env-harness-v1",
    "io-algorithms-v1": "io-harness-v1",
    "python-ut-v1": "pyut-harness-v1",
    "pyut-transfer-v1": "pyut-harness-v1",
    "tooluse-v1": "tooluse-harness-v1",
}


class SuiteIntegrityError(RuntimeError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class SealedConfig:
    path: Path
    harness_id: str
    harness_hash: str
    suite_hash: str
    episodes: int
    is_heldout: bool


def _hash_bytes(data: bytes) -> str:
    return blake3(data).hexdigest()


def _hash_file(path: Path) -> str:
    return _hash_bytes(path.read_bytes())


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _parse_sealed_config(path: Path, data: dict | None = None) -> SealedConfig:
    if data is None:
        data = _load_toml(path)
    sealed = data.get("sealed")
    if not isinstance(sealed, dict):
        raise ValueError("sealed section missing")
    required = ("eval_harness_id", "eval_harness_hash", "eval_suite_hash", "episodes")
    missing = [key for key in required if key not in sealed]
    if missing:
        raise ValueError(f"missing sealed fields: {', '.join(missing)}")
    episodes = sealed.get("episodes")
    if not isinstance(episodes, int) or episodes <= 0:
        raise ValueError("sealed.episodes must be a positive int")
    is_heldout = "heldout" in path.name
    return SealedConfig(
        path=path,
        harness_id=str(sealed["eval_harness_id"]),
        harness_hash=str(sealed["eval_harness_hash"]),
        suite_hash=str(sealed["eval_suite_hash"]),
        episodes=episodes,
        is_heldout=is_heldout,
    )


def _parse_sealed_block(data: dict, *, block: str, path: Path, is_heldout: bool) -> SealedConfig:
    sealed = data.get(block)
    if sealed is None:
        raise ValueError(f"{block} section missing")
    if not isinstance(sealed, dict):
        raise ValueError(f"{block} must be object")
    required = ("eval_harness_id", "eval_harness_hash", "eval_suite_hash", "episodes")
    missing = [key for key in required if key not in sealed]
    if missing:
        raise ValueError(f"missing {block} fields: {', '.join(missing)}")
    episodes = sealed.get("episodes")
    if not isinstance(episodes, int) or episodes <= 0:
        raise ValueError(f"{block}.episodes must be positive int")
    return SealedConfig(
        path=path,
        harness_id=str(sealed["eval_harness_id"]),
        harness_hash=str(sealed["eval_harness_hash"]),
        suite_hash=str(sealed["eval_suite_hash"]),
        episodes=episodes,
        is_heldout=is_heldout,
    )


def _validate_jsonl(path: Path, *, harness_id: str) -> None:
    required = REQUIRED_FIELDS.get(harness_id)
    if required is None:
        raise ValueError(f"unknown harness id for suite validation: {harness_id}")
    for index, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on line {index}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"line {index} must be an object")
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(f"line {index} missing fields: {', '.join(missing)}")


def _validate_suite_file(path: Path, *, harness_id: str, expected_hash: str) -> None:
    if _hash_file(path) != expected_hash:
        raise ValueError("suite hash mismatch")
    _validate_jsonl(path, harness_id=harness_id)


def check_suite_integrity(
    repo_root: Path,
    *,
    pointer_paths: list[Path] | None = None,
    config_paths: list[Path] | None = None,
) -> None:
    errors: list[str] = []
    pointers = DEFAULT_POINTERS if pointer_paths is None else pointer_paths
    configs = DEFAULT_CONFIGS if config_paths is None else config_paths

    for rel_path in pointers:
        path = repo_root / rel_path
        if not path.exists():
            errors.append(f"pointer missing: {rel_path}")
            continue
        try:
            data = _load_json(path)
        except json.JSONDecodeError as exc:
            errors.append(f"pointer invalid JSON {rel_path}: {exc}")
            continue
        suite_hash = data.get("suite_hash")
        domain = data.get("domain")
        if not isinstance(suite_hash, str) or not suite_hash:
            errors.append(f"pointer missing suite_hash: {rel_path}")
            continue
        harness_id = DOMAIN_TO_HARNESS.get(str(domain))
        if harness_id is None:
            errors.append(f"pointer unknown domain: {domain}")
            continue
        suite_path = repo_root / "sealed_suites" / f"{suite_hash}.jsonl"
        if not suite_path.exists():
            errors.append(f"suite file missing: sealed_suites/{suite_hash}.jsonl")
            continue
        try:
            _validate_suite_file(suite_path, harness_id=harness_id, expected_hash=suite_hash)
        except ValueError as exc:
            errors.append(f"pointer suite invalid ({suite_path.name}): {exc}")

    for rel_path in configs:
        path = repo_root / rel_path
        if not path.exists():
            errors.append(f"config missing: {rel_path}")
            continue
        try:
            data = _load_toml(path)
            config = _parse_sealed_config(path, data)
        except ValueError as exc:
            errors.append(f"config invalid {rel_path}: {exc}")
            continue
        try:
            harness = get_harness(config.harness_id)
        except Exception as exc:  # noqa: BLE001 - report actionable message.
            errors.append(f"config unknown harness {rel_path}: {exc}")
            continue
        harness_hash = getattr(harness, "harness_hash", None)
        if harness_hash != config.harness_hash:
            errors.append(
                "config harness hash mismatch "
                f"{rel_path}: expected {harness_hash}, got {config.harness_hash}"
            )
            continue

        suite_path = repo_root / "sealed_suites" / f"{config.suite_hash}.jsonl"
        if config.is_heldout:
            if suite_path.exists():
                errors.append(
                    f"heldout suite bytes committed: sealed_suites/{config.suite_hash}.jsonl"
                )
            continue
        if not suite_path.exists():
            errors.append(f"dev suite missing: sealed_suites/{config.suite_hash}.jsonl")
            continue
        try:
            _validate_suite_file(
                suite_path, harness_id=config.harness_id, expected_hash=config.suite_hash
            )
        except ValueError as exc:
            errors.append(f"dev suite invalid ({suite_path.name}): {exc}")

        if "sealed_safety" in data:
            try:
                safety_cfg = _parse_sealed_block(
                    data,
                    block="sealed_safety",
                    path=path,
                    is_heldout=config.is_heldout,
                )
            except ValueError as exc:
                errors.append(f"config safety invalid {rel_path}: {exc}")
                continue
            try:
                safety_harness = get_harness(safety_cfg.harness_id)
            except Exception as exc:  # noqa: BLE001 - report actionable message.
                errors.append(f"config safety unknown harness {rel_path}: {exc}")
                continue
            if getattr(safety_harness, "harness_hash", None) != safety_cfg.harness_hash:
                errors.append(
                    "config safety harness hash mismatch "
                    f"{rel_path}: expected {safety_harness.harness_hash}, got {safety_cfg.harness_hash}"
                )
                continue
            safety_suite = repo_root / "sealed_suites" / f"{safety_cfg.suite_hash}.jsonl"
            if safety_cfg.is_heldout:
                if safety_suite.exists():
                    errors.append(
                        f"heldout safety suite bytes committed: sealed_suites/{safety_cfg.suite_hash}.jsonl"
                    )
            else:
                if not safety_suite.exists():
                    errors.append(f"safety suite missing: sealed_suites/{safety_cfg.suite_hash}.jsonl")
                    continue
                try:
                    _validate_suite_file(
                        safety_suite,
                        harness_id=safety_cfg.harness_id,
                        expected_hash=safety_cfg.suite_hash,
                    )
                except ValueError as exc:
                    errors.append(f"safety suite invalid ({safety_suite.name}): {exc}")

    if errors:
        raise SuiteIntegrityError(errors)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        check_suite_integrity(repo_root)
    except SuiteIntegrityError as exc:
        for error in exc.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("OK: suite/config integrity check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
