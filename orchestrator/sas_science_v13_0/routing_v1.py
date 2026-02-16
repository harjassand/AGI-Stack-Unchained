"""Routing helpers for SAS-Science v13.0."""

from __future__ import annotations

from pathlib import Path


def resolve_run_root(state_dir: Path) -> Path:
    return state_dir.resolve()


__all__ = ["resolve_run_root"]
