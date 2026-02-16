from __future__ import annotations

from pathlib import Path

from orchestrator.heldout_rotation import update_heldout_config_hash


def test_update_heldout_config_updates_only_hash(tmp_path: Path) -> None:
    config_path = tmp_path / "sealed_pyut_heldout.toml"
    content = "\n".join(
        [
            "[sealed]",
            "eval_harness_id = \"pyut-harness-v1\"",
            "eval_harness_hash = \"pyut-harness-v1-hash-2\"",
            "eval_suite_hash = \"oldhash\"",
            "episodes = 32",
            "",
        ]
    )
    config_path.write_text(content, encoding="utf-8")

    update_heldout_config_hash(config_path=config_path, suite_hash="newhash")
    updated = config_path.read_text(encoding="utf-8")
    assert "eval_suite_hash = \"newhash\"" in updated
    assert "eval_harness_id = \"pyut-harness-v1\"" in updated
