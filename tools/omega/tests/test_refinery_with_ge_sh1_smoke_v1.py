from __future__ import annotations

import json
import sys
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def _write_registry(path: Path) -> None:
    payload = {
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
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_refinery_with_ge_sh1_smoke_v1(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    campaign_src = tmp_path / "campaign_src"
    campaign_src.mkdir(parents=True, exist_ok=True)
    campaign_pack = campaign_src / "rsi_omega_daemon_pack_v1.json"
    campaign_pack.write_text(
        json.dumps(
            {
                "schema_version": "rsi_omega_daemon_pack_v1",
                "omega_capability_registry_rel": "omega_capability_registry_v2.json",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    _write_registry(campaign_src / "omega_capability_registry_v2.json")

    worktree = tmp_path / "worktree"
    (worktree / "meta-core").mkdir(parents=True, exist_ok=True)
    (worktree / "campaigns" / "rsi_ge_symbiotic_optimizer_sh1_v0_1").mkdir(parents=True, exist_ok=True)
    (worktree / "campaigns" / "rsi_ge_symbiotic_optimizer_sh1_v0_1" / "rsi_ge_symbiotic_optimizer_sh1_pack_v0_1.json").write_text(
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

    sandbox_meta_core = tmp_path / "meta_core_sandbox"
    sandbox_meta_core.mkdir(parents=True, exist_ok=True)

    def _prepare_worktree(*, repo_root: Path, branch: str, worktree_dir: Path) -> Path:  # noqa: ARG001
        return worktree

    def _fake_run_tick(*, campaign_pack: Path, out_dir: Path, tick_u64: int, prev_state_dir: Path | None = None):  # noqa: ARG001
        dispatch_dir = out_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state" / "dispatch" / "a0"
        dispatch_dir.mkdir(parents=True, exist_ok=True)
        (dispatch_dir / ("sha256_" + ("9" * 64) + ".omega_dispatch_receipt_v1.json")).write_text(
            json.dumps(
                {
                    "schema_version": "omega_dispatch_receipt_v1",
                    "tick_u64": int(tick_u64),
                    "campaign_id": "rsi_ge_symbiotic_optimizer_sh1_v0_1",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        receipt_dir = out_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state" / "dispatch" / "a0" / "verifier"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipt_dir / "ccap_receipt_v1.json"
        receipt_path.write_text(
            json.dumps(
                {
                    "schema_version": "ccap_receipt_v1",
                    "ccap_id": "sha256:" + ("1" * 64),
                    "base_tree_id": "sha256:" + ("2" * 64),
                    "applied_tree_id": "sha256:" + ("3" * 64),
                    "realized_out_id": "sha256:" + ("4" * 64),
                    "ek_id": "sha256:" + ("5" * 64),
                    "op_pool_id": "sha256:" + ("6" * 64),
                    "auth_hash": "sha256:" + ("7" * 64),
                    "determinism_check": "PASS",
                    "eval_status": "PASS",
                    "decision": "PROMOTE",
                    "cost_vector": {
                        "cpu_ms": 0,
                        "wall_ms": 0,
                        "mem_mb": 0,
                        "disk_mb": 0,
                        "fds": 0,
                        "procs": 0,
                        "threads": 0,
                    },
                    "logs_hash": "sha256:" + ("8" * 64),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        return {"safe_halt": False}

    class _FakeVerifierClient:
        def __init__(self, *, repo_root: Path):  # noqa: ARG002
            pass

        def verify(self, state_dir: Path, *, mode: str = "full"):  # noqa: ARG002
            return True, "VALID", "VALID"

        def close(self) -> None:
            return None

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
                    "promoted_u64": 1,
                    "activation_success_u64": 1,
                    "unique_promotions_u64": 1,
                    "unique_activations_applied_u64": 1,
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
                    "non_noop_ticks_per_min": 1.0,
                    "promotion_ticks_per_min": 1.0,
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

    def _fake_ge_audit(*, runs_root: Path, run_dir: Path, ge_config_path: Path):  # noqa: ANN003
        del runs_root, ge_config_path
        out_json = run_dir / "GE_AUDIT_REPORT_v1.json"
        out_md = run_dir / "GE_AUDIT_REPORT.md"
        out_json.write_text(
            json.dumps(
                {
                    "schema_version": "ge_audit_report_v1",
                    "kpi": {"promote_u64": 1, "total_wall_ms_u64": 100, "yield_promotions_per_wall_ms_q32": 42949672},
                    "novelty": {"novelty_coverage_q32": 2147483648, "total_u64": 1},
                    "falsification_flags": [],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        out_md.write_text("# GE Audit\n", encoding="utf-8")
        return out_json, out_md

    monotonic_state = {"value": 0.0}

    def _fake_monotonic() -> float:
        monotonic_state["value"] += 120.0
        return monotonic_state["value"]

    monkeypatch.setattr(runner, "_assert_livewire_repo_clean", lambda _repo_root: None)
    monkeypatch.setattr(runner, "_prepare_livewire_worktree", _prepare_worktree)
    monkeypatch.setattr(runner, "_sync_campaign_fixtures_into_worktree", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "_load_run_tick", lambda _repo_root: _fake_run_tick)
    monkeypatch.setattr(runner, "OmegaVerifierClient", _FakeVerifierClient)
    monkeypatch.setattr(runner, "_run_benchmark_summary", _fake_benchmark)
    monkeypatch.setattr(runner, "_stage_and_commit_livewire_tick", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "load_gate_statuses", lambda _run_dir: {"A": "PASS", "B": "PASS", "C": "PASS", "F": "PASS", "P": "PASS", "Q": "PASS"})
    monkeypatch.setattr(runner, "create_meta_core_sandbox", lambda runs_root, series: sandbox_meta_core)  # noqa: ARG005
    monkeypatch.setattr(runner, "_run_ge_audit_report", _fake_ge_audit)
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
        "--ge_max_ccaps",
        "3",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    runner.main()

    run_dirs = sorted(runs_root.glob("omega_overnight_*"))
    assert run_dirs
    run_dir = run_dirs[-1]

    report = json.loads((run_dir / "OMEGA_OVERNIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    assert report["termination_reason"] == "DEADLINE_EXPIRED"
    assert bool(report["safe_halt"]) is False

    ge_sh1 = report.get("ge_sh1") or {}
    assert int(ge_sh1.get("ge_dispatch_u64", 0)) >= 1
    assert int(ge_sh1.get("ccap_receipts_u64", 0)) >= 1
    ge_json = Path(str(ge_sh1.get("audit_report_json", "")))
    ge_md = Path(str(ge_sh1.get("audit_report_md", "")))
    assert ge_json.exists() and ge_json.is_file()
    assert ge_md.exists() and ge_md.is_file()
    ge_audit_payload = json.loads(ge_json.read_text(encoding="utf-8"))
    novelty_obj = ge_audit_payload.get("novelty") if isinstance(ge_audit_payload, dict) else {}
    assert int((novelty_obj or {}).get("total_u64", 0)) > 0

    receipt_paths = sorted(run_dir.glob("**/*ccap_receipt_v1.json"))
    assert receipt_paths
