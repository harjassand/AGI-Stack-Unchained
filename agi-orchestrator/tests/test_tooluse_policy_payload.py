from __future__ import annotations

from orchestrator.agent_policy import tooluse_policy_payload


def test_tooluse_policy_payload_contains_actions() -> None:
    payload = tooluse_policy_payload(
        name="tooluse_agent",
        concept="tooluse.file_transform",
        action_sequence=[0, 1],
    )
    definition = payload["definitions"][0]
    body = definition["body"]
    assert body["tag"] == "if"
    assert body["then"]["value"] == 0
    assert body["else"]["then"]["value"] == 1
