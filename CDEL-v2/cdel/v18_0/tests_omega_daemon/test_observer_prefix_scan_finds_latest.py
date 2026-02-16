from __future__ import annotations

import json
from pathlib import Path

from cdel.v18_0 import omega_observer_v1 as observer
from cdel.v18_0.omega_observer_index_v1 import load_index


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_observer_prefix_scan_finds_latest(tmp_path, monkeypatch) -> None:
    older_meta = (
        tmp_path
        / "runs"
        / "rsi_sas_metasearch_v16_1_demo_001"
        / "daemon"
        / "rsi_sas_metasearch_v16_1"
        / "state"
        / "reports"
        / "sha256_0001.metasearch_compute_report_v1.json"
    )
    newer_meta = (
        tmp_path
        / "runs"
        / "rsi_sas_metasearch_v16_1_demo_002"
        / "daemon"
        / "rsi_sas_metasearch_v16_1"
        / "state"
        / "reports"
        / "sha256_9999.metasearch_compute_report_v1.json"
    )
    _write_json(
        older_meta,
        {
            "schema_version": "metasearch_compute_report_v1",
            "c_base_work_cost_total": 11,
            "c_cand_work_cost_total": 7,
        },
    )
    _write_json(
        newer_meta,
        {
            "schema_version": "metasearch_compute_report_v1",
            "c_base_work_cost_total": 12,
            "c_cand_work_cost_total": 3,
        },
    )

    _write_json(
        tmp_path
        / "runs"
        / "rsi_sas_val_v17_0_demo_001"
        / "daemon"
        / "rsi_sas_val_v17_0"
        / "state"
        / "hotloop"
        / "sha256_hotloop.kernel_hotloop_report_v1.json",
        {
            "schema_version": "kernel_hotloop_report_v1",
            "top_loops": [{"bytes": 9}, {"bytes": 1}],
        },
    )
    _write_json(
        tmp_path
        / "runs"
        / "rsi_sas_system_v14_0_demo_001"
        / "daemon"
        / "rsi_sas_system_v14_0"
        / "state"
        / "artifacts"
        / "sha256_perf.sas_system_perf_report_v1.json",
        {
            "schema_version": "sas_system_perf_report_v1",
            "cand_cost_total": 3,
            "ref_cost_total": 7,
        },
    )
    _write_json(
        tmp_path
        / "runs"
        / "rsi_sas_science_v13_0_demo_001"
        / "daemon"
        / "rsi_sas_science_v13_0"
        / "state"
        / "promotion"
        / "sha256_science.sas_science_promotion_bundle_v1.json",
        {
            "schema_version": "sas_science_promotion_bundle_v1",
            "discovery_bundle": {
                "heldout_metrics": {
                    "rmse_pos1_q32": {
                        "q": "456",
                    }
                }
            },
        },
    )

    monkeypatch.setattr(observer, "repo_root", lambda: tmp_path)

    report, _digest = observer.observe(
        tick_u64=1,
        active_manifest_hash="sha256:" + ("1" * 64),
        policy_hash="sha256:" + ("2" * 64),
        registry_hash="sha256:" + ("3" * 64),
        objectives_hash="sha256:" + ("4" * 64),
    )
    assert int(report["metrics"]["science_rmse_q32"]["q"]) == 456
    assert "OBJ_EXPAND_CAPABILITIES" in report["metrics"]
    assert "OBJ_MAXIMIZE_SCIENCE" in report["metrics"]
    assert "OBJ_MAXIMIZE_SPEED" in report["metrics"]

    index = load_index(tmp_path)
    entry = ((index.get("entries") or {}).get("metasearch_compute_report_v1") or {}).get("path_rel")
    assert entry == newer_meta.relative_to(tmp_path).as_posix()
