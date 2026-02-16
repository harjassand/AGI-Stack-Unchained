from __future__ import annotations

import json
from pathlib import Path

from tools.omega.omega_skill_manifest_v1 import generate_skill_manifest


def _write_registry(path: Path, *, enabled: bool) -> None:
    payload = {
        "schema_version": "omega_capability_registry_v2",
        "capabilities": [
            {
                "capability_id": "RSI_SAS_CODE",
                "campaign_id": "rsi_sas_code_v12_0",
                "orchestrator_module": "orchestrator.rsi_sas_code_v12_0",
                "verifier_module": "cdel.v12_0.verify_rsi_sas_code_v1",
                "enabled": bool(enabled),
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_generate_skill_manifest_collects_and_dedupes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "CDEL-v2" / "cdel" / "v12_0").mkdir(parents=True, exist_ok=True)
    (repo_root / "CDEL-v2" / "cdel" / "v12_0" / "verify_rsi_sas_code_v1.py").write_text(
        "def verify(*args, **kwargs):\n    return 'VALID'\n",
        encoding="utf-8",
    )

    _write_registry(
        repo_root / "campaigns" / "rsi_omega_daemon_v18_0" / "omega_capability_registry_v2.json",
        enabled=True,
    )
    _write_registry(
        repo_root / "daemon" / "rsi_omega_daemon_v18_0" / "config" / "omega_capability_registry_v2.json",
        enabled=False,
    )

    manifest = generate_skill_manifest(repo_root=repo_root)
    assert manifest.get("schema_version") == "OMEGA_SKILL_MANIFEST_v1"
    skills = manifest.get("skills")
    assert isinstance(skills, list)
    assert len(skills) == 1
    row = skills[0]
    assert row.get("skill_id") == "SAS_CODE_V12_0"
    assert row.get("cdel_version") == "v12_0"
    assert row.get("family") == "CODE"
    assert row.get("capability_id") == "RSI_SAS_CODE"
    assert row.get("campaign_id") == "rsi_sas_code_v12_0"
    assert row.get("orchestrator_module") == "orchestrator.rsi_sas_code_v12_0"
    assert row.get("verifier_module") == "cdel.v12_0.verify_rsi_sas_code_v1"
    assert bool(row.get("enabled_by_default_b")) is True
