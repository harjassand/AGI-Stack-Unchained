from __future__ import annotations

import json
from pathlib import Path

from cdel.v18_0 import omega_observer_v1 as observer
from cdel.v18_0.omega_common_v1 import OmegaV18Error
from cdel.v18_0.omega_observer_index_v1 import load_index, store_index


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _seed_valid_artifacts(root: Path) -> None:
    _write_json(
        root
        / "runs"
        / "rsi_sas_metasearch_v16_1_demo_010"
        / "daemon"
        / "rsi_sas_metasearch_v16_1"
        / "state"
        / "reports"
        / "sha256_meta.metasearch_compute_report_v1.json",
        {
            "schema_version": "metasearch_compute_report_v1",
            "c_base_work_cost_total": 10,
            "c_cand_work_cost_total": 4,
        },
    )
    _write_json(
        root
        / "runs"
        / "rsi_sas_val_v17_0_demo_010"
        / "daemon"
        / "rsi_sas_val_v17_0"
        / "state"
        / "hotloop"
        / "sha256_hotloop.kernel_hotloop_report_v1.json",
        {
            "schema_version": "kernel_hotloop_report_v1",
            "top_loops": [{"bytes": 8}, {"bytes": 2}],
        },
    )
    _write_json(
        root
        / "runs"
        / "rsi_sas_system_v14_0_demo_010"
        / "daemon"
        / "rsi_sas_system_v14_0"
        / "state"
        / "artifacts"
        / "sha256_perf.sas_system_perf_report_v1.json",
        {
            "schema_version": "sas_system_perf_report_v1",
            "cand_cost_total": 1,
            "ref_cost_total": 3,
        },
    )
    _write_json(
        root
        / "runs"
        / "rsi_sas_science_v13_0_demo_010"
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
                        "q": "222",
                    }
                }
            },
        },
    )


def test_observer_index_rejects_escape_paths(tmp_path, monkeypatch) -> None:
    _seed_valid_artifacts(tmp_path)
    store_index(
        tmp_path,
        {
            "schema_version": "omega_observer_index_v1",
            "entries": {
                "metasearch_compute_report_v1": {"path_rel": "../evil.json"},
                "kernel_hotloop_report_v1": {"path_rel": "meta-core/secret.json"},
            },
        },
    )

    monkeypatch.setattr(observer, "repo_root", lambda: tmp_path)

    try:
        report, _digest = observer.observe(
            tick_u64=1,
            active_manifest_hash="sha256:" + ("a" * 64),
            policy_hash="sha256:" + ("b" * 64),
            registry_hash="sha256:" + ("c" * 64),
            objectives_hash="sha256:" + ("d" * 64),
        )
        assert int(report["metrics"]["science_rmse_q32"]["q"]) == 222
        assert "OBJ_EXPAND_CAPABILITIES" in report["metrics"]
        assert "OBJ_MAXIMIZE_SCIENCE" in report["metrics"]
        assert "OBJ_MAXIMIZE_SPEED" in report["metrics"]
    except OmegaV18Error as exc:
        assert "SCHEMA_FAIL" in str(exc)
        return

    index = load_index(tmp_path)
    entry = ((index.get("entries") or {}).get("metasearch_compute_report_v1") or {}).get("path_rel")
    assert isinstance(entry, str)
    assert entry.startswith("runs/")
    assert ".." not in Path(entry).parts
