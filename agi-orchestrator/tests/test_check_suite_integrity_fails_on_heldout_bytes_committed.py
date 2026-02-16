from __future__ import annotations

from pathlib import Path

import pytest

from cdel.sealed.harnesses.io_v1 import HARNESS_HASH as IO_HARNESS_HASH
from scripts.check_suite_integrity import SuiteIntegrityError, check_suite_integrity


def test_check_suite_integrity_fails_on_heldout_bytes_committed(tmp_path: Path) -> None:
    configs_dir = tmp_path / "configs"
    suites_dir = tmp_path / "sealed_suites"
    configs_dir.mkdir()
    suites_dir.mkdir()

    suite_hash = "0" * 64
    config_path = configs_dir / "sealed_io_heldout.toml"
    config_path.write_text(
        "\n".join(
            [
                "[sealed]",
                'eval_harness_id = "io-harness-v1"',
                f'eval_harness_hash = "{IO_HARNESS_HASH}"',
                f'eval_suite_hash = "{suite_hash}"',
                "episodes = 8",
                "",
            ]
        ),
        encoding="utf-8",
    )

    suite_path = suites_dir / f"{suite_hash}.jsonl"
    suite_path.write_text(
        '{"episode": 0, "args": [{"tag": "int", "value": 0}], "target": {"tag": "bool", "value": true}}\n',
        encoding="utf-8",
    )

    with pytest.raises(SuiteIntegrityError, match="heldout suite bytes committed"):
        check_suite_integrity(tmp_path, pointer_paths=[], config_paths=[Path("configs/sealed_io_heldout.toml")])
