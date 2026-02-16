from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def _write_registry(path: Path, *, polymath_enabled: bool) -> None:
    payload = {
        "schema_version": "omega_capability_registry_v2",
        "capabilities": [
            {"campaign_id": "rsi_polymath_scout_v1", "enabled": bool(polymath_enabled)},
            {"campaign_id": "rsi_polymath_bootstrap_domain_v1", "enabled": bool(polymath_enabled)},
            {"campaign_id": "rsi_polymath_conquer_domain_v1", "enabled": bool(polymath_enabled)},
            {"campaign_id": "rsi_sas_code_v12_0", "enabled": True},
        ],
    }
    _write_json(path, payload)


def _fake_subprocess_run(cmd, **kwargs):  # noqa: ANN001
    _ = kwargs
    if cmd[:3] == ["git", "rev-parse", "HEAD"]:
        return subprocess.CompletedProcess(cmd, 0, stdout="abc123\n", stderr="")
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


class _FakeVerifierClient:
    def __init__(self, *, repo_root: Path):  # noqa: ARG002
        pass

    def verify(self, state_dir: Path, *, mode: str = "full"):  # noqa: ARG002
        return True, "VALID", "VALID"

    def close(self) -> None:
        return None


def _write_fake_benchmark_artifacts(*, run_dir: Path, p_status: str, q_status: str) -> None:
    gates_payload = {
        "schema_version": "OMEGA_BENCHMARK_GATES_v1",
        "gates": {
            "A": {"status": "PASS", "details": {}},
            "B": {"status": "PASS", "details": {}},
            "C": {"status": "PASS", "details": {}},
            "D": {"status": "PASS", "details": {}},
            "E": {"status": "PASS", "details": {}},
            "F": {"status": "PASS", "details": {}},
            "P": {
                "status": str(p_status),
                "details": {
                    "scout_dispatch_u64": 2,
                    "last_scout_tick_u64": 2,
                    "void_hash_first": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
                    "void_hash_last": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
                    "void_hash_changed_b": True,
                },
            },
            "Q": {
                "status": str(q_status),
                "details": {
                    "domains_bootstrapped_first_u64": 0,
                    "domains_bootstrapped_last_u64": 0,
                    "domains_bootstrapped_delta_u64": 0,
                    "conquer_improved_u64": 0,
                },
            },
            "R": {"status": "PASS", "details": {}},
        },
    }
    _write_json(run_dir / "OMEGA_BENCHMARK_GATES_v1.json", gates_payload)
    _write_json(
        run_dir / "OMEGA_GATE_PROOF_v1.json",
        {
            "schema_version": "OMEGA_GATE_PROOF_v1",
            "gates": {
                "P": {"status": str(p_status), "inputs": {}, "intermediates": {}},
                "Q": {"status": str(q_status), "inputs": {}, "intermediates": {}},
            },
        },
    )
    _write_json(
        run_dir / "OMEGA_PROMOTION_SUMMARY_v1.json",
        {
            "schema_version": "OMEGA_PROMOTION_SUMMARY_v1",
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
                f"- Gate P (x): **{str(p_status)}**",
                f"- Gate Q (x): **{str(q_status)}**",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _patch_common(
    *,
    monkeypatch,
    campaign_pack: Path,
    worktree: Path,
    run_tick_fn,
    benchmark_writer_fn,
) -> None:
    monkeypatch.setattr(runner, "_assert_livewire_repo_clean", lambda _repo_root: None)
    monkeypatch.setattr(runner, "_prepare_livewire_worktree", lambda **_kwargs: worktree)
    monkeypatch.setattr(runner, "_sync_campaign_fixtures_into_worktree", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "_resolve_campaign_pack_for_repo", lambda **_kwargs: campaign_pack)
    monkeypatch.setattr(runner, "_prepare_campaign_pack_overlay", lambda **_kwargs: campaign_pack)
    monkeypatch.setattr(runner, "_load_run_tick", lambda _repo_root: run_tick_fn)
    monkeypatch.setattr(runner, "OmegaVerifierClient", _FakeVerifierClient)
    monkeypatch.setattr(runner, "_run_benchmark_summary", benchmark_writer_fn)
    monkeypatch.setattr(runner, "_stage_and_commit_livewire_tick", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "_write_skill_manifest_artifacts", lambda **kwargs: (Path(kwargs["run_dir"]) / "skill.json", Path(kwargs["run_dir"]) / "skill_wt.json"))
    monkeypatch.setattr(runner.subprocess, "run", _fake_subprocess_run)


def test_polymath_stall_p_failfast_by_tick_10(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    campaign_src = tmp_path / "campaign_src_p"
    campaign_src.mkdir(parents=True, exist_ok=True)
    campaign_pack = campaign_src / "campaign_pack.json"
    _write_json(campaign_pack, {"schema_version": "dummy"})
    _write_registry(campaign_src / "omega_capability_registry_v2.json", polymath_enabled=True)

    worktree = tmp_path / "worktree_p"
    (worktree / "meta-core").mkdir(parents=True, exist_ok=True)

    def _fake_run_tick(*, campaign_pack: Path, out_dir: Path, tick_u64: int, prev_state_dir: Path | None = None):  # noqa: ARG001
        return {"safe_halt": False}

    def _fake_benchmark(run_dir: Path, runs_root: Path) -> None:  # noqa: ARG001
        _write_fake_benchmark_artifacts(run_dir=run_dir, p_status="FAIL", q_status="FAIL")

    _patch_common(
        monkeypatch=monkeypatch,
        campaign_pack=campaign_pack,
        worktree=worktree,
        run_tick_fn=_fake_run_tick,
        benchmark_writer_fn=_fake_benchmark,
    )

    argv = [
        "omega_overnight_runner_v1.py",
        "--hours",
        "0.01",
        "--series_prefix",
        "omega_d3_stall_p",
        "--meta_core_mode",
        "production",
        "--runs_root",
        str(runs_root),
        "--campaign_pack",
        str(campaign_pack),
        "--profile",
        "unified",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    runner.main()

    run_dir = runs_root / "omega_d3_stall_p"
    report = json.loads((run_dir / "OMEGA_OVERNIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    assert report["termination_reason"] == "POLYMATH_STALL_P"
    assert int(report["ticks_completed_u64"]) <= 10

    diagnostic = json.loads((run_dir / "OMEGA_DIAGNOSTIC_PACKET_v1.json").read_text(encoding="utf-8"))
    failures = diagnostic.get("gate_failures") if isinstance(diagnostic, dict) else []
    assert isinstance(failures, list)
    gates = {str(row.get("gate", "")) for row in failures if isinstance(row, dict)}
    assert "P" in gates
    p_rows = [row for row in failures if isinstance(row, dict) and str(row.get("gate", "")) == "P"]
    assert p_rows
    assert str(p_rows[0].get("reason", "")) in {"SCOUT_NOT_DISPATCHED", "VOID_REPORT_EMPTY", "VOID_HASH_NOT_CHANGED"}


def test_polymath_stall_q_failfast_by_tick_30(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    campaign_src = tmp_path / "campaign_src_q"
    campaign_src.mkdir(parents=True, exist_ok=True)
    campaign_pack = campaign_src / "campaign_pack.json"
    _write_json(campaign_pack, {"schema_version": "dummy"})
    _write_registry(campaign_src / "omega_capability_registry_v2.json", polymath_enabled=True)

    worktree = tmp_path / "worktree_q"
    (worktree / "meta-core").mkdir(parents=True, exist_ok=True)

    def _fake_run_tick(*, campaign_pack: Path, out_dir: Path, tick_u64: int, prev_state_dir: Path | None = None):  # noqa: ARG001
        state_dir = out_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state"
        _write_json(
            state_dir / "observations" / f"sha256_obs_{int(tick_u64):06d}.omega_observation_report_v1.json",
            {
                "schema_version": "omega_observation_report_v1",
                "tick_u64": int(tick_u64),
                "metrics": {
                    "top_void_score_q32": {"q": 1},
                    "domains_ready_for_conquer_u64": 0,
                    "domains_bootstrapped_u64": 0,
                    "domain_coverage_ratio": {"q": 0},
                },
                "sources": [],
            },
        )
        if int(tick_u64) in (1, 2):
            action_id = f"scout_{int(tick_u64):02d}"
            subrun_rel = f"subruns/{action_id}_rsi_polymath_scout_v1"
            _write_json(
                state_dir / "dispatch" / action_id / f"sha256_{action_id}.omega_dispatch_receipt_v1.json",
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
                        "topic_id": f"topic_{int(tick_u64)}",
                        "topic_name": f"topic_{int(tick_u64)}",
                        "candidate_domain_id": f"demo_{int(tick_u64)}",
                        "trend_score_q32": {"q": 1},
                        "coverage_score_q32": {"q": 0},
                        "void_score_q32": {"q": 1},
                        "source_evidence": [],
                    }
                ],
            )
        _write_jsonl(
            worktree / "polymath" / "registry" / "polymath_void_report_v1.jsonl",
            [
                {
                    "schema_version": "polymath_void_report_v1",
                    "topic_id": "offline",
                    "topic_name": "offline",
                    "candidate_domain_id": "offline::1",
                    "trend_score_q32": {"q": 1},
                    "coverage_score_q32": {"q": 0},
                    "void_score_q32": {"q": 1},
                    "source_evidence": [],
                }
            ],
        )
        return {"safe_halt": False}

    def _fake_benchmark(run_dir: Path, runs_root: Path) -> None:  # noqa: ARG001
        _write_fake_benchmark_artifacts(run_dir=run_dir, p_status="PASS", q_status="FAIL")

    _patch_common(
        monkeypatch=monkeypatch,
        campaign_pack=campaign_pack,
        worktree=worktree,
        run_tick_fn=_fake_run_tick,
        benchmark_writer_fn=_fake_benchmark,
    )

    argv = [
        "omega_overnight_runner_v1.py",
        "--hours",
        "0.01",
        "--series_prefix",
        "omega_d3_stall_q",
        "--meta_core_mode",
        "production",
        "--runs_root",
        str(runs_root),
        "--campaign_pack",
        str(campaign_pack),
        "--profile",
        "unified",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    runner.main()

    run_dir = runs_root / "omega_d3_stall_q"
    report = json.loads((run_dir / "OMEGA_OVERNIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    assert report["termination_reason"] == "POLYMATH_STALL_Q"
    assert int(report["ticks_completed_u64"]) <= 30

    diagnostic = json.loads((run_dir / "OMEGA_DIAGNOSTIC_PACKET_v1.json").read_text(encoding="utf-8"))
    failures = diagnostic.get("gate_failures") if isinstance(diagnostic, dict) else []
    assert isinstance(failures, list)
    q_rows = [row for row in failures if isinstance(row, dict) and str(row.get("gate", "")) == "Q"]
    assert q_rows
    evidence = q_rows[0].get("evidence")
    assert isinstance(evidence, dict)
    assert int(evidence.get("domains_ready_for_conquer_u64", 0)) == 0
    assert int(evidence.get("domains_bootstrapped_delta_u64", 0)) == 0


def test_unified_gate_applicability_omits_pq_when_polymath_disabled(tmp_path: Path) -> None:
    campaign_src = tmp_path / "campaign_src_disabled"
    campaign_src.mkdir(parents=True, exist_ok=True)
    campaign_pack = campaign_src / "campaign_pack.json"
    _write_json(campaign_pack, {"schema_version": "dummy"})
    _write_registry(campaign_src / "omega_capability_registry_v2.json", polymath_enabled=False)

    enablement = runner._overlay_polymath_enablement(campaign_pack)
    assert bool(enablement["polymath_enabled"]) is False
    required = runner._required_pass_gates("unified", polymath_enabled=bool(enablement["polymath_enabled"]))
    assert required == ("A", "B", "C", "D", "E", "F")
