from __future__ import annotations

import json
import sys
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_registry(path: Path) -> None:
    _write_json(
        path,
        {
            "schema_version": "omega_capability_registry_v2",
            "capabilities": [
                {
                    "campaign_id": "rsi_sas_code_v12_0",
                    "enabled": True,
                    "campaign_pack_rel": "campaigns/rsi_sas_code_v12_0/rsi_sas_code_pack_v1.json",
                },
                {
                    "campaign_id": "rsi_sas_metasearch_v16_1",
                    "enabled": True,
                    "campaign_pack_rel": "campaigns/rsi_sas_metasearch_v16_1/rsi_sas_metasearch_pack_v16_1.json",
                },
                {
                    "campaign_id": "rsi_ge_symbiotic_optimizer_sh1_v0_1",
                    "enabled": False,
                    "enable_ccap": 1,
                    "campaign_pack_rel": "campaigns/rsi_ge_symbiotic_optimizer_sh1_v0_1/rsi_ge_symbiotic_optimizer_sh1_pack_v0_1.json",
                },
            ],
        },
    )


def _write_benchmark_artifacts(run_dir: Path) -> None:
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
    _write_json(
        run_dir / "OMEGA_PROMOTION_SUMMARY_v1.json",
        {
            "promoted_u64": 0,
            "activation_success_u64": 0,
            "unique_promotions_u64": 0,
            "unique_activations_applied_u64": 0,
            "activation_failure_reason_counts": [],
            "top_touched_paths": [],
        },
    )
    _write_json(
        run_dir / "OMEGA_TIMINGS_AGG_v1.json",
        {
            "schema_version": "OMEGA_TIMINGS_AGG_v1",
            "non_noop_ticks_per_min": 0.0,
            "promotion_ticks_per_min": 0.0,
        },
    )
    _write_json(
        run_dir / "OMEGA_RUN_SCORECARD_v1.json",
        {
            "schema_version": "omega_run_scorecard_v1",
            "median_stps_non_noop_q32": 0,
        },
    )


def _run_with_ge_counts(tmp_path: Path, monkeypatch, *, ge_dispatch_u64: int, ccap_receipts_u64: int) -> dict:
    runs_root = tmp_path / "runs"
    campaign_src = tmp_path / "campaign_src"
    campaign_src.mkdir(parents=True, exist_ok=True)
    campaign_pack = campaign_src / "rsi_omega_daemon_pack_v1.json"
    _write_json(
        campaign_pack,
        {
            "schema_version": "rsi_omega_daemon_pack_v1",
            "omega_capability_registry_rel": "omega_capability_registry_v2.json",
        },
    )
    _write_registry(campaign_src / "omega_capability_registry_v2.json")

    fake_repo = tmp_path / "repo"
    (fake_repo / "meta-core").mkdir(parents=True, exist_ok=True)
    ge_src = fake_repo / "campaigns" / "rsi_ge_symbiotic_optimizer_sh1_v0_1"
    ge_src.mkdir(parents=True, exist_ok=True)
    _write_json(
        ge_src / "rsi_ge_symbiotic_optimizer_sh1_pack_v0_1.json",
        {
            "schema_version": "rsi_ge_symbiotic_optimizer_sh1_pack_v0_1",
            "max_ccaps": 1,
            "model_id": "ge-v0_3",
        },
    )

    sandbox_meta_core = tmp_path / "meta_core_sandbox"
    sandbox_meta_core.mkdir(parents=True, exist_ok=True)

    def _prepare_worktree(*, repo_root: Path, branch: str, worktree_dir: Path) -> Path:  # noqa: ARG001
        return fake_repo

    def _fake_run_tick(*, campaign_pack: Path, out_dir: Path, tick_u64: int, prev_state_dir: Path | None = None):  # noqa: ARG001
        return {"safe_halt": False}

    class _FakeVerifierClient:
        def __init__(self, *, repo_root: Path):  # noqa: ARG002
            pass

        def verify(self, state_dir: Path, *, mode: str = "full"):  # noqa: ARG002
            return True, "VALID", "VALID"

        def close(self) -> None:
            return None

    monotonic_state = {"value": 0.0}

    def _fake_monotonic() -> float:
        monotonic_state["value"] += 120.0
        return monotonic_state["value"]

    monkeypatch.setattr(runner, "_REPO_ROOT", fake_repo)
    monkeypatch.setattr(runner, "_ORIGINAL_REPO_ROOT", fake_repo)
    monkeypatch.setattr(runner, "_assert_livewire_repo_clean", lambda _repo_root: None)
    monkeypatch.setattr(runner, "_prepare_livewire_worktree", _prepare_worktree)
    monkeypatch.setattr(runner, "_sync_campaign_fixtures_into_worktree", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "_load_run_tick", lambda _repo_root: _fake_run_tick)
    monkeypatch.setattr(runner, "OmegaVerifierClient", _FakeVerifierClient)
    monkeypatch.setattr(runner, "_run_benchmark_summary", lambda run_dir, runs_root: _write_benchmark_artifacts(run_dir))
    monkeypatch.setattr(runner, "_stage_and_commit_livewire_tick", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "load_gate_statuses", lambda _run_dir: {"A": "PASS", "B": "PASS", "C": "PASS", "F": "PASS", "P": "PASS", "Q": "PASS"})
    monkeypatch.setattr(runner, "create_meta_core_sandbox", lambda runs_root, series: sandbox_meta_core)  # noqa: ARG005
    monkeypatch.setattr(
        runner,
        "_count_ge_sh1_artifacts",
        lambda _run_dir: {"ge_dispatch_u64": ge_dispatch_u64, "ccap_receipts_u64": ccap_receipts_u64},
    )
    monkeypatch.setattr(runner.time, "monotonic", _fake_monotonic)

    argv = [
        "omega_overnight_runner_v1.py",
        "--hours",
        "0.05",
        "--meta_core_mode",
        "sandbox",
        "--runs_root",
        str(runs_root),
        "--campaign_pack",
        str(campaign_pack),
        "--profile",
        "refinery",
        "--enable_ge_sh1_optimizer",
        "1",
        "--ge_audit",
        "0",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    runner.main()

    run_dirs = sorted(runs_root.glob("omega_overnight_*"))
    assert run_dirs
    report = json.loads((run_dirs[-1] / "OMEGA_OVERNIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    return report


def test_refinery_sets_ge_not_dispatched_fail_closed(tmp_path: Path, monkeypatch) -> None:
    report = _run_with_ge_counts(tmp_path, monkeypatch, ge_dispatch_u64=0, ccap_receipts_u64=0)
    assert report["termination_reason"] == "GE_NOT_DISPATCHED"
    assert bool(report["safe_halt"]) is True


def test_refinery_sets_ge_no_ccap_receipts_fail_closed(tmp_path: Path, monkeypatch) -> None:
    report = _run_with_ge_counts(tmp_path, monkeypatch, ge_dispatch_u64=1, ccap_receipts_u64=0)
    assert report["termination_reason"] == "GE_NO_CCAP_RECEIPTS"
    assert bool(report["safe_halt"]) is True
