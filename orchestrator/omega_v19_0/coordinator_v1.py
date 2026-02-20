"""Compatibility wrapper for the v19.0 deterministic microkernel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator.omega_v18_0.applier_v1 import run_activation
from orchestrator.omega_v18_0.goal_synthesizer_v1 import synthesize_goal_queue
from orchestrator.omega_v18_0.observer_v1 import read_meta_core_active_manifest_hash

from .microkernel_v1 import (
    _axis_gate_applies_safe_halt,
    _axis_gate_promotion_reason_code,
    _load_axis_gate_failure,
    tick_once,
)
from .promoter_v1 import run_promotion, run_subverifier


def run_tick(
    *,
    campaign_pack: Path,
    out_dir: Path,
    tick_u64: int,
    prev_state_dir: Path | None = None,
) -> dict[str, Any]:
    """Run one deterministic v19 tick using microkernel execution order."""

    return tick_once(
        campaign_pack=campaign_pack,
        out_dir=out_dir,
        tick_u64=tick_u64,
        prev_state_dir=prev_state_dir,
        run_subverifier_fn=run_subverifier,
        run_promotion_fn=run_promotion,
        run_activation_fn=run_activation,
        read_meta_core_active_manifest_hash_fn=read_meta_core_active_manifest_hash,
        synthesize_goal_queue_fn=synthesize_goal_queue,
    )


__all__ = [
    "run_tick",
    "run_subverifier",
    "run_promotion",
    "run_activation",
    "read_meta_core_active_manifest_hash",
    "synthesize_goal_queue",
    "_load_axis_gate_failure",
    "_axis_gate_applies_safe_halt",
    "_axis_gate_promotion_reason_code",
]
