from __future__ import annotations

import pytest

from orchestrator.smoke_config import validate_sealed_config


def test_validate_sealed_config_requires_fields(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[sealed]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="sealed fields missing"):
        validate_sealed_config(path)


def test_validate_sealed_config_checks_suite_hash(tmp_path) -> None:
    suite = tmp_path / "suite.jsonl"
    suite.write_text("{}", encoding="utf-8")

    config = tmp_path / "config.toml"
    config.write_text(
        "\n".join(
            [
                "[sealed]",
                'eval_harness_id = "io-harness-v1"',
                'eval_harness_hash = "io-harness-v1-hash"',
                'eval_suite_hash = "deadbeef"',
                "episodes = 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="suite hash mismatch"):
        validate_sealed_config(config, suite_path=suite)
