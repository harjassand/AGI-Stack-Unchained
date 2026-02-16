from __future__ import annotations

import json
from pathlib import Path

from self_improve_code_v1.domains.flagship_code_rsi_v1 import domain as domain_mod


def test_flagship_config_load() -> None:
    cfg_path = Path(__file__).resolve().parents[1] / "domains" / "flagship_code_rsi_v1" / "default_run_config.json"
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == "flagship_code_rsi_v1"
    required = [
        "run_id",
        "seed",
        "target_repo_id",
        "target_repo_path",
        "baseline_commit",
        "candidate",
        "curriculum",
        "proposal",
        "devscreen",
        "sealed_dev",
        "sealed_heldout",
        "output",
    ]
    for key in required:
        assert key in raw

    # load with domain helper
    loaded = domain_mod._load_run_config(str(cfg_path))
    assert loaded["schema_version"] == "flagship_code_rsi_v1"
