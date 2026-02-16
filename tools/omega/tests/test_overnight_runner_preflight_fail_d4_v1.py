from __future__ import annotations

import json
import sys
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _latest_run_dir(runs_root: Path) -> Path:
    runs = sorted(runs_root.glob("omega_overnight_*"))
    assert runs
    return runs[-1]


def test_preflight_fail_when_capability_registry_missing_d4_v1(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    campaign_root = tmp_path / "campaign"
    campaign_pack = campaign_root / "rsi_omega_daemon_pack_v1.json"
    _write_json(campaign_pack, {"schema_version": "rsi_omega_daemon_pack_v1"})

    worktree = tmp_path / "worktree"
    (worktree / "meta-core").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(runner, "_assert_livewire_repo_clean", lambda _repo_root: None)
    monkeypatch.setattr(runner, "_prepare_livewire_worktree", lambda **kwargs: worktree)
    monkeypatch.setattr(runner, "_sync_campaign_fixtures_into_worktree", lambda **kwargs: None)

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

    run_dir = _latest_run_dir(runs_root)
    report = json.loads((run_dir / "OMEGA_OVERNIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    assert report["termination_reason"] == "PREFLIGHT_FAIL"
    assert bool(report["safe_halt"]) is False

    preflight = json.loads((run_dir / "OMEGA_PREFLIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    assert bool(preflight["ok_b"]) is False
    assert preflight["fail_reason"] == "capability_registry_json_object"

    assert (run_dir / "OMEGA_DIAGNOSTIC_PACKET_v1.json").exists()
    assert (run_dir / "OMEGA_REPLAY_MANIFEST_v1.json").exists()


def test_preflight_fail_when_polymath_void_path_is_noncanonical_d4_v1(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    campaign_root = tmp_path / "campaign"
    campaign_pack = campaign_root / "rsi_omega_daemon_pack_v1.json"
    _write_json(campaign_pack, {"schema_version": "rsi_omega_daemon_pack_v1"})

    scout_pack = tmp_path / "rsi_polymath_scout_pack_v1.json"
    _write_json(
        scout_pack,
        {
            "schema_version": "rsi_polymath_scout_pack_v1",
            "void_report_path_rel": "polymath/registry/noncanonical_void_report_v1.jsonl",
        },
    )
    _write_json(
        campaign_root / "omega_capability_registry_v2.json",
        {
            "schema_version": "omega_capability_registry_v2",
            "capabilities": [
                {
                    "campaign_id": "rsi_polymath_scout_v1",
                    "enabled": True,
                    "campaign_pack_rel": scout_pack.as_posix(),
                }
            ],
        },
    )

    worktree = tmp_path / "worktree"
    (worktree / "meta-core").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(runner, "_assert_livewire_repo_clean", lambda _repo_root: None)
    monkeypatch.setattr(runner, "_prepare_livewire_worktree", lambda **kwargs: worktree)
    monkeypatch.setattr(runner, "_sync_campaign_fixtures_into_worktree", lambda **kwargs: None)

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

    run_dir = _latest_run_dir(runs_root)
    report = json.loads((run_dir / "OMEGA_OVERNIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    assert report["termination_reason"] == "PREFLIGHT_FAIL"
    assert bool(report["safe_halt"]) is False

    preflight = json.loads((run_dir / "OMEGA_PREFLIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    assert bool(preflight["ok_b"]) is False
    assert preflight["fail_reason"] == "polymath_void_report_path_canonical"
