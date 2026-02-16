from __future__ import annotations

import json
from pathlib import Path

from cdel.v18_0 import omega_observer_v1 as observer
from cdel.v18_0.omega_observer_index_v1 import store_index


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _seed_observer_inputs(root: Path) -> dict[str, Path]:
    rows = {
        "metasearch_compute_report_v1": root
        / "runs"
        / "rsi_sas_metasearch_v16_1_demo_001"
        / "daemon"
        / "rsi_sas_metasearch_v16_1"
        / "state"
        / "reports"
        / "sha256_a.metasearch_compute_report_v1.json",
        "kernel_hotloop_report_v1": root
        / "runs"
        / "rsi_sas_val_v17_0_demo_001"
        / "daemon"
        / "rsi_sas_val_v17_0"
        / "state"
        / "hotloop"
        / "sha256_b.kernel_hotloop_report_v1.json",
        "sas_system_perf_report_v1": root
        / "runs"
        / "rsi_sas_system_v14_0_demo_001"
        / "daemon"
        / "rsi_sas_system_v14_0"
        / "state"
        / "artifacts"
        / "sha256_c.sas_system_perf_report_v1.json",
        "sas_science_promotion_bundle_v1": root
        / "runs"
        / "rsi_sas_science_v13_0_demo_001"
        / "daemon"
        / "rsi_sas_science_v13_0"
        / "state"
        / "promotion"
        / "sha256_d.sas_science_promotion_bundle_v1.json",
    }
    _write_json(
        rows["metasearch_compute_report_v1"],
        {
            "schema_version": "metasearch_compute_report_v1",
            "c_base_work_cost_total": 10,
            "c_cand_work_cost_total": 5,
        },
    )
    _write_json(
        rows["kernel_hotloop_report_v1"],
        {
            "schema_version": "kernel_hotloop_report_v1",
            "top_loops": [{"bytes": 7}, {"bytes": 3}],
        },
    )
    _write_json(
        rows["sas_system_perf_report_v1"],
        {
            "schema_version": "sas_system_perf_report_v1",
            "cand_cost_total": 2,
            "ref_cost_total": 5,
        },
    )
    _write_json(
        rows["sas_science_promotion_bundle_v1"],
        {
            "schema_version": "sas_science_promotion_bundle_v1",
            "discovery_bundle": {
                "heldout_metrics": {
                    "rmse_pos1_q32": {
                        "q": "321",
                    }
                }
            },
        },
    )
    return rows


def test_observer_uses_index_fastpath(tmp_path, monkeypatch) -> None:
    paths = _seed_observer_inputs(tmp_path)
    store_index(
        tmp_path,
        {
            "schema_version": "omega_observer_index_v1",
            "entries": {
                key: {"path_rel": path.relative_to(tmp_path).as_posix()}
                for key, path in paths.items()
            },
        },
    )

    monkeypatch.setattr(observer, "repo_root", lambda: tmp_path)

    orig_glob = Path.glob

    def _guarded_glob(self: Path, pattern: str):
        if "**" in pattern:
            raise AssertionError("observer used recursive glob")
        return orig_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", _guarded_glob)

    report, _digest = observer.observe(
        tick_u64=1,
        active_manifest_hash="sha256:" + ("a" * 64),
        policy_hash="sha256:" + ("b" * 64),
        registry_hash="sha256:" + ("c" * 64),
        objectives_hash="sha256:" + ("d" * 64),
    )

    assert int(report["metrics"]["science_rmse_q32"]["q"]) == 321
