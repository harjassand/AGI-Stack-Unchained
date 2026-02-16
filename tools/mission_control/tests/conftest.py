"""Pytest configuration for Mission Control tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Add tools/mission_control to path so 'mission_control' package can be imported
tools_mission_control_dir = Path(__file__).parent.parent.resolve()
if str(tools_mission_control_dir) not in sys.path:
    sys.path.insert(0, str(tools_mission_control_dir))
