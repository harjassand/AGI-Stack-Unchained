from __future__ import annotations

import shutil

from cdel.v18_0 import verify_rsi_omega_daemon_v1 as verifier_module
from cdel.v18_0.omega_verifier_worker_v1 import VerifierWorker

from .utils import load_json, repo_root, run_tick_with_pack, write_json


def _prepare_no_dispatch_pack(tmp_path):
    src = repo_root() / "campaigns" / "rsi_omega_daemon_v18_0"
    dst = tmp_path / "campaign_pack"
    shutil.copytree(src, dst)

    registry_path = dst / "omega_capability_registry_v2.json"
    registry = load_json(registry_path)
    rows = registry.get("capabilities")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                row["enabled"] = False
    write_json(registry_path, registry)

    goal_path = dst / "goals" / "omega_goal_queue_v1.json"
    write_json(goal_path, {"schema_version": "omega_goal_queue_v1", "goals": []})
    return dst / "rsi_omega_daemon_pack_v1.json"


def test_verifier_worker_cache_skips_recompute(tmp_path, monkeypatch) -> None:
    campaign_pack = _prepare_no_dispatch_pack(tmp_path)
    _, state_dir = run_tick_with_pack(
        tmp_path=tmp_path / "run",
        campaign_pack=campaign_pack,
        tick_u64=1,
    )

    calls = {"observe": 0, "diagnose": 0, "decide": 0}

    original_observe = verifier_module._recompute_observation_from_sources
    original_diagnose = verifier_module.diagnose
    original_decide = verifier_module.decide

    def _observe_wrapper(
        *,
        root,
        runs_roots=None,
        observation_payload,
        policy_hash,
        registry_hash,
        objectives_hash,
        prev_observation=None,
    ):
        calls["observe"] += 1
        return original_observe(
            root=root,
            runs_roots=runs_roots,
            observation_payload=observation_payload,
            policy_hash=policy_hash,
            registry_hash=registry_hash,
            objectives_hash=objectives_hash,
            prev_observation=prev_observation,
        )

    def _diagnose_wrapper(*, tick_u64, observation_report, objectives):
        calls["diagnose"] += 1
        return original_diagnose(
            tick_u64=tick_u64,
            observation_report=observation_report,
            objectives=objectives,
        )

    def _decide_wrapper(*args, **kwargs):
        calls["decide"] += 1
        return original_decide(*args, **kwargs)

    monkeypatch.setattr(verifier_module, "_recompute_observation_from_sources", _observe_wrapper)
    monkeypatch.setattr(verifier_module, "diagnose", _diagnose_wrapper)
    monkeypatch.setattr(verifier_module, "decide", _decide_wrapper)

    worker = VerifierWorker()

    first = worker.handle_request(
        {
            "op": "VERIFY",
            "state_dir": str(state_dir),
            "mode": "full",
        }
    )
    assert first["ok"] is True
    assert first["verdict"] == "VALID"
    assert calls["observe"] >= 1
    assert calls["diagnose"] >= 1
    assert calls["decide"] >= 1

    calls_after_first = dict(calls)
    second = worker.handle_request(
        {
            "op": "VERIFY",
            "state_dir": str(state_dir),
            "mode": "full",
        }
    )
    assert second["ok"] is True
    assert second["verdict"] == "VALID"
    assert calls == calls_after_first
