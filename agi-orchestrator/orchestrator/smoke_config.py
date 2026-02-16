"""Helpers for smoke scripts that must be deterministic and self-contained."""

from __future__ import annotations

from pathlib import Path
import tomllib

from blake3 import blake3
from cdel.sealed.harnesses import env_v1, io_v1, pyut_v1, tooluse_v1


DEFAULT_ALPHA_TOTAL = "1e-4"
DEFAULT_SCHEDULE_NAME = "p_series"
DEFAULT_SCHEDULE_EXPONENT = 2
DEFAULT_SCHEDULE_COEFFICIENT = "0.60792710185402662866"


def materialize_env_config(
    *,
    out_path: Path,
    suite_hash: str,
    suite_path: Path | None = None,
    public_key: str,
    key_id: str,
    episodes: int,
    safety_suite_hash: str | None = None,
    safety_episodes: int | None = None,
    safety_public_key: str | None = None,
    safety_key_id: str | None = None,
    constraints_spec_hash: str | None = None,
    constraints_required_concepts: list[str] | None = None,
    alpha_total: str = DEFAULT_ALPHA_TOTAL,
    schedule_name: str = DEFAULT_SCHEDULE_NAME,
    schedule_exponent: int = DEFAULT_SCHEDULE_EXPONENT,
    schedule_coefficient: str = DEFAULT_SCHEDULE_COEFFICIENT,
) -> None:
    if episodes <= 0:
        raise ValueError("episodes must be positive")

    text = (
        "[sealed]\n"
        f'public_key = "{public_key}"\n'
        f'key_id = "{key_id}"\n'
        f'alpha_total = "{alpha_total}"\n'
        f'eval_harness_id = "{env_v1.HARNESS_ID}"\n'
        f'eval_harness_hash = "{env_v1.HARNESS_HASH}"\n'
        f'eval_suite_hash = "{suite_hash}"\n'
        f"episodes = {episodes}\n"
        "\n"
        "[sealed.alpha_schedule]\n"
        f'name = "{schedule_name}"\n'
        f"exponent = {schedule_exponent}\n"
        f'coefficient = "{schedule_coefficient}"\n'
        "\n"
        "sealed.public_keys = []\n"
        "sealed.prev_public_keys = []\n"
    )
    if safety_suite_hash is not None:
        if safety_episodes is None or safety_episodes <= 0:
            raise ValueError("safety_episodes must be positive")
        safety_key = safety_public_key or public_key
        safety_id = safety_key_id or key_id
        text += (
            "\n"
            "[sealed_safety]\n"
            f'public_key = "{safety_key}"\n'
            f'key_id = "{safety_id}"\n'
            f'alpha_total = "{alpha_total}"\n'
            f'eval_harness_id = "{env_v1.HARNESS_ID}"\n'
            f'eval_harness_hash = "{env_v1.HARNESS_HASH}"\n'
            f'eval_suite_hash = "{safety_suite_hash}"\n'
            f"episodes = {safety_episodes}\n"
            "\n"
            "[sealed_safety.alpha_schedule]\n"
            f'name = "{schedule_name}"\n'
            f"exponent = {schedule_exponent}\n"
            f'coefficient = "{schedule_coefficient}"\n'
            "\n"
            "sealed_safety.public_keys = []\n"
            "sealed_safety.prev_public_keys = []\n"
        )
    if constraints_spec_hash is not None:
        required = _format_required_concepts(constraints_required_concepts or [])
        text += (
            "\n"
            "[constraints]\n"
            f'spec_hash = "{constraints_spec_hash}"\n'
            f"required_concepts = {required}\n"
        )
    out_path.write_text(text, encoding="utf-8")
    validate_sealed_config(out_path, suite_path=suite_path)


def materialize_io_config(
    *,
    out_path: Path,
    suite_hash: str,
    suite_path: Path | None = None,
    public_key: str,
    key_id: str,
    episodes: int,
    alpha_total: str = DEFAULT_ALPHA_TOTAL,
    schedule_name: str = DEFAULT_SCHEDULE_NAME,
    schedule_exponent: int = DEFAULT_SCHEDULE_EXPONENT,
    schedule_coefficient: str = DEFAULT_SCHEDULE_COEFFICIENT,
) -> None:
    if episodes <= 0:
        raise ValueError("episodes must be positive")

    text = (
        "[sealed]\n"
        f'public_key = "{public_key}"\n'
        f'key_id = "{key_id}"\n'
        f'alpha_total = "{alpha_total}"\n'
        f'eval_harness_id = "{io_v1.HARNESS_ID}"\n'
        f'eval_harness_hash = "{io_v1.HARNESS_HASH}"\n'
        f'eval_suite_hash = "{suite_hash}"\n'
        f"episodes = {episodes}\n"
        "\n"
        "[sealed.alpha_schedule]\n"
        f'name = "{schedule_name}"\n'
        f"exponent = {schedule_exponent}\n"
        f'coefficient = "{schedule_coefficient}"\n'
        "\n"
        "sealed.public_keys = []\n"
        "sealed.prev_public_keys = []\n"
    )
    out_path.write_text(text, encoding="utf-8")
    validate_sealed_config(out_path, suite_path=suite_path)


def materialize_pyut_config(
    *,
    out_path: Path,
    suite_hash: str,
    suite_path: Path | None = None,
    public_key: str,
    key_id: str,
    episodes: int,
    alpha_total: str = DEFAULT_ALPHA_TOTAL,
    schedule_name: str = DEFAULT_SCHEDULE_NAME,
    schedule_exponent: int = DEFAULT_SCHEDULE_EXPONENT,
    schedule_coefficient: str = DEFAULT_SCHEDULE_COEFFICIENT,
) -> None:
    if episodes <= 0:
        raise ValueError("episodes must be positive")

    text = (
        "[sealed]\n"
        f'public_key = "{public_key}"\n'
        f'key_id = "{key_id}"\n'
        f'alpha_total = "{alpha_total}"\n'
        f'eval_harness_id = "{pyut_v1.HARNESS_ID}"\n'
        f'eval_harness_hash = "{pyut_v1.HARNESS_HASH}"\n'
        f'eval_suite_hash = "{suite_hash}"\n'
        f"episodes = {episodes}\n"
        "\n"
        "[sealed.alpha_schedule]\n"
        f'name = "{schedule_name}"\n'
        f"exponent = {schedule_exponent}\n"
        f'coefficient = "{schedule_coefficient}"\n'
        "\n"
        "sealed.public_keys = []\n"
        "sealed.prev_public_keys = []\n"
    )
    out_path.write_text(text, encoding="utf-8")
    validate_sealed_config(out_path, suite_path=suite_path)


def materialize_tooluse_config(
    *,
    out_path: Path,
    suite_hash: str,
    suite_path: Path | None = None,
    public_key: str,
    key_id: str,
    episodes: int,
    safety_suite_hash: str | None = None,
    safety_episodes: int | None = None,
    safety_public_key: str | None = None,
    safety_key_id: str | None = None,
    constraints_spec_hash: str | None = None,
    constraints_required_concepts: list[str] | None = None,
    alpha_total: str = DEFAULT_ALPHA_TOTAL,
    schedule_name: str = DEFAULT_SCHEDULE_NAME,
    schedule_exponent: int = DEFAULT_SCHEDULE_EXPONENT,
    schedule_coefficient: str = DEFAULT_SCHEDULE_COEFFICIENT,
) -> None:
    if episodes <= 0:
        raise ValueError("episodes must be positive")

    text = (
        "[sealed]\n"
        f'public_key = "{public_key}"\n'
        f'key_id = "{key_id}"\n'
        f'alpha_total = "{alpha_total}"\n'
        f'eval_harness_id = "{tooluse_v1.HARNESS_ID}"\n'
        f'eval_harness_hash = "{tooluse_v1.HARNESS_HASH}"\n'
        f'eval_suite_hash = "{suite_hash}"\n'
        f"episodes = {episodes}\n"
        "\n"
        "[sealed.alpha_schedule]\n"
        f'name = "{schedule_name}"\n'
        f"exponent = {schedule_exponent}\n"
        f'coefficient = "{schedule_coefficient}"\n'
        "\n"
        "sealed.public_keys = []\n"
        "sealed.prev_public_keys = []\n"
    )
    if safety_suite_hash is not None:
        if safety_episodes is None or safety_episodes <= 0:
            raise ValueError("safety_episodes must be positive")
        safety_key = safety_public_key or public_key
        safety_id = safety_key_id or key_id
        text += (
            "\n"
            "[sealed_safety]\n"
            f'public_key = "{safety_key}"\n'
            f'key_id = "{safety_id}"\n'
            f'alpha_total = "{alpha_total}"\n'
            f'eval_harness_id = "{tooluse_v1.HARNESS_ID}"\n'
            f'eval_harness_hash = "{tooluse_v1.HARNESS_HASH}"\n'
            f'eval_suite_hash = "{safety_suite_hash}"\n'
            f"episodes = {safety_episodes}\n"
            "\n"
            "[sealed_safety.alpha_schedule]\n"
            f'name = "{schedule_name}"\n'
            f"exponent = {schedule_exponent}\n"
            f'coefficient = "{schedule_coefficient}"\n'
            "\n"
            "sealed_safety.public_keys = []\n"
            "sealed_safety.prev_public_keys = []\n"
        )
    if constraints_spec_hash is not None:
        required = _format_required_concepts(constraints_required_concepts or [])
        text += (
            "\n"
            "[constraints]\n"
            f'spec_hash = "{constraints_spec_hash}"\n'
            f"required_concepts = {required}\n"
        )
    out_path.write_text(text, encoding="utf-8")
    validate_sealed_config(out_path, suite_path=suite_path)


def validate_sealed_config(path: Path, *, suite_path: Path | None = None) -> None:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    sealed = data.get("sealed")
    if not isinstance(sealed, dict):
        raise ValueError("sealed config missing")

    required = ("eval_harness_id", "eval_harness_hash", "eval_suite_hash", "episodes")
    missing = [key for key in required if key not in sealed]
    if missing:
        raise ValueError(f"sealed fields missing: {', '.join(missing)}")

    episodes = sealed.get("episodes")
    if not isinstance(episodes, int) or episodes <= 0:
        raise ValueError("sealed.episodes must be positive int")

    if suite_path is not None:
        if not suite_path.exists():
            raise FileNotFoundError(f"suite path missing: {suite_path}")
        digest = blake3(suite_path.read_bytes()).hexdigest()
        if digest != sealed.get("eval_suite_hash"):
            raise ValueError("suite hash mismatch")

    sealed_safety = data.get("sealed_safety")
    if sealed_safety is None:
        return
    if not isinstance(sealed_safety, dict):
        raise ValueError("sealed_safety config must be object")
    safety_required = ("eval_harness_id", "eval_harness_hash", "eval_suite_hash", "episodes")
    missing_safety = [key for key in safety_required if key not in sealed_safety]
    if missing_safety:
        raise ValueError(f"sealed_safety fields missing: {', '.join(missing_safety)}")
    safety_episodes = sealed_safety.get("episodes")
    if not isinstance(safety_episodes, int) or safety_episodes <= 0:
        raise ValueError("sealed_safety.episodes must be positive int")


def _format_required_concepts(items: list[str]) -> str:
    if not items:
        return "[]"
    ordered = sorted(items)
    rendered = ", ".join(f"\"{item}\"" for item in ordered)
    return f"[{rendered}]"
