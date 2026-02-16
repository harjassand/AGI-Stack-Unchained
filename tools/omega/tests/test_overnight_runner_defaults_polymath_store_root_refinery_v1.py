from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def _write_registry(path: Path) -> None:
    payload = {
        "schema_version": "omega_capability_registry_v2",
        "capabilities": [
            {"campaign_id": "rsi_sas_code_v12_0", "enabled": True},
            {"campaign_id": "rsi_sas_metasearch_v16_1", "enabled": True},
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_refinery_defaults_polymath_store_root_when_missing(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    campaign_src = tmp_path / "campaign_src"
    campaign_src.mkdir(parents=True, exist_ok=True)
    campaign_pack = campaign_src / "campaign_pack.json"
    campaign_pack.write_text(json.dumps({"schema_version": "dummy"}) + "\n", encoding="utf-8")
    _write_registry(campaign_src / "omega_capability_registry_v2.json")

    worktree = tmp_path / "worktree"
    (worktree / "meta-core").mkdir(parents=True, exist_ok=True)

    fake_origin = tmp_path / "origin"
    fake_origin.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runner, "_ORIGINAL_REPO_ROOT", fake_origin)

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

    def _fake_subprocess_run(cmd, **kwargs):  # noqa: ANN001
        _ = kwargs
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="abc123\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def _fake_benchmark(run_dir: Path, runs_root: Path) -> None:  # noqa: ARG001
        (run_dir / "OMEGA_BENCHMARK_SUMMARY_v1.md").write_text(
            "\n".join(
                [
                    "# OMEGA Benchmark Summary (test)",
                    "- % RUNAWAY_BLOCKED NOOP: **0.00%**",
                    "- Gate A (x): **PASS**",
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
                    "median_stps_non_noop_q32": 0,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

    captured: dict[str, str] = {}

    def _fake_seed_flagships(*, repo_root: Path, store_root: Path, summary_path: Path) -> dict[str, object]:  # noqa: ARG001
        captured["seed_store_root"] = store_root.as_posix()
        summary_path.write_text(json.dumps({"status": "OK"}, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        return {"status": "OK"}

    def _fake_refinery_proposer(  # noqa: PLR0913
        *,
        repo_root: Path,  # noqa: ARG001
        store_root: Path,
        workers: int,  # noqa: ARG001
        max_domains: int,  # noqa: ARG001
        summary_path: Path,
    ) -> dict[str, object]:
        captured["proposer_store_root"] = store_root.as_posix()
        summary_path.write_text(
            json.dumps({"status": "OK", "proposals_generated_u64": 0}, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return {"status": "OK", "proposals_generated_u64": 0}

    monkeypatch.delenv("OMEGA_POLYMATH_STORE_ROOT", raising=False)
    monkeypatch.setattr(runner, "_assert_livewire_repo_clean", lambda _repo_root: None)
    monkeypatch.setattr(runner, "_prepare_livewire_worktree", _prepare_worktree)
    monkeypatch.setattr(runner, "_sync_campaign_fixtures_into_worktree", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "_load_run_tick", lambda _repo_root: _fake_run_tick)
    monkeypatch.setattr(runner, "OmegaVerifierClient", _FakeVerifierClient)
    monkeypatch.setattr(runner, "_run_benchmark_summary", _fake_benchmark)
    monkeypatch.setattr(runner, "_run_polymath_seed_flagships", _fake_seed_flagships)
    monkeypatch.setattr(runner, "_run_polymath_refinery_proposer", _fake_refinery_proposer)
    monkeypatch.setattr(runner, "_stage_and_commit_livewire_tick", lambda **_kwargs: None)
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
        "--profile",
        "refinery",
        "--enable_polymath_refinery_proposer",
        "1",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    runner.main()

    expected_store = (fake_origin / ".omega_cache" / "polymath" / "store").resolve().as_posix()
    assert captured.get("seed_store_root") == expected_store
    assert captured.get("proposer_store_root") == expected_store

    run_dirs = sorted(runs_root.glob("omega_overnight_*"))
    assert run_dirs
    report = json.loads((run_dirs[-1] / "OMEGA_OVERNIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    assert report.get("termination_reason") != "MISSING_POLYMATH_STORE_ROOT"
