from __future__ import annotations

import json
import sys
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def test_overnight_runner_meta_core_mode_production_does_not_call_sandbox(tmp_path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    campaign_pack = tmp_path / "campaign_pack.json"
    campaign_pack.write_text(json.dumps({"schema_version": "dummy"}) + "\n", encoding="utf-8")

    worktree = tmp_path / "worktree"
    (worktree / "meta-core").mkdir(parents=True, exist_ok=True)

    def _raise_if_sandbox_called(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("sandbox must not be created in production mode")

    def _prepare_worktree(*, repo_root: Path, branch: str, worktree_dir: Path) -> Path:  # noqa: ARG001
        return worktree

    def _fake_run_tick(*, campaign_pack: Path, out_dir: Path, tick_u64: int, prev_state_dir: Path | None = None):  # noqa: ARG001
        return {"safe_halt": True}

    class _FakeVerifierClient:
        def __init__(self, *, repo_root: Path):  # noqa: ARG002
            pass

        def verify(self, state_dir: Path, *, mode: str = "full"):  # noqa: ARG002
            return True, "VALID", "VALID"

        def close(self) -> None:
            return None

    monkeypatch.setattr(runner, "create_meta_core_sandbox", _raise_if_sandbox_called)
    monkeypatch.setattr(runner, "_assert_livewire_repo_clean", lambda _repo_root: None)
    monkeypatch.setattr(runner, "_prepare_livewire_worktree", _prepare_worktree)
    monkeypatch.setattr(runner, "_load_run_tick", lambda _repo_root: _fake_run_tick)
    monkeypatch.setattr(runner, "OmegaVerifierClient", _FakeVerifierClient)
    monkeypatch.setattr(runner, "_run_benchmark_summary", lambda run_dir, runs_root: None)
    monkeypatch.setattr(runner, "_stage_and_commit_livewire_tick", lambda **kwargs: None)

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
    ]
    monkeypatch.setattr(sys, "argv", argv)

    runner.main()

    run_dirs = sorted(runs_root.glob("omega_overnight_*"))
    assert run_dirs
    report_path = run_dirs[-1] / "OMEGA_OVERNIGHT_REPORT_v1.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["meta_core_mode"] == "production"
    assert "perf_rates" in report
    assert "auto_rollback" in report
    assert bool(((report.get("auto_rollback") or {}).get("rollback_applied_b", False))) is False
    progress = ((report.get("polymath") or {}).get("progress") or {})
    assert int(progress.get("domains_bootstrapped_delta_u64", 0)) == 0
    assert int(progress.get("top_void_score_delta_q32", 0)) == 0
    assert int(progress.get("coverage_ratio_delta_q32", 0)) == 0
