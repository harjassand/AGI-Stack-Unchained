from __future__ import annotations

import json
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ge_sh1_registry_state_dir_rel_is_subrun_root_dot() -> None:
    # CCAP-producing GE SH-1 optimizer writes state at the subrun root (promotion/, ccap/, ...),
    # not under daemon/<campaign>/state. If this is wrong, unified runs can SAFE_HALT due to
    # subverifier "MISSING_STATE_INPUT" when hashing the replay state dir.
    registry_paths = [
        Path("campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json"),
        Path("campaigns/rsi_omega_daemon_v18_0_prod/omega_capability_registry_v2.json"),
    ]
    for path in registry_paths:
        payload = _load(path)
        rows = payload.get("capabilities", [])
        assert isinstance(rows, list)
        ge_rows = [r for r in rows if isinstance(r, dict) and r.get("campaign_id") == "rsi_ge_symbiotic_optimizer_sh1_v0_1"]
        assert len(ge_rows) == 1
        assert ge_rows[0].get("state_dir_rel") == "."

