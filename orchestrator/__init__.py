"""Tracked orchestrator overlay for AGI-Stack root (v16.1 wiring).

This package extends lookup into Extension-1/agi-orchestrator/orchestrator so
existing orchestrator modules remain importable while v16.1 wrappers live in a
tracked root path.
"""

from __future__ import annotations

from pathlib import Path
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]
_ext = Path(__file__).resolve().parents[1] / "Extension-1" / "agi-orchestrator" / "orchestrator"
if _ext.exists():
    __path__.append(str(_ext))  # type: ignore[attr-defined]
