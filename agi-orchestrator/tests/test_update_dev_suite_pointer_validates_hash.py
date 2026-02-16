from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.suite_pointer import update_pyut_dev_suite_pointer


def _write_suite(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_config(path: Path, suite_hash: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "[sealed]",
                "eval_harness_id = \"pyut-harness-v1\"",
                "eval_harness_hash = \"pyut-harness-v1-hash-2\"",
                f"eval_suite_hash = \"{suite_hash}\"",
                "episodes = 32",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_update_dev_suite_pointer_validates_hash(tmp_path: Path) -> None:
    suites_dir = tmp_path / "sealed_suites"
    pointer_path = tmp_path / "suites" / "pyut_dev_current.json"
    dev_config = tmp_path / "configs" / "sealed_pyut_dev.toml"

    bad_hash = "deadbeef"
    suite_path = suites_dir / f"{bad_hash}.jsonl"
    _write_suite(suite_path, "{\"episode\":0}\n")
    _write_config(dev_config, bad_hash)

    with pytest.raises(ValueError, match="suite hash mismatch"):
        update_pyut_dev_suite_pointer(
            suite_hash=bad_hash,
            suites_dir=suites_dir,
            pointer_path=pointer_path,
            dev_config_path=dev_config,
            updated_at="2026-01-23",
            source="manual",
            notes="test",
        )
