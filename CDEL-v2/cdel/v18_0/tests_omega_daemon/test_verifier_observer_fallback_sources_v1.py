from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0 import verify_rsi_omega_daemon_v1 as verifier
from cdel.v18_0.omega_common_v1 import OmegaV18Error, canon_hash_obj


def _fallback_source(*, schema_id: str, campaign_id: str) -> dict[str, str]:
    artifact_hash = canon_hash_obj(
        {
            "schema_id": schema_id,
            "campaign_id": campaign_id,
            "reason_code": "MISSING_STATE_INPUT",
        }
    )
    return {
        "schema_id": schema_id,
        "artifact_hash": artifact_hash,
        "producer_campaign_id": campaign_id,
        "producer_run_id": "observer_fallback",
    }


def test_verifier_accepts_observer_fallback_sources(tmp_path: Path) -> None:
    rows = [
        ("metasearch_compute_report_v1", "rsi_sas_metasearch_v16_1"),
        ("kernel_hotloop_report_v1", "rsi_sas_val_v17_0"),
        ("sas_system_perf_report_v1", "rsi_sas_system_v14_0"),
        ("sas_science_promotion_bundle_v1", "rsi_sas_science_v13_0"),
    ]
    for schema_id, campaign_id in rows:
        source = _fallback_source(schema_id=schema_id, campaign_id=campaign_id)
        got_schema_id, payload = verifier._read_observer_source_artifact(root=tmp_path, source=source)
        assert got_schema_id == schema_id
        assert isinstance(payload, dict)


def test_verifier_rejects_bad_observer_fallback_hash(tmp_path: Path) -> None:
    source = _fallback_source(schema_id="metasearch_compute_report_v1", campaign_id="rsi_sas_metasearch_v16_1")
    source["artifact_hash"] = "sha256:" + ("0" * 64)
    with pytest.raises(OmegaV18Error):
        verifier._read_observer_source_artifact(root=tmp_path, source=source)
