"""Build superego action requests (v7.0)."""

from __future__ import annotations

from typing import Any

from cdel.v7_0.superego_policy import compute_request_id

MAX_OBJECTIVE_TEXT = 512


def build_action_request(
    *,
    daemon_id: str,
    tick: int,
    objective_class: str,
    objective_text: str,
    capabilities: list[str],
    target_paths: list[str],
    sealed_eval_required: bool,
    inputs: list[str] | None = None,
    outputs_planned: list[str] | None = None,
) -> dict[str, Any]:
    text = objective_text
    if len(text) > MAX_OBJECTIVE_TEXT:
        text = text[:MAX_OBJECTIVE_TEXT]

    payload: dict[str, Any] = {
        "schema_version": "superego_action_request_v1",
        "request_id": "",
        "daemon_id": daemon_id,
        "tick": int(tick),
        "objective_class": objective_class,
        "objective_text": text,
        "capabilities": list(capabilities),
        "target_paths": list(target_paths),
        "sealed_eval_required": bool(sealed_eval_required),
    }
    if inputs:
        payload["inputs"] = list(inputs)
    if outputs_planned:
        payload["outputs_planned"] = list(outputs_planned)

    payload["request_id"] = compute_request_id(payload)
    return payload


__all__ = ["build_action_request"]
