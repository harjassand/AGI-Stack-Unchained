from __future__ import annotations

from pathlib import Path

from cdel.v18_0 import omega_observer_v1 as observer
from cdel.v18_0.omega_common_v1 import OmegaV18Error, Q32_ONE


def _missing_artifact(**_kwargs):  # noqa: ANN003
    raise OmegaV18Error("INVALID:MISSING_STATE_INPUT")


def test_metasearch_metric_uses_neutral_fallback_when_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(observer, "_resolve_artifact_path", _missing_artifact)
    metric_q32, source = observer._load_metasearch_metric(root=tmp_path, index={})
    assert metric_q32 == int(Q32_ONE)
    assert str(source.get("schema_id", "")) == "metasearch_compute_report_v1"
    assert str(source.get("producer_campaign_id", "")) == "rsi_sas_metasearch_v16_1"
    assert str(source.get("producer_run_id", "")) == "observer_fallback"
    assert str(source.get("artifact_hash", "")).startswith("sha256:")


def test_hotloop_metric_uses_zero_fallback_when_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(observer, "_resolve_artifact_path", _missing_artifact)
    metric_q32, source = observer._load_hotloop_metric(root=tmp_path, index={})
    assert metric_q32 == 0
    assert str(source.get("schema_id", "")) == "kernel_hotloop_report_v1"
    assert str(source.get("producer_campaign_id", "")) == "rsi_sas_val_v17_0"
    assert str(source.get("producer_run_id", "")) == "observer_fallback"
    assert str(source.get("artifact_hash", "")).startswith("sha256:")


def test_build_metric_uses_zero_fallback_when_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(observer, "_resolve_artifact_path", _missing_artifact)
    metric_q32, source = observer._load_build_metric(root=tmp_path, index={})
    assert metric_q32 == 0
    assert str(source.get("schema_id", "")) == "sas_system_perf_report_v1"
    assert str(source.get("producer_campaign_id", "")) == "rsi_sas_system_v14_0"
    assert str(source.get("producer_run_id", "")) == "observer_fallback"
    assert str(source.get("artifact_hash", "")).startswith("sha256:")


def test_science_metric_uses_zero_fallback_when_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(observer, "_resolve_artifact_path", _missing_artifact)
    metric_q32, source = observer._load_science_metric_global(root=tmp_path, index={})
    assert metric_q32 == 0
    assert str(source.get("schema_id", "")) == "sas_science_promotion_bundle_v1"
    assert str(source.get("producer_campaign_id", "")) == "rsi_sas_science_v13_0"
    assert str(source.get("producer_run_id", "")) == "observer_fallback"
    assert str(source.get("artifact_hash", "")).startswith("sha256:")
