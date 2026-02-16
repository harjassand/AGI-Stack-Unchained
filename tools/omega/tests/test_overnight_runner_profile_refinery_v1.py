from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def _write_registry(path: Path) -> None:
    scout_pack = path.parent / "rsi_polymath_scout_pack_v1.json"
    bootstrap_pack = path.parent / "rsi_polymath_bootstrap_domain_pack_v1.json"
    _write_json = lambda target, payload: target.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _write_json(
        scout_pack,
        {
            "schema_version": "rsi_polymath_scout_pack_v1",
            "void_report_path_rel": "polymath/registry/polymath_void_report_v1.jsonl",
        },
    )
    _write_json(
        bootstrap_pack,
        {
            "schema_version": "rsi_polymath_bootstrap_domain_pack_v1",
            "void_report_path_rel": "polymath/registry/polymath_void_report_v1.jsonl",
        },
    )
    payload = {
        "schema_version": "omega_capability_registry_v2",
        "capabilities": [
            {
                "campaign_id": "rsi_polymath_scout_v1",
                "campaign_pack_rel": scout_pack.as_posix(),
                "enabled": False,
            },
            {
                "campaign_id": "rsi_polymath_bootstrap_domain_v1",
                "campaign_pack_rel": bootstrap_pack.as_posix(),
                "enabled": False,
            },
            {
                "campaign_id": "rsi_polymath_conquer_domain_v1",
                "enabled": False,
            },
            {
                "campaign_id": "rsi_sas_metasearch_v16_1",
                "enabled": True,
            },
            {
                "campaign_id": "rsi_sas_code_v12_0",
                "enabled": True,
            },
            {
                "campaign_id": "rsi_sas_system_v14_0",
                "enabled": True,
            },
        ],
    }
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_prepare_overlay_refinery_disables_metasearch(tmp_path: Path) -> None:
    src = tmp_path / "pack_src"
    src.mkdir(parents=True, exist_ok=True)
    campaign_pack = src / "rsi_omega_daemon_pack_v1.json"
    campaign_pack.write_text(json.dumps({"schema_version": "rsi_omega_daemon_pack_v1"}) + "\n", encoding="utf-8")
    _write_registry(src / "omega_capability_registry_v2.json")

    run_dir = tmp_path / "run"
    overlay_pack = runner._prepare_campaign_pack_overlay(
        campaign_pack=campaign_pack,
        run_dir=run_dir,
        enable_self_optimize_core=False,
        enable_polymath_drive=False,
        enable_polymath_bootstrap=False,
        enable_ge_sh1_optimizer=False,
        ge_pack_overrides=None,
        profile="refinery",
    )

    registry_path = overlay_pack.parent / "omega_capability_registry_v2.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    caps = payload.get("capabilities")
    assert isinstance(caps, list)
    metasearch_rows = [row for row in caps if isinstance(row, dict) and str(row.get("campaign_id", "")) == "rsi_sas_metasearch_v16_1"]
    assert len(metasearch_rows) == 1
    assert bool(metasearch_rows[0].get("enabled", True)) is False
    system_rows = [row for row in caps if isinstance(row, dict) and str(row.get("campaign_id", "")) == "rsi_sas_system_v14_0"]
    assert len(system_rows) == 1
    assert bool(system_rows[0].get("enabled", True)) is False


def test_prepare_overlay_refinery_enables_ge_and_overrides_pack(tmp_path: Path, monkeypatch) -> None:
    fake_repo = tmp_path / "repo"
    ge_src = fake_repo / "campaigns" / "rsi_ge_symbiotic_optimizer_sh1_v0_1"
    ge_src.mkdir(parents=True, exist_ok=True)
    (ge_src / "rsi_ge_symbiotic_optimizer_sh1_pack_v0_1.json").write_text(
        json.dumps(
            {
                "schema_version": "rsi_ge_symbiotic_optimizer_sh1_pack_v0_1",
                "max_ccaps": 1,
                "model_id": "ge-v0_3",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    src = tmp_path / "pack_src"
    src.mkdir(parents=True, exist_ok=True)
    campaign_pack = src / "rsi_omega_daemon_pack_v1.json"
    campaign_pack.write_text(json.dumps({"schema_version": "rsi_omega_daemon_pack_v1"}) + "\n", encoding="utf-8")
    (src / "omega_capability_registry_v2.json").write_text(
        json.dumps(
            {
                "schema_version": "omega_capability_registry_v2",
                "capabilities": [
                    {"campaign_id": "rsi_sas_code_v12_0", "enabled": True},
                    {"campaign_id": "rsi_sas_metasearch_v16_1", "enabled": True},
                    {
                        "campaign_id": "rsi_ge_symbiotic_optimizer_sh1_v0_1",
                        "enabled": False,
                        "campaign_pack_rel": "campaigns/rsi_ge_symbiotic_optimizer_sh1_v0_1/rsi_ge_symbiotic_optimizer_sh1_pack_v0_1.json",
                    },
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(runner, "_REPO_ROOT", fake_repo)
    run_dir = tmp_path / "runs" / "series_one"
    overlay_pack = runner._prepare_campaign_pack_overlay(
        campaign_pack=campaign_pack,
        run_dir=run_dir,
        enable_self_optimize_core=False,
        enable_polymath_drive=False,
        enable_polymath_bootstrap=False,
        enable_ge_sh1_optimizer=True,
        ge_pack_overrides={"max_ccaps": 3, "model_id": "ge-v0_3_test"},
        profile="refinery",
    )

    registry = json.loads((overlay_pack.parent / "omega_capability_registry_v2.json").read_text(encoding="utf-8"))
    caps = registry.get("capabilities") if isinstance(registry, dict) else []
    assert isinstance(caps, list)
    ge_rows = [row for row in caps if isinstance(row, dict) and str(row.get("campaign_id", "")) == "rsi_ge_symbiotic_optimizer_sh1_v0_1"]
    assert len(ge_rows) == 1
    ge_row = ge_rows[0]
    assert bool(ge_row.get("enabled", False)) is True
    assert int(ge_row.get("enable_ccap", 0)) == 1
    assert ge_row.get("campaign_pack_rel") == "runs/series_one/_overnight_pack/rsi_ge_symbiotic_optimizer_sh1_pack_v0_1.json"

    ge_overlay_pack = overlay_pack.parent / "rsi_ge_symbiotic_optimizer_sh1_pack_v0_1.json"
    ge_payload = json.loads(ge_overlay_pack.read_text(encoding="utf-8"))
    assert int(ge_payload.get("max_ccaps", 0)) == 3
    assert str(ge_payload.get("model_id", "")) == "ge-v0_3_test"


def test_refinery_required_gates_exclude_d_and_e() -> None:
    refinery_gates = runner._required_pass_gates("refinery")
    assert refinery_gates == ("A", "B", "C", "F", "P", "Q")
    assert runner._required_pass_gates("unified") == ("A", "B", "C", "D", "E", "F", "P", "Q")

    status = {
        "A": "PASS",
        "B": "PASS",
        "C": "PASS",
        "D": "FAIL",
        "E": "FAIL",
        "F": "PASS",
        "P": "PASS",
        "Q": "PASS",
    }
    assert runner._all_required_gates_pass(status, required_gates=refinery_gates)
    assert not runner._all_required_gates_pass(status, required_gates=runner._required_pass_gates("full"))


def test_inject_pending_goal_keeps_in_synth_cap(tmp_path: Path) -> None:
    goal_queue_path = tmp_path / "goals" / "omega_goal_queue_v1.json"
    goal_queue_path.parent.mkdir(parents=True, exist_ok=True)
    base_goals = [
        {
            "goal_id": f"goal_base_{idx:04d}",
            "capability_id": "RSI_SAS_METASEARCH",
            "status": "PENDING",
        }
        for idx in range(300)
    ]
    goal_queue_path.write_text(
        json.dumps(
            {
                "schema_version": "omega_goal_queue_v1",
                "goals": base_goals,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    runner._inject_pending_goal(
        goal_queue_path=goal_queue_path,
        goal_id="goal_auto_00_ge_sh1_optimizer_0001",
        capability_id="RSI_GE_SH1_OPTIMIZER",
    )

    payload = json.loads(goal_queue_path.read_text(encoding="utf-8"))
    goals = payload.get("goals") if isinstance(payload, dict) else None
    assert isinstance(goals, list)
    assert len(goals) == 300
    assert goals[-1] == {
        "goal_id": "goal_auto_00_ge_sh1_optimizer_0001",
        "capability_id": "RSI_GE_SH1_OPTIMIZER",
        "status": "PENDING",
    }
    assert str(goals[0].get("goal_id", "")) == "goal_base_0000"


def test_refinery_profile_seeds_initial_scout(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    campaign_src = tmp_path / "campaign_src"
    campaign_src.mkdir(parents=True, exist_ok=True)
    campaign_pack = campaign_src / "campaign_pack.json"
    campaign_pack.write_text(json.dumps({"schema_version": "dummy"}) + "\n", encoding="utf-8")
    _write_registry(campaign_src / "omega_capability_registry_v2.json")
    worktree = tmp_path / "worktree"
    (worktree / "meta-core").mkdir(parents=True, exist_ok=True)

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

    scout_calls: list[dict[str, str]] = []

    def _fake_scout(**kwargs):  # noqa: ANN003
        scout_calls.append({"repo_root": str(kwargs.get("repo_root", ""))})
        return True

    monkeypatch.setattr(runner, "_assert_livewire_repo_clean", lambda _repo_root: None)
    monkeypatch.setattr(runner, "_prepare_livewire_worktree", _prepare_worktree)
    monkeypatch.setattr(runner, "_load_run_tick", lambda _repo_root: _fake_run_tick)
    monkeypatch.setattr(runner, "OmegaVerifierClient", _FakeVerifierClient)
    monkeypatch.setattr(runner, "_run_benchmark_summary", _fake_benchmark)
    monkeypatch.setattr(runner, "_stage_and_commit_livewire_tick", lambda **kwargs: None)
    monkeypatch.setattr(runner, "_run_polymath_scout", _fake_scout)
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
        "--profile",
        "refinery",
        "--enable_polymath_drive",
        "1",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    runner.main()
    assert scout_calls


def test_refinery_ignores_non_required_gate_regression(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    campaign_src = tmp_path / "campaign_src"
    campaign_src.mkdir(parents=True, exist_ok=True)
    campaign_pack = campaign_src / "campaign_pack.json"
    campaign_pack.write_text(json.dumps({"schema_version": "dummy"}) + "\n", encoding="utf-8")
    _write_registry(campaign_src / "omega_capability_registry_v2.json")
    worktree = tmp_path / "worktree"
    (worktree / "meta-core").mkdir(parents=True, exist_ok=True)

    def _prepare_worktree(*, repo_root: Path, branch: str, worktree_dir: Path) -> Path:  # noqa: ARG001
        return worktree

    def _fake_run_tick(*, campaign_pack: Path, out_dir: Path, tick_u64: int, prev_state_dir: Path | None = None):  # noqa: ARG001
        return {"safe_halt": tick_u64 >= 2}

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

    gate_status_calls = {"count": 0}

    def _fake_load_gate_statuses(_run_dir: Path) -> dict[str, str]:
        gate_status_calls["count"] += 1
        if gate_status_calls["count"] == 1:
            return {
                "A": "PASS",
                "B": "PASS",
                "C": "PASS",
                "D": "PASS",
                "E": "PASS",
                "F": "PASS",
                "P": "PASS",
                "Q": "PASS",
                "R": "PASS",
            }
        return {
            "A": "PASS",
            "B": "PASS",
            "C": "PASS",
            "D": "FAIL",
            "E": "FAIL",
            "F": "PASS",
            "P": "PASS",
            "Q": "PASS",
            "R": "PASS",
        }

    monkeypatch.setattr(runner, "_assert_livewire_repo_clean", lambda _repo_root: None)
    monkeypatch.setattr(runner, "_prepare_livewire_worktree", _prepare_worktree)
    monkeypatch.setattr(runner, "_load_run_tick", lambda _repo_root: _fake_run_tick)
    monkeypatch.setattr(runner, "OmegaVerifierClient", _FakeVerifierClient)
    monkeypatch.setattr(runner, "_run_benchmark_summary", _fake_benchmark)
    monkeypatch.setattr(runner, "_stage_and_commit_livewire_tick", lambda **kwargs: None)
    monkeypatch.setattr(runner, "_run_polymath_scout", lambda **kwargs: True)
    monkeypatch.setattr(runner, "load_gate_statuses", _fake_load_gate_statuses)
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
        "--profile",
        "refinery",
        "--enable_polymath_drive",
        "1",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    runner.main()

    run_dirs = sorted(runs_root.glob("omega_overnight_*"))
    assert run_dirs
    report = json.loads((run_dirs[-1] / "OMEGA_OVERNIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    assert report["termination_reason"] == "SAFE_HALT"
    assert report["termination_reason"] != "GATE_REGRESSION"
    assert bool((report.get("auto_rollback") or {}).get("triggered_by_gate_regression_or_failure_b", False)) is False
    assert report.get("gate_failures") == []
    assert (report.get("latest_gate_status") or {}).get("D") == "FAIL"


def test_refinery_does_not_halt_on_required_gate_regression(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    campaign_src = tmp_path / "campaign_src"
    campaign_src.mkdir(parents=True, exist_ok=True)
    campaign_pack = campaign_src / "campaign_pack.json"
    campaign_pack.write_text(json.dumps({"schema_version": "dummy"}) + "\n", encoding="utf-8")
    _write_registry(campaign_src / "omega_capability_registry_v2.json")
    worktree = tmp_path / "worktree"
    (worktree / "meta-core").mkdir(parents=True, exist_ok=True)

    def _prepare_worktree(*, repo_root: Path, branch: str, worktree_dir: Path) -> Path:  # noqa: ARG001
        return worktree

    def _fake_run_tick(*, campaign_pack: Path, out_dir: Path, tick_u64: int, prev_state_dir: Path | None = None):  # noqa: ARG001
        return {"safe_halt": tick_u64 >= 2}

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

    gate_status_calls = {"count": 0}

    def _fake_load_gate_statuses(_run_dir: Path) -> dict[str, str]:
        gate_status_calls["count"] += 1
        if gate_status_calls["count"] == 1:
            return {
                "A": "PASS",
                "B": "PASS",
                "C": "PASS",
                "D": "PASS",
                "E": "PASS",
                "F": "PASS",
                "P": "PASS",
                "Q": "PASS",
                "R": "PASS",
            }
        return {
            "A": "FAIL",
            "B": "PASS",
            "C": "PASS",
            "D": "PASS",
            "E": "PASS",
            "F": "PASS",
            "P": "PASS",
            "Q": "PASS",
            "R": "PASS",
        }

    monkeypatch.setattr(runner, "_assert_livewire_repo_clean", lambda _repo_root: None)
    monkeypatch.setattr(runner, "_prepare_livewire_worktree", _prepare_worktree)
    monkeypatch.setattr(runner, "_load_run_tick", lambda _repo_root: _fake_run_tick)
    monkeypatch.setattr(runner, "OmegaVerifierClient", _FakeVerifierClient)
    monkeypatch.setattr(runner, "_run_benchmark_summary", _fake_benchmark)
    monkeypatch.setattr(runner, "_stage_and_commit_livewire_tick", lambda **kwargs: None)
    monkeypatch.setattr(runner, "_run_polymath_scout", lambda **kwargs: True)
    monkeypatch.setattr(runner, "load_gate_statuses", _fake_load_gate_statuses)
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
        "--profile",
        "refinery",
        "--enable_polymath_drive",
        "1",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    runner.main()

    run_dirs = sorted(runs_root.glob("omega_overnight_*"))
    assert run_dirs
    report = json.loads((run_dirs[-1] / "OMEGA_OVERNIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    assert report["termination_reason"] == "SAFE_HALT"
    assert report["termination_reason"] != "GATE_FAIL"
    assert report["termination_reason"] != "GATE_REGRESSION"
    assert report.get("gate_failures")
    assert bool((report.get("auto_rollback") or {}).get("triggered_by_gate_regression_or_failure_b", False)) is False
