from __future__ import annotations

import json
import sys
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_unified_gate_a_fail_is_not_failfast_before_tick_20(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    campaign_src = tmp_path / "campaign_src"
    campaign_src.mkdir(parents=True, exist_ok=True)
    campaign_pack = campaign_src / "campaign_pack.json"
    _write_json(campaign_pack, {"schema_version": "dummy"})
    _write_json(
        campaign_src / "omega_capability_registry_v2.json",
        {
            "schema_version": "omega_capability_registry_v2",
            "capabilities": [{"campaign_id": "rsi_sas_code_v12_0", "enabled": True}],
        },
    )

    worktree = tmp_path / "worktree"
    (worktree / "meta-core").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(runner, "_assert_livewire_repo_clean", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        runner,
        "_prepare_livewire_worktree",
        lambda *, repo_root, branch, worktree_dir: worktree,  # noqa: ARG005
    )
    monkeypatch.setattr(runner, "_sync_campaign_fixtures_into_worktree", lambda **_kwargs: None)
    monkeypatch.setattr(
        runner,
        "_load_run_tick",
        lambda _repo_root: (lambda **_kwargs: {"safe_halt": True}),
    )
    monkeypatch.setattr(runner, "_stage_and_commit_livewire_tick", lambda **_kwargs: None)

    def _fake_replay_manifest(**kwargs):  # noqa: ANN001
        path = kwargs["run_dir"] / "OMEGA_REPLAY_MANIFEST_v1.json"
        _write_json(path, {"schema_version": "OMEGA_REPLAY_MANIFEST_v1"})
        return path

    monkeypatch.setattr(runner, "write_replay_manifest", _fake_replay_manifest)

    class _FakeVerifierClient:
        def __init__(self, *, repo_root: Path):  # noqa: ARG002
            pass

        def verify(self, state_dir: Path, *, mode: str = "full"):  # noqa: ARG002
            return True, "VALID", "VALID"

        def close(self) -> None:
            return None

    monkeypatch.setattr(runner, "OmegaVerifierClient", _FakeVerifierClient)

    def _fake_benchmark(run_dir: Path, _runs_root: Path) -> None:
        _write_json(
            run_dir / "OMEGA_PROMOTION_SUMMARY_v1.json",
            {
                "schema_version": "OMEGA_PROMOTION_SUMMARY_v1",
                "promoted_u64": 1,
                "activation_success_u64": 1,
                "unique_promotions_u64": 1,
                "unique_activations_applied_u64": 1,
                "unique_promoted_families_u64": 1,
                "promotion_skip_reason_counts": {},
                "activation_failure_reason_counts": [],
            },
        )
        _write_json(
            run_dir / "OMEGA_BENCHMARK_GATES_v1.json",
            {
                "schema_version": "OMEGA_BENCHMARK_GATES_v1",
                "gates": {
                    "A": {"status": "FAIL", "details": {}},
                    "B": {"status": "PASS", "details": {}},
                    "C": {"status": "PASS", "details": {}},
                    "D": {"status": "PASS", "details": {}},
                    "E": {"status": "PASS", "details": {}},
                    "F": {"status": "PASS", "details": {}},
                },
            },
        )
        (run_dir / "OMEGA_BENCHMARK_SUMMARY_v1.md").write_text(
            "\n".join(
                [
                    "# Benchmark",
                    "- Gate A (x): **FAIL**",
                    "- Gate B (x): **PASS**",
                    "- Gate C (x): **PASS**",
                    "- Gate D (x): **PASS**",
                    "- Gate E (x): **PASS**",
                    "- Gate F (x): **PASS**",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(runner, "_run_benchmark_summary", _fake_benchmark)

    argv = [
        "omega_overnight_runner_v1.py",
        "--hours",
        "0.001",
        "--series_prefix",
        "gate_a_warmup",
        "--meta_core_mode",
        "sandbox",
        "--runs_root",
        str(runs_root),
        "--campaign_pack",
        str(campaign_pack),
        "--profile",
        "unified",
        "--polymath_scout_every_ticks",
        "1",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    runner.main()

    report = json.loads((runs_root / "gate_a_warmup" / "OMEGA_OVERNIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    assert report["termination_reason"] != "GATE_FAIL"
