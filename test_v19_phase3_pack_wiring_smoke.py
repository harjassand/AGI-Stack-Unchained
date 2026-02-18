from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent

PACK_PATHS = [
    REPO_ROOT
    / "campaigns"
    / "rsi_omega_daemon_v19_0_phase3_mutator"
    / "rsi_omega_daemon_pack_v1.json",
    REPO_ROOT
    / "campaigns"
    / "rsi_omega_daemon_v19_0_phase3_market_mutator"
    / "rsi_omega_daemon_pack_v1.json",
    REPO_ROOT
    / "campaigns"
    / "rsi_omega_daemon_v19_0_phase3_death_test"
    / "rsi_omega_daemon_pack_v1.json",
    REPO_ROOT
    / "campaigns"
    / "rsi_omega_daemon_v19_0_phase3_bench"
    / "rsi_omega_daemon_pack_v1.json",
    REPO_ROOT
    / "campaigns"
    / "rsi_omega_daemon_v19_0_phase3_market_toy"
    / "rsi_omega_daemon_pack_v1.json",
]

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"expected JSON object at {path}")
    return payload


def _smoke_pack(pack_path: Path) -> None:
    assert pack_path.exists(), f"missing pack: {pack_path}"
    pack = _load_json(pack_path)
    pack_dir = pack_path.parent

    for key, value in pack.items():
        if not key.endswith("_rel"):
            continue
        if not isinstance(value, str) or not value.strip():
            continue
        target = (pack_dir / value).resolve()
        assert target.exists(), f"pack {pack_path}: field {key} points to missing path: {target}"

    registry_rel = str(pack.get("omega_capability_registry_rel", "")).strip()
    assert registry_rel, f"pack {pack_path}: missing omega_capability_registry_rel"
    registry_path = (pack_dir / registry_rel).resolve()
    assert registry_path.exists(), f"pack {pack_path}: registry path is missing: {registry_path}"

    registry = _load_json(registry_path)
    capabilities = registry.get("capabilities")
    assert isinstance(capabilities, list), f"pack {pack_path}: registry.capabilities must be a list"

    for row in capabilities:
        assert isinstance(row, dict), f"pack {pack_path}: capability entries must be objects"
        capability_id = str(row.get("capability_id", "<unknown>"))

        campaign_pack_rel = str(row.get("campaign_pack_rel", "")).strip()
        if campaign_pack_rel:
            campaign_pack_path = (REPO_ROOT / campaign_pack_rel).resolve()
            assert campaign_pack_path.exists(), (
                f"{capability_id}: campaign_pack_rel points to missing path: {campaign_pack_path}"
            )

        if not bool(row.get("enabled", False)):
            continue

        for field_name in ("orchestrator_module", "verifier_module"):
            module_name = str(row.get(field_name, "")).strip()
            if not module_name.startswith(("orchestrator.", "cdel.")):
                continue
            try:
                importlib.import_module(module_name)
            except Exception as exc:  # noqa: BLE001
                raise AssertionError(
                    f"{capability_id}: failed to import {field_name} module {module_name}: {exc}"
                ) from exc


def test_v19_phase3_pack_wiring_smoke() -> None:
    for path in PACK_PATHS:
        _smoke_pack(path)

