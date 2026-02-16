from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def test_overnight_runner_writes_rollback_metadata_on_gate_failure(tmp_path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    campaign_pack = tmp_path / "campaign_pack.json"
    campaign_pack.write_text(json.dumps({"schema_version": "dummy"}) + "\n", encoding="utf-8")
    (tmp_path / "omega_capability_registry_v2.json").write_text(
        json.dumps({"schema_version": "omega_capability_registry_v2", "capabilities": []}, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    worktree = tmp_path / "worktree"
    (worktree / "meta-core").mkdir(parents=True, exist_ok=True)

    def _prepare_worktree(*, repo_root: Path, branch: str, worktree_dir: Path) -> Path:  # noqa: ARG001
        return worktree

    def _fake_run_tick(*, campaign_pack: Path, out_dir: Path, tick_u64: int, prev_state_dir: Path | None = None):  # noqa: ARG001
        return {"safe_halt": False}

    class _FakeVerifierClient:
        def __init__(self, *, repo_root: Path):  # noqa: ARG002
            pass

        def verify(self, state_dir: Path, *, mode: str = "full"):  # noqa: ARG002
            return True, "VALID", "VALID"

        def close(self) -> None:
            return None

    reset_targets: list[str] = []

    def _fake_subprocess_run(cmd, **kwargs):  # noqa: ANN001
        _ = kwargs
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="abc123\n", stderr="")
        if cmd[:3] == ["git", "reset", "--hard"]:
            reset_targets.append(str(cmd[3]))
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def _fake_benchmark(run_dir: Path, runs_root: Path) -> None:  # noqa: ARG001
        (run_dir / "OMEGA_BENCHMARK_SUMMARY_v1.md").write_text(
            "\n".join(
                [
                    "# OMEGA Benchmark Summary (test)",
                    "- % RUNAWAY_BLOCKED NOOP: **100.00%**",
                    "- Gate A (x): **FAIL**",
                    "- Gate B (x): **PASS**",
                    "- Gate C (x): **PASS**",
                    "- Gate D (x): **PASS**",
                    "- Gate E (x): **PASS**",
                    "- Gate F (x): **PASS**",
                    "- Gate P (x): **PASS**",
                    "- Gate Q (x): **PASS**",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (run_dir / "OMEGA_PROMOTION_SUMMARY_v1.json").write_text(
            json.dumps(
                {
                    "promoted_u64": 0,
                    "activation_success_u64": 0,
                    "unique_promotions_u64": 0,
                    "unique_activations_applied_u64": 0,
                    "activation_failure_reason_counts": [],
                    "top_touched_paths": [],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        (run_dir / "OMEGA_TIMINGS_AGG_v1.json").write_text(
            json.dumps(
                {
                    "schema_version": "OMEGA_TIMINGS_AGG_v1",
                    "non_noop_ticks_per_min": 0.0,
                    "promotion_ticks_per_min": 0.0,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        (run_dir / "OMEGA_RUN_SCORECARD_v1.json").write_text(
            json.dumps(
                {
                    "schema_version": "omega_run_scorecard_v1",
                    "median_stps_non_noop_q32": 123,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(runner, "_assert_livewire_repo_clean", lambda _repo_root: None)
    monkeypatch.setattr(runner, "_prepare_livewire_worktree", _prepare_worktree)
    monkeypatch.setattr(runner, "_load_run_tick", lambda _repo_root: _fake_run_tick)
    monkeypatch.setattr(runner, "OmegaVerifierClient", _FakeVerifierClient)
    monkeypatch.setattr(runner, "_run_benchmark_summary", _fake_benchmark)
    monkeypatch.setattr(runner, "_stage_and_commit_livewire_tick", lambda **kwargs: None)
    monkeypatch.setattr(runner.subprocess, "run", _fake_subprocess_run)

    argv = [
        "omega_overnight_runner_v1.py",
        "--hours",
        "0.01",
        "--meta_core_mode",
        "production",
        "--runs_root",
        str(runs_root),
        "--campaign_pack",
        str(campaign_pack),
        "--polymath_scout_every_ticks",
        "1",
        "--stall_watchdog_checkpoints",
        "1000",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    runner.main()

    run_dirs = sorted(runs_root.glob("omega_overnight_*"))
    assert run_dirs
    report = json.loads((run_dirs[-1] / "OMEGA_OVERNIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    auto_rollback = report.get("auto_rollback") or {}
    assert bool(auto_rollback.get("triggered_by_gate_regression_or_failure_b", False)) is True
    assert bool(auto_rollback.get("rollback_applied_b", False)) is True
    assert str(auto_rollback.get("rollback_target_sha", "")) == "abc123"
    assert reset_targets == ["abc123"]
