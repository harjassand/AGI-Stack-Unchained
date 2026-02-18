"""Tracked orchestrator overlay for AGI-Stack root (v16.1 wiring).

This package extends lookup into Extension-1/agi-orchestrator/orchestrator so
existing orchestrator modules remain importable while v16.1 wrappers live in a
tracked root path.
"""

from __future__ import annotations

import os
from pathlib import Path
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]
_ext = Path(__file__).resolve().parents[1] / "Extension-1" / "agi-orchestrator" / "orchestrator"
if _ext.exists():
    __path__.append(str(_ext))  # type: ignore[attr-defined]

# When running inside a detached git worktree (ignite), untracked Extension-1 content
# may not exist in that worktree. Allow pointing at the host checkout explicitly.
_host_root = str(os.environ.get("OMEGA_HOST_REPO_ROOT", "")).strip()
if _host_root:
    _host_ext = Path(_host_root) / "Extension-1" / "agi-orchestrator" / "orchestrator"
    if _host_ext.exists():
        try:
            paths = list(__path__)  # type: ignore[attr-defined]
            host_str = str(_host_ext)
            if host_str not in paths:
                # Keep the overlay path first; prefer host extension content next.
                paths.insert(1, host_str)
                __path__[:] = paths  # type: ignore[index]
        except Exception:
            # Best-effort; if __path__ is not mutable, rely on sys.path ordering.
            pass
