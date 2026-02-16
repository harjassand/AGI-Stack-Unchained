"""Deterministic problem selector (v8.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Tuple

from cdel.v8_0.math_problem import load_problem_spec


class ProblemSelectionError(RuntimeError):
    pass


def select_problem(problems_dir: Path, *, policy: str) -> Tuple[dict[str, Any], Path]:
    _ = policy
    if not problems_dir.exists():
        raise ProblemSelectionError("MISSING_PROBLEMS_DIR")
    candidates = sorted(problems_dir.glob("*.math_problem_spec_v1.json"))
    if not candidates:
        raise ProblemSelectionError("NO_PROBLEMS")
    path = candidates[0]
    return load_problem_spec(path), path


__all__ = ["select_problem", "ProblemSelectionError"]
