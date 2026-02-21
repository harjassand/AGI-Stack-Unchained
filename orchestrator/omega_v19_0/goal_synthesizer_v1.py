"""v19-owned goal synthesizer wrapper over shared deterministic logic."""

from __future__ import annotations

from typing import Any

from orchestrator.omega_v18_0.goal_synthesizer_v1 import (
    suppressed_capability_ids_from_episodic_memory as _suppressed_capability_ids_from_episodic_memory_v18,
)
from orchestrator.omega_v18_0.goal_synthesizer_v1 import (
    synthesize_goal_queue as _synthesize_goal_queue_v18,
)


def synthesize_goal_queue(
    *,
    tick_u64: int,
    goal_queue_base: dict[str, Any],
    state: dict[str, Any],
    issue_bundle: dict[str, Any],
    observation_report: dict[str, Any],
    registry: dict[str, Any],
    runaway_cfg: dict[str, Any] | None = None,
    run_scorecard: dict[str, Any] | None = None,
    tick_stats: dict[str, Any] | None = None,
    tick_outcome: dict[str, Any] | None = None,
    hotspots: dict[str, Any] | None = None,
    episodic_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # v19 currently shares deterministic synthesis logic with v18.
    # Keep this wrapper so v19 policy thresholds can diverge without import churn.
    return _synthesize_goal_queue_v18(
        tick_u64=tick_u64,
        goal_queue_base=goal_queue_base,
        state=state,
        issue_bundle=issue_bundle,
        observation_report=observation_report,
        registry=registry,
        runaway_cfg=runaway_cfg,
        run_scorecard=run_scorecard,
        tick_stats=tick_stats,
        tick_outcome=tick_outcome,
        hotspots=hotspots,
        episodic_memory=episodic_memory,
    )


def suppressed_capability_ids_from_episodic_memory(
    *,
    tick_u64: int,
    episodic_memory: dict[str, Any] | None,
) -> list[str]:
    return _suppressed_capability_ids_from_episodic_memory_v18(
        tick_u64=tick_u64,
        episodic_memory=episodic_memory,
    )


__all__ = [
    "synthesize_goal_queue",
    "suppressed_capability_ids_from_episodic_memory",
]
