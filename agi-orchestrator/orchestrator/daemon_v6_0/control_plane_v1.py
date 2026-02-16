"""Control-plane helpers (STOP/PAUSE + signals)."""

from __future__ import annotations

import signal
from pathlib import Path


class ControlPlane:
    def __init__(self, control_dir: Path) -> None:
        self.control_dir = control_dir
        self.stop_requested = False
        self.pause_requested = False

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_stop)
        signal.signal(signal.SIGINT, self._handle_stop)

    def _handle_stop(self, *_args: object) -> None:
        self.stop_requested = True

    def refresh(self) -> None:
        if (self.control_dir / "STOP").exists():
            self.stop_requested = True
        self.pause_requested = (self.control_dir / "PAUSE").exists()


__all__ = ["ControlPlane"]
