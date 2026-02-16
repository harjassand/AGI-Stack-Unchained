from __future__ import annotations

import json
from pathlib import Path

from tools.omega import omega_benchmark_suite_v1 as benchmark


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def test_gate_p_tracks_scout_subrun_void_hashes(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    state_dir = run_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state"

    for tick_u64 in (1, 2):
        _write_json(
            state_dir / "observations" / f"sha256_obs_{tick_u64}.omega_observation_report_v1.json",
            {
                "schema_version": "omega_observation_report_v1",
                "tick_u64": int(tick_u64),
                "metrics": {"domains_bootstrapped_u64": 0, "polymath_portfolio_score_q32": {"q": 0}},
                "sources": [
                    {
                        "schema_id": "polymath_void_report_v1",
                        "artifact_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    }
                ],
            },
        )

    for tick_u64, action, topic in (
        (1, "action_a", "topic_a"),
        (2, "action_b", "topic_b"),
    ):
        subrun_rel = f"subruns/{action}_rsi_polymath_scout_v1"
        _write_json(
            state_dir / "dispatch" / action / f"sha256_{action}.omega_dispatch_receipt_v1.json",
            {
                "schema_version": "omega_dispatch_receipt_v1",
                "tick_u64": int(tick_u64),
                "campaign_id": "rsi_polymath_scout_v1",
                "return_code": 0,
                "subrun": {"subrun_root_rel": subrun_rel},
            },
        )
        _write_jsonl(
            state_dir / subrun_rel / "polymath" / "registry" / "polymath_void_report_v1.jsonl",
            [
                {
                    "schema_version": "polymath_void_report_v1",
                    "topic_id": topic,
                    "void_score_q32": {"q": 1 << 31},
                }
            ],
        )

    stats = benchmark._polymath_gate_stats(run_dir)
    assert int(stats["scout_dispatch_u64"]) == 2
    assert int(stats["void_hash_history_u64"]) == 2
    assert bool(stats["void_hash_changed_b"])
    assert bool(stats["gate_p_pass"])
