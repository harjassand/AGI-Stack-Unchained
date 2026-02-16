"""Eval harness interface for sealed worker."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class EvalHarness(Protocol):
    harness_id: str
    harness_hash: str

    def run_episodes(
        self,
        *,
        eval_cfg: dict,
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
        ...
