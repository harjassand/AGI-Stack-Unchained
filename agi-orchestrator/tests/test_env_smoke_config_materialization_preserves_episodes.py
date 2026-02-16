from __future__ import annotations

import tomllib

from cdel.sealed.harnesses import env_v1

from orchestrator.smoke_config import materialize_env_config


def test_env_smoke_config_materialization_preserves_episodes(tmp_path) -> None:
    out_path = tmp_path / "env_config.toml"
    materialize_env_config(
        out_path=out_path,
        suite_hash="deadbeef",
        public_key="pubkey",
        key_id="keyid",
        episodes=7,
    )

    data = tomllib.loads(out_path.read_text(encoding="utf-8"))
    sealed = data["sealed"]

    assert sealed["episodes"] == 7
    assert sealed["eval_harness_id"] == env_v1.HARNESS_ID
    assert sealed["eval_harness_hash"] == env_v1.HARNESS_HASH
