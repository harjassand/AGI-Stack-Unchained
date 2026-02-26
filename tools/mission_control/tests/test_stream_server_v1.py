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
        return {"mission_id": "sha256:test", "staged_path": ".omega_cache/mission_staging/pending_mission.json"}

    monkeypatch.setattr(stream_server_v1, "_resolve_nlpmc_compiler", lambda: positional_compiler)

    client = TestClient(stream_server_v1.app)
    response = client.post("/api/mission", json={"human_intent_str": "test intent"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "mission_id": "sha256:test",
        "staged_path": ".omega_cache/mission_staging/pending_mission.json",
    }
