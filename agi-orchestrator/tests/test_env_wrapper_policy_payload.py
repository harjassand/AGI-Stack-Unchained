from __future__ import annotations

from orchestrator.agent_policy import wrapper_policy_payload


def test_env_wrapper_policy_payload() -> None:
    payload = wrapper_policy_payload(
        name="policy_agent",
        concept="gridworld",
        target_symbol="policy_oracle",
        type_norm="Int -> Int -> Int -> Int -> Int",
    )
    definition = payload["definitions"][0]
    assert definition["body"]["tag"] == "app"
    assert definition["body"]["fn"]["name"] == "policy_oracle"
