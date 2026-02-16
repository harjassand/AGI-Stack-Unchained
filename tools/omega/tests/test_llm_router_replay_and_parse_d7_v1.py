from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.omega import omega_llm_router_v1 as router_v1


def _sha256_prefixed(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_registry(path: Path) -> None:
    payload = {
        "schema_version": "omega_capability_registry_v2",
        "capabilities": [
            {
                "campaign_id": "rsi_sas_metasearch_v16_1",
                "capability_id": "RSI_SAS_METASEARCH",
                "enabled": True,
            },
            {
                "campaign_id": "rsi_sas_code_v12_0",
                "capability_id": "RSI_SAS_CODE",
                "enabled": False,
            },
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_llm_router_replay_parse_and_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_registry(run_dir / "_overnight_pack" / "omega_capability_registry_v2.json")

    allowlists = router_v1._load_registry_allowlists(run_dir)  # noqa: SLF001
    prompt_payload = router_v1._prompt_payload(run_dir=run_dir, tick_u64=10, allowlists=allowlists)  # noqa: SLF001
    prompt = json.dumps(prompt_payload, sort_keys=True, separators=(",", ":"))

    response = json.dumps(
        {
            "schema_version": "omega_llm_router_plan_v1",
            "created_at_utc": "should_be_ignored",
            "created_from_tick_u64": 999,
            "web_queries": [
                {"provider": "unknown", "query": "ignored", "top_k": 1},
                {"provider": "duckduckgo", "query": "x" * 300, "top_k": 5},
            ],
            "goal_injections": [
                {
                    "capability_id": "RSI_SAS_METASEARCH",
                    "goal_id": "goal_auto_router_0001",
                    "priority_u8": 9,
                    "reason": "focus search quality",
                },
                {
                    "capability_id": "RSI_NOT_ENABLED",
                    "goal_id": "goal_bad",
                    "priority_u8": 20,
                    "reason": "must be rejected",
                },
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    replay_path = run_dir / "_overnight_pack" / "replay" / "orch_llm_replay.jsonl"
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    replay_row = {
        "schema_version": "orch_llm_replay_row_v1",
        "backend": "openai",
        "model": "gpt-4.1",
        "prompt_sha256": _sha256_prefixed(prompt),
        "response_sha256": _sha256_prefixed(response),
        "prompt": prompt,
        "response": response,
        "created_at_utc": "2026-02-11T00:00:00Z",
    }
    replay_path.write_text(json.dumps(replay_row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    monkeypatch.setenv("ORCH_LLM_BACKEND", "openai_replay")
    monkeypatch.setenv("ORCH_OPENAI_MODEL", "gpt-4.1")
    monkeypatch.setenv("ORCH_LLM_REPLAY_PATH", replay_path.as_posix())
    monkeypatch.setenv("ORCH_LLM_MAX_CALLS", "4")
    monkeypatch.setenv("ORCH_LLM_MAX_PROMPT_CHARS", "200000")
    monkeypatch.setenv("ORCH_LLM_MAX_RESPONSE_CHARS", "200000")
    monkeypatch.setenv("ORCH_LLM_TEMPERATURE", "0.6")
    monkeypatch.setenv("ORCH_LLM_MAX_TOKENS", "777")
    monkeypatch.setenv("ORCH_LLM_TOP_P", "0.8")

    result = router_v1.run(run_dir=run_dir, tick_u64=10, store_root=run_dir / "polymath" / "store")
    assert str(result.get("status", "")) == "OK"
    goals = result.get("goal_injections")
    assert isinstance(goals, list)
    assert goals == [
        {
            "capability_id": "RSI_SAS_METASEARCH",
            "goal_id": "goal_auto_router_0001",
            "priority_u8": 9,
            "reason": "focus search quality",
        }
    ]

    plan = json.loads((run_dir / "OMEGA_LLM_ROUTER_PLAN_v1.json").read_text(encoding="utf-8"))
    assert plan.get("schema_version") == "omega_llm_router_plan_v1"
    assert plan.get("created_at_utc") == ""
    assert int(plan.get("created_from_tick_u64", -1)) == 10
    diagnostics = plan.get("diagnostics") if isinstance(plan, dict) else {}
    assert isinstance(diagnostics, dict)
    assert len(diagnostics.get("rejected_web_queries", [])) == 2
    assert len(diagnostics.get("rejected_goal_injections", [])) == 1
    assert float(diagnostics.get("llm_temperature_f64", 0.0)) == 0.6
    assert int(diagnostics.get("llm_max_tokens_u64", 0)) == 777
    assert float(diagnostics.get("llm_top_p_f64", 0.0)) == 0.8

    trace_lines = [line for line in (run_dir / "OMEGA_LLM_TOOL_TRACE_v1.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(trace_lines) == 1
    trace = json.loads(trace_lines[0])
    assert trace.get("created_at_utc") == ""
    assert trace.get("prompt_sha256") == result.get("prompt_sha256")
    assert trace.get("response_sha256") == result.get("response_sha256")
    assert float(trace.get("llm_temperature_f64", 0.0)) == 0.6
    assert int(trace.get("llm_max_tokens_u64", 0)) == 777
    assert float(trace.get("llm_top_p_f64", 0.0)) == 0.8


def test_llm_router_failsoft_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_registry(run_dir / "_overnight_pack" / "omega_capability_registry_v2.json")

    monkeypatch.setenv("ORCH_LLM_BACKEND", "mock")
    monkeypatch.setenv("ORCH_LLM_MOCK_RESPONSE", "{this is not json")

    result = router_v1.run_failsoft(run_dir=run_dir, tick_u64=0, store_root=run_dir / "polymath" / "store")
    assert str(result.get("status", "")) == "ERROR"
    assert "LLM_ROUTER_INVALID_JSON" in str(result.get("error_reason", ""))

    plan = json.loads((run_dir / "OMEGA_LLM_ROUTER_PLAN_v1.json").read_text(encoding="utf-8"))
    assert plan.get("created_at_utc") == ""
    diagnostics = plan.get("diagnostics") if isinstance(plan, dict) else {}
    assert isinstance(diagnostics, dict)
    assert "LLM_ROUTER_INVALID_JSON" in str(diagnostics.get("error_reason", ""))


def test_llm_router_backend_alias_google_maps_to_gemini_harvest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = tmp_path / "run_alias"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_registry(run_dir / "_overnight_pack" / "omega_capability_registry_v2.json")

    monkeypatch.setenv("ORCH_LLM_BACKEND", "google")
    monkeypatch.setenv("ORCH_GEMINI_MODEL", "gemini-2.0-flash")
    monkeypatch.setenv("ORCH_LLM_REPLAY_PATH", (run_dir / "missing_replay.jsonl").as_posix())

    result = router_v1.run_failsoft(run_dir=run_dir, tick_u64=0, store_root=run_dir / "polymath" / "store")
    assert str(result.get("status", "")) == "ERROR"
    assert "LLM_LIVE_DISABLED" in str(result.get("error_reason", ""))
