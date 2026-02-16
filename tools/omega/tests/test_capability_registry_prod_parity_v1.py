from __future__ import annotations

import json
from pathlib import Path

_TARGET_CAMPAIGN_ID = "rsi_sas_code_v12_0"
_REGISTRY_PATHS = (
    "campaigns/rsi_omega_daemon_v18_0_prod/omega_capability_registry_v2.json",
    "daemon/rsi_omega_daemon_v18_0_prod/config/omega_capability_registry_v2.json",
    "daemon/rsi_omega_daemon_v18_0/config/omega_capability_registry_v2.json",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _cooldown_ticks_u64(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list):
        raise AssertionError(f"invalid capability registry shape: {path.as_posix()}")
    for row in capabilities:
        if isinstance(row, dict) and str(row.get("campaign_id", "")) == _TARGET_CAMPAIGN_ID:
            return int(row.get("cooldown_ticks_u64", -1))
    raise AssertionError(f"missing {_TARGET_CAMPAIGN_ID} in {path.as_posix()}")


def test_sas_code_cooldown_parity_in_prod_registries() -> None:
    root = _repo_root()
    for rel in _REGISTRY_PATHS:
        path = root / rel
        assert path.exists() and path.is_file()
        cooldown_u64 = _cooldown_ticks_u64(path)
        assert cooldown_u64 <= 1, f"expected cooldown<=1 for {_TARGET_CAMPAIGN_ID} in {rel}, got {cooldown_u64}"
