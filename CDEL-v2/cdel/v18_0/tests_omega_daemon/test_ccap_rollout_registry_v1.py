from __future__ import annotations

import json
from pathlib import Path


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ccap_rollout_is_scoped_to_disabled_ccap_families() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    registry_paths = [
        repo_root / "campaigns" / "rsi_omega_daemon_v18_0" / "omega_capability_registry_v2.json",
        repo_root / "campaigns" / "rsi_omega_daemon_v18_0_prod" / "omega_capability_registry_v2.json",
        repo_root / "daemon" / "rsi_omega_daemon_v18_0" / "config" / "omega_capability_registry_v2.json",
        repo_root / "daemon" / "rsi_omega_daemon_v18_0_prod" / "config" / "omega_capability_registry_v2.json",
    ]

    for path in registry_paths:
        payload = _load(path)
        caps = payload.get("capabilities")
        assert isinstance(caps, list), str(path)
        enabled = [row for row in caps if isinstance(row, dict) and row.get("enable_ccap") == 1]
        assert len(enabled) == 2, str(path)
        by_capability = {str(row.get("capability_id", "")): row for row in enabled}

        assert set(by_capability.keys()) == {"RSI_POLYMATH_SCOUT", "RSI_GE_SH1_OPTIMIZER"}, str(path)

        scout = by_capability["RSI_POLYMATH_SCOUT"]
        assert scout.get("campaign_id") == "rsi_polymath_scout_v1", str(path)
        assert scout.get("enabled") is False, str(path)
        assert scout.get("verifier_module") == "cdel.v18_0.verify_ccap_v1", str(path)
        assert str(scout.get("promotion_bundle_rel", "")).endswith(".omega_promotion_bundle_ccap_v1.json"), str(path)

        ge_sh1 = by_capability["RSI_GE_SH1_OPTIMIZER"]
        assert ge_sh1.get("campaign_id") == "rsi_ge_symbiotic_optimizer_sh1_v0_1", str(path)
        assert ge_sh1.get("enabled") is False, str(path)
        assert ge_sh1.get("verifier_module") == "cdel.v18_0.verify_ccap_v1", str(path)
        assert str(ge_sh1.get("promotion_bundle_rel", "")).endswith(".omega_promotion_bundle_ccap_v1.json"), str(path)
