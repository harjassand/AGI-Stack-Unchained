from __future__ import annotations

import shutil
from pathlib import Path

from .utils import latest_file, load_json, pack_path, repo_root, run_tick_with_pack, verify_valid


def test_prev_tick_perf_signal_observed_when_prev_run_is_under_runs(tmp_path) -> None:
    series_root = repo_root() / "runs" / f"zz_test_prev_tick_perf_{tmp_path.name}"
    shutil.rmtree(series_root, ignore_errors=True)
    series_root.mkdir(parents=True, exist_ok=True)
    try:
        _, state_dir_1 = run_tick_with_pack(
            tmp_path=series_root,
            campaign_pack=pack_path(),
            tick_u64=1,
        )
        perf_files = sorted((state_dir_1 / "perf").glob("sha256_*.omega_tick_perf_v1.json"))
        assert perf_files

        _, state_dir_2 = run_tick_with_pack(
            tmp_path=series_root,
            campaign_pack=pack_path(),
            tick_u64=2,
            prev_state_dir=state_dir_1,
        )
        observation = load_json(latest_file(state_dir_2 / "observations", "sha256_*.omega_observation_report_v1.json"))
        metrics = observation.get("metrics")
        assert isinstance(metrics, dict)
        assert int(metrics.get("previous_tick_total_ns_u64", 0)) > 0

        sources = observation.get("sources")
        assert isinstance(sources, list)
        assert any(isinstance(row, dict) and row.get("schema_id") == "omega_tick_perf_v1" for row in sources)

        assert verify_valid(state_dir_2) == "VALID"
    finally:
        shutil.rmtree(series_root, ignore_errors=True)
