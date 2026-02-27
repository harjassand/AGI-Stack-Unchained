"""Tests for Mission Control stream server mission endpoint behavior."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tools.mission_control import stream_server_v1


def test_api_mission_returns_structured_error_payload(monkeypatch) -> None:
    def broken_compiler(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("NLPMC_VALIDATION_FAILED: parse failed")

    monkeypatch.setattr(stream_server_v1, "_resolve_nlpmc_compiler", lambda: broken_compiler)

    client = TestClient(stream_server_v1.app)
    response = client.post("/api/mission", json={"human_intent_str": "test intent"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "error": "NLPMC_VALIDATION_FAILED: parse failed",
    }


def test_api_mission_keeps_not_available_response(monkeypatch) -> None:
    monkeypatch.setattr(stream_server_v1, "_resolve_nlpmc_compiler", lambda: None)

    client = TestClient(stream_server_v1.app)
    response = client.post("/api/mission", json={"human_intent_str": "test intent"})

    assert response.status_code == 501
    assert response.json() == {"ok": False, "error": "NLPMC_NOT_AVAILABLE"}


def test_api_mission_supports_positional_compiler(monkeypatch) -> None:
    def positional_compiler(human_intent_str: str):
        return {
            "mission_id": "sha256:test",
            "staged_path": ".omega_cache/mission_staging/pending_mission.json",
            "payload": {
                "schema_name": "mission_request_v1",
                "schema_version": "v19_0",
                "user_prompt": human_intent_str,
                "domain": "general",
                "success_spec": {
                    "definition_of_done": "produce a deterministic report",
                    "pinned_eval_refs": [
                        {
                            "suitepack_id": "suitepack_demo_v1",
                            "heldout_b": True,
                            "gate": {"metric": "score", "op": ">=", "threshold_q32": 0},
                        }
                    ],
                    "deliverables": ["report"],
                },
            },
        }

    monkeypatch.setattr(stream_server_v1, "_resolve_nlpmc_compiler", lambda: positional_compiler)

    client = TestClient(stream_server_v1.app)
    response = client.post("/api/mission", json={"human_intent_str": "test intent"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert isinstance(payload["mission_id"], str) and payload["mission_id"].startswith("sha256:")
    assert payload["staged_path"] == ".omega_cache/mission_staging/pending_mission.json"
    assert payload["compile_receipt"]["ok_b"] is True
    assert payload["mission_graph_id"].startswith("sha256:")


def test_api_chat_returns_direct_answer_for_arithmetic() -> None:
    client = TestClient(stream_server_v1.app)
    response = client.post("/api/chat", json={"message": "whats 12+3", "mode": "customer"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "kind": "DIRECT_ANSWER",
        "assistant_message": "15",
        "confidence": "HIGH",
    }


def test_api_chat_stages_mission_for_non_arithmetic(monkeypatch) -> None:
    def positional_compiler(human_intent_str: str):
        return {
            "mission_id": "sha256:test",
            "staged_path": ".omega_cache/mission_staging/pending_mission.json",
            "payload": {
                "schema_name": "mission_request_v1",
                "schema_version": "v19_0",
                "domain": "general",
                "user_prompt": human_intent_str,
                "success_spec": {
                    "definition_of_done": "report",
                    "pinned_eval_refs": [
                        {
                            "suitepack_id": "suitepack_demo_v1",
                            "heldout_b": True,
                            "gate": {"metric": "score", "op": ">=", "threshold_q32": 0},
                        }
                    ],
                    "deliverables": ["report"],
                },
            },
        }

    monkeypatch.setattr(stream_server_v1, "_resolve_nlpmc_compiler", lambda: positional_compiler)

    client = TestClient(stream_server_v1.app)
    response = client.post("/api/chat", json={"message": "solve dark matter", "mode": "customer"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["kind"] == "MISSION"
    assert payload["assistant_message"] == "Queued. Streaming progress and verified artifacts as they arrive."
    assert payload["mission_staged_path"] == ".omega_cache/mission_staging/pending_mission.json"
    assert payload["mission_request_preview"]["schema_name"] == "mission_request_v1"
    assert payload["mission_request_preview"]["schema_version"] == "v19_0"
    assert payload["compile_receipt"]["ok_b"] is True
    assert payload["mission_graph_id"].startswith("sha256:")
