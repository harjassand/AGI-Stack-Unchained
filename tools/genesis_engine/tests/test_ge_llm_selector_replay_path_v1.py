from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.genesis_engine import ge_symbiotic_optimizer_v0_3 as ge_v0_3


def _sha256_prefixed(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _selector_prompt_for_test(
    *,
    candidates: list[dict[str, str]],
    max_proposals_u64: int,
    max_ccaps: int,
    latest_observation: dict[str, object],
    allowed_targets: list[str],
    allowed_templates: list[str],
) -> str:
    candidate_pool = list(candidates[: max(1, int(max_proposals_u64))])
    return ge_v0_3._selector_prompt(  # noqa: SLF001
        skill_metrics=ge_v0_3._normalized_skill_metrics_for_prompt(latest_observation),  # noqa: SLF001
        allowed_targets=allowed_targets,
        allowed_templates=allowed_templates,
        candidates=[
            {
                "template_id": str(row["template_id"]),
                "target_relpath": str(row["target_relpath"]),
            }
            for row in candidate_pool
        ],
        max_select=max_ccaps,
    )


def test_ge_llm_selector_replay_path_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replay_path = tmp_path / "selector_replay.jsonl"
    allowed_targets = [
        "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json",
        "campaigns/rsi_omega_daemon_v18_0_prod/omega_capability_registry_v2.json",
    ]
    allowed_templates = ["JSON_TWEAK_COOLDOWN_MINUS_1", "JSON_TWEAK_BUDGET_HINT_MINUS_1STEP"]
    planned_candidates = [
        {
            "bucket": "nov",
            "template_id": "JSON_TWEAK_COOLDOWN_MINUS_1",
            "target_relpath": "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json",
        },
        {
            "bucket": "grow",
            "template_id": "JSON_TWEAK_BUDGET_HINT_MINUS_1STEP",
            "target_relpath": "campaigns/rsi_omega_daemon_v18_0_prod/omega_capability_registry_v2.json",
        },
    ]
    latest_observation = {
        "metrics": {
            "alignment_q32": {"q": 1 << 32},
            "math_attempts_u64": 3,
            "math_success_rate_rat": {"num_u64": 1, "den_u64": 2},
        }
    }
    selector_cfg = {
        "enabled_b": True,
        "backend": "openai_replay",
        "model": "gpt-4.1",
        "max_proposals_u64": 8,
    }
    max_ccaps = 2

    prompt = _selector_prompt_for_test(
        candidates=planned_candidates,
        max_proposals_u64=8,
        max_ccaps=max_ccaps,
        latest_observation=latest_observation,
        allowed_targets=allowed_targets,
        allowed_templates=allowed_templates,
    )
    response = json.dumps(
        [
            {
                "template_id": "JSON_TWEAK_COOLDOWN_MINUS_1",
                "target_relpath": "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json",
            }
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
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
    monkeypatch.setenv("ORCH_LLM_REPLAY_PATH", str(replay_path))

    selected_a, prompt_rows_a, error_a = ge_v0_3._select_with_llm_selector(  # noqa: SLF001
        selector_cfg=selector_cfg,
        candidates=planned_candidates,
        allowed_targets=allowed_targets,
        allowed_templates=allowed_templates,
        max_ccaps=max_ccaps,
        latest_observation=latest_observation,
    )
    selected_b, prompt_rows_b, error_b = ge_v0_3._select_with_llm_selector(  # noqa: SLF001
        selector_cfg=selector_cfg,
        candidates=planned_candidates,
        allowed_targets=allowed_targets,
        allowed_templates=allowed_templates,
        max_ccaps=max_ccaps,
        latest_observation=latest_observation,
    )

    assert error_a is None
    assert error_b is None
    assert selected_a == selected_b
    assert selected_a == [
        {
            "bucket": "nov",
            "template_id": "JSON_TWEAK_COOLDOWN_MINUS_1",
            "target_relpath": "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json",
            "model": "gpt-4.1",
        }
    ]
    assert prompt_rows_a == prompt_rows_b
    assert prompt_rows_a[0]["prompt_hash"] == _sha256_prefixed(prompt)
    assert prompt_rows_a[0]["response_hash"] == _sha256_prefixed(response)


def test_ge_llm_selector_accepts_items_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replay_path = tmp_path / "selector_replay_items_envelope.jsonl"
    selector_cfg = {
        "enabled_b": True,
        "backend": "openai_replay",
        "model": "gpt-4.1",
        "max_proposals_u64": 8,
    }
    candidates = [
        {
            "bucket": "nov",
            "template_id": "JSON_TWEAK_COOLDOWN_MINUS_1",
            "target_relpath": "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json",
        }
    ]
    allowed_targets = ["campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json"]
    allowed_templates = ["JSON_TWEAK_COOLDOWN_MINUS_1"]
    max_ccaps = 1
    latest_observation = {"metrics": {}}

    prompt = _selector_prompt_for_test(
        candidates=candidates,
        max_proposals_u64=8,
        max_ccaps=max_ccaps,
        latest_observation=latest_observation,
        allowed_targets=allowed_targets,
        allowed_templates=allowed_templates,
    )
    response = json.dumps(
        {
            "type": "array",
            "items": [
                {
                    "template_id": "JSON_TWEAK_COOLDOWN_MINUS_1",
                    "target_relpath": "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json",
                }
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
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
    monkeypatch.setenv("ORCH_LLM_REPLAY_PATH", str(replay_path))

    selected, _prompt_rows, error_reason = ge_v0_3._select_with_llm_selector(  # noqa: SLF001
        selector_cfg=selector_cfg,
        candidates=candidates,
        allowed_targets=allowed_targets,
        allowed_templates=allowed_templates,
        max_ccaps=max_ccaps,
        latest_observation=latest_observation,
    )

    assert error_reason is None
    assert selected == [
        {
            "bucket": "nov",
            "template_id": "JSON_TWEAK_COOLDOWN_MINUS_1",
            "target_relpath": "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json",
            "model": "gpt-4.1",
        }
    ]


def test_ge_llm_selector_replay_miss_is_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replay_path = tmp_path / "missing_selector_replay.jsonl"
    replay_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("ORCH_LLM_REPLAY_PATH", str(replay_path))

    selected, prompt_rows, error_reason = ge_v0_3._select_with_llm_selector(  # noqa: SLF001
        selector_cfg={
            "enabled_b": True,
            "backend": "openai_replay",
            "model": "gpt-4.1",
            "max_proposals_u64": 8,
        },
        candidates=[
            {
                "bucket": "nov",
                "template_id": "JSON_TWEAK_COOLDOWN_MINUS_1",
                "target_relpath": "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json",
            }
        ],
        allowed_targets=["campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json"],
        allowed_templates=["JSON_TWEAK_COOLDOWN_MINUS_1"],
        max_ccaps=1,
        latest_observation={"metrics": {}},
    )

    assert selected == []
    assert prompt_rows == []
    assert error_reason == "LLM_REPLAY_MISS"
