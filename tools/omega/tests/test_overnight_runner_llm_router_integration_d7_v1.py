from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


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
    (run_dir / "OMEGA_PROMOTION_SUMMARY_v1.json").write_text(
        json.dumps(
            {
                "promoted_u64": 2,
                "activation_success_u64": 1,
                "unique_promotions_u64": 2,
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


def test_overnight_runner_llm_router_integration(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    campaign_src = tmp_path / "campaign_src"
    campaign_src.mkdir(parents=True, exist_ok=True)
    campaign_pack = campaign_src / "campaign_pack.json"
    campaign_pack.write_text(json.dumps({"schema_version": "dummy"}) + "\n", encoding="utf-8")

    worktree = tmp_path / "worktree"
    (worktree / "meta-core").mkdir(parents=True, exist_ok=True)

    def _prepare_worktree(*, repo_root: Path, branch: str, worktree_dir: Path) -> Path:  # noqa: ARG001
        return worktree

    def _fake_run_tick(*, campaign_pack: Path, out_dir: Path, tick_u64: int, prev_state_dir: Path | None = None):  # noqa: ARG001
        return {"safe_halt": int(tick_u64) >= 10}

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
        _write_benchmark_artifacts(run_dir)

    router_ticks: list[int] = []

    def _fake_llm_router_run_failsoft(*, run_dir: Path, tick_u64: int, store_root: Path | None = None) -> dict[str, object]:
        router_ticks.append(int(tick_u64))
        assert store_root is not None
        assert store_root.resolve() == (run_dir / "polymath" / "store").resolve()

        plan_path = run_dir / "OMEGA_LLM_ROUTER_PLAN_v1.json"
        trace_path = run_dir / "OMEGA_LLM_TOOL_TRACE_v1.jsonl"
        plan_payload = {
            "schema_version": "omega_llm_router_plan_v1",
            "created_at_utc": "",
            "created_from_tick_u64": int(tick_u64),
            "web_queries": [
                {
                    "provider": "wikipedia",
                    "query": "OpenAI",
                    "top_k": 2,
                    "sealed": {
                        "url": "https://en.wikipedia.org/w/api.php?action=query&format=json&list=search&srlimit=2&srsearch=OpenAI",
                        "sha256": "sha256:" + "1" * 64,
                        "receipt_path": str(run_dir / "polymath" / "store" / "receipts" / ("1" * 64 + ".json")),
                        "bytes_path": str(run_dir / "polymath" / "store" / "blobs" / "sha256" / ("1" * 64)),
                        "cached_b": False,
                    },
                    "summary": {"provider": "wikipedia", "query": "OpenAI", "results": [], "top_k_u64": 2},
                }
            ],
            "goal_injections": [
                {
                    "capability_id": "RSI_SAS_CODE",
                    "goal_id": "goal_auto_llm_code_0001",
                    "priority_u8": 3,
                    "reason": "test",
                },
                {
                    "capability_id": "RSI_SAS_METASEARCH",
                    "goal_id": "goal_auto_llm_meta_0001",
                    "priority_u8": 9,
                    "reason": "test",
                },
            ],
        }
        plan_path.write_text(json.dumps(plan_payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        with trace_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "schema_version": "omega_llm_tool_trace_row_v1",
                        "created_at_utc": "",
                        "tick_u64": int(tick_u64),
                        "prompt_sha256": "sha256:" + "2" * 64,
                        "response_sha256": "sha256:" + "3" * 64,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )

        store_root_path = run_dir / "polymath" / "store"
        (store_root_path / "indexes").mkdir(parents=True, exist_ok=True)
        (store_root_path / "blobs" / "sha256").mkdir(parents=True, exist_ok=True)
        (store_root_path / "receipts").mkdir(parents=True, exist_ok=True)
        (store_root_path / "indexes" / "urls_to_sha256.jsonl").write_text(
            json.dumps(
                {
                    "schema_version": "polymath_url_index_v1",
                    "url": "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=OpenAI&format=json&srlimit=2",
                    "sha256": "sha256:" + "1" * 64,
                    "request_hash": "sha256:" + "4" * 64,
                    "receipt_sha256": "sha256:" + "5" * 64,
                    "fetched_at_utc": "",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        return {
            "status": "OK",
            "goal_injections": plan_payload["goal_injections"],
            "web_queries": plan_payload["web_queries"],
            "plan_path": plan_path.as_posix(),
            "trace_path": trace_path.as_posix(),
            "prompt_sha256": "sha256:" + "2" * 64,
            "response_sha256": "sha256:" + "3" * 64,
            "backend": "mock",
            "provider": "mock",
            "model": "mock",
        }

    monkeypatch.setenv("ORCH_LLM_BACKEND", "mock")
    monkeypatch.setattr(runner, "_assert_livewire_repo_clean", lambda _repo_root: None)
    monkeypatch.setattr(runner, "_prepare_livewire_worktree", _prepare_worktree)
    monkeypatch.setattr(runner, "_sync_campaign_fixtures_into_worktree", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "_load_run_tick", lambda _repo_root: _fake_run_tick)
    monkeypatch.setattr(runner, "OmegaVerifierClient", _FakeVerifierClient)
    monkeypatch.setattr(runner, "_run_benchmark_summary", _fake_benchmark)
    monkeypatch.setattr(runner, "_stage_and_commit_livewire_tick", lambda **_kwargs: None)
    monkeypatch.setattr(
        runner,
        "_preflight_contract",
        lambda **_kwargs: {
            "schema_version": "OMEGA_PREFLIGHT_REPORT_v1",
            "ok_b": True,
            "fail_reason": "",
            "checks": [],
        },
    )
    monkeypatch.setattr(runner.subprocess, "run", _fake_subprocess_run)
    monkeypatch.setattr(runner.omega_llm_router_v1, "run_failsoft", _fake_llm_router_run_failsoft)

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
        "--enable_llm_router",
        "1",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    runner.main()

    run_dirs = sorted(runs_root.glob("omega_overnight_*"))
    assert run_dirs
    run_dir = run_dirs[-1]

    assert router_ticks[0] == 0
    assert 10 in router_ticks

    plan_path = run_dir / "OMEGA_LLM_ROUTER_PLAN_v1.json"
    trace_path = run_dir / "OMEGA_LLM_TOOL_TRACE_v1.jsonl"
    replay_manifest_path = run_dir / "OMEGA_REPLAY_MANIFEST_v1.json"
    assert plan_path.exists()
    assert trace_path.exists()
    assert replay_manifest_path.exists()

    report = json.loads((run_dir / "OMEGA_OVERNIGHT_REPORT_v1.json").read_text(encoding="utf-8"))
    llm_router = report.get("llm_router") if isinstance(report, dict) else {}
    assert isinstance(llm_router, dict)
    assert bool(llm_router.get("enabled", False)) is True
    assert int(llm_router.get("invocations_u64", 0)) >= 2

    artifacts = report.get("artifacts") if isinstance(report, dict) else {}
    assert isinstance(artifacts, dict)
    assert str(artifacts.get("llm_router_plan_json", "")).endswith("OMEGA_LLM_ROUTER_PLAN_v1.json")
    assert str(artifacts.get("llm_router_tool_trace_jsonl", "")).endswith("OMEGA_LLM_TOOL_TRACE_v1.jsonl")
    assert str(artifacts.get("replay_manifest_json", "")).endswith("OMEGA_REPLAY_MANIFEST_v1.json")

    replay_manifest = json.loads(replay_manifest_path.read_text(encoding="utf-8"))
    artifact_rows = replay_manifest.get("artifacts") if isinstance(replay_manifest, dict) else []
    assert isinstance(artifact_rows, list)
    artifact_paths: set[str] = set()
    for row in artifact_rows:
        if not isinstance(row, dict):
            continue
        path_value = str(row.get("path", "")).strip()
        if not path_value:
            continue
        abs_path = Path(path_value).resolve()
        try:
            artifact_paths.add(abs_path.relative_to(run_dir.resolve()).as_posix())
        except Exception:  # noqa: BLE001
            artifact_paths.add(abs_path.as_posix())
    assert "OMEGA_LLM_ROUTER_PLAN_v1.json" in artifact_paths
    assert "OMEGA_LLM_TOOL_TRACE_v1.jsonl" in artifact_paths
    assert "polymath/store/indexes/urls_to_sha256.jsonl" in artifact_paths
