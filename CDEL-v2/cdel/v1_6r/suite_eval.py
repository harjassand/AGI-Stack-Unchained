"""Suite evaluation helper shared with Pi0 gate eval (v1.5r)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.sealed.harnesses import get_harness


def run_suite_eval(
    *,
    eval_cfg: dict[str, Any],
    defs_env: dict[str, object],
    baseline_symbol: str,
    candidate_symbol: str,
    oracle_symbol: str,
    seed_key: bytes,
    project_root: Path,
    int_min: int,
    int_max: int,
    list_max_len: int,
    fun_symbols: list[str],
    artifact_dir: Path | None,
) -> tuple[list[int], int, int, bytes]:
    """Run a suite evaluation using the same harness path as sealed worker."""
    harness_id = eval_cfg.get("eval_harness_id")
    harness_hash = eval_cfg.get("eval_harness_hash")
    if not isinstance(harness_id, str) or not isinstance(harness_hash, str):
        raise ValueError("eval_harness_id/hash required")
    harness = get_harness(harness_id)
    if harness.harness_hash != harness_hash:
        raise ValueError("eval_harness_hash mismatch")
    return harness.run_episodes(
        eval_cfg=eval_cfg,
        defs_env=defs_env,
        baseline_symbol=baseline_symbol,
        candidate_symbol=candidate_symbol,
        oracle_symbol=oracle_symbol,
        seed_key=seed_key,
        project_root=project_root,
        int_min=int_min,
        int_max=int_max,
        list_max_len=list_max_len,
        fun_symbols=fun_symbols,
        artifact_dir=artifact_dir,
    )
