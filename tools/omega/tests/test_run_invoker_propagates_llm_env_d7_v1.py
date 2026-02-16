from __future__ import annotations

import json
from pathlib import Path

from orchestrator.common.run_invoker_v1 import _build_env, run_module


def test_run_invoker_propagates_llm_and_net_env(monkeypatch, tmp_path: Path) -> None:
    replay_path = (tmp_path / "replay" / "orch_llm_replay.jsonl").resolve()
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    replay_path.write_text("", encoding="utf-8")

    monkeypatch.setenv("OMEGA_NET_LIVE_OK", "1")
    monkeypatch.setenv("ORCH_LLM_BACKEND", "openai_replay")
    monkeypatch.setenv("ORCH_LLM_REPLAY_PATH", replay_path.as_posix())
    monkeypatch.setenv("ORCH_LLM_MAX_CALLS", "7")
    monkeypatch.setenv("ORCH_LLM_TEMPERATURE", "0.7")
    monkeypatch.setenv("ORCH_LLM_MAX_TOKENS", "2048")
    monkeypatch.setenv("ORCH_LLM_TOP_P", "0.9")

    module_path = tmp_path / "env_probe_llm_v1.py"
    module_path.write_text(
        "import json\n"
        "import os\n"
        "print(json.dumps({\n"
        "  'OMEGA_NET_LIVE_OK': os.environ.get('OMEGA_NET_LIVE_OK',''),\n"
        "  'ORCH_LLM_BACKEND': os.environ.get('ORCH_LLM_BACKEND',''),\n"
        "  'ORCH_LLM_REPLAY_PATH': os.environ.get('ORCH_LLM_REPLAY_PATH',''),\n"
        "  'ORCH_LLM_MAX_CALLS': os.environ.get('ORCH_LLM_MAX_CALLS',''),\n"
        "  'ORCH_LLM_TEMPERATURE': os.environ.get('ORCH_LLM_TEMPERATURE',''),\n"
        "  'ORCH_LLM_MAX_TOKENS': os.environ.get('ORCH_LLM_MAX_TOKENS',''),\n"
        "  'ORCH_LLM_TOP_P': os.environ.get('ORCH_LLM_TOP_P',''),\n"
        "}, sort_keys=True, separators=(',',':')))\n",
        encoding="utf-8",
    )

    receipt = run_module(
        py_module="env_probe_llm_v1",
        argv=[],
        cwd=tmp_path,
        output_dir=tmp_path / "out",
    )
    assert int(receipt["return_code"]) == 0

    payload = json.loads(Path(receipt["stdout_path"]).read_text(encoding="utf-8").strip())
    assert payload["OMEGA_NET_LIVE_OK"] == "1"
    assert payload["ORCH_LLM_BACKEND"] == "openai_replay"
    assert payload["ORCH_LLM_REPLAY_PATH"] == replay_path.as_posix()
    assert payload["ORCH_LLM_MAX_CALLS"] == "7"
    assert payload["ORCH_LLM_TEMPERATURE"] == "0.7"
    assert payload["ORCH_LLM_MAX_TOKENS"] == "2048"
    assert payload["ORCH_LLM_TOP_P"] == "0.9"

    env = _build_env()
    assert env["OMEGA_NET_LIVE_OK"] == "1"
    assert env["ORCH_LLM_BACKEND"] == "openai_replay"
    assert env["ORCH_LLM_REPLAY_PATH"] == replay_path.as_posix()
    assert env["ORCH_LLM_MAX_CALLS"] == "7"
    assert env["ORCH_LLM_TEMPERATURE"] == "0.7"
    assert env["ORCH_LLM_MAX_TOKENS"] == "2048"
    assert env["ORCH_LLM_TOP_P"] == "0.9"
