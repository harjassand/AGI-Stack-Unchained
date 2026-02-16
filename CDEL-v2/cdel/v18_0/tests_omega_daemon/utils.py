"""Test helpers for omega daemon v18.0."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cdel.v18_0.verify_rsi_omega_daemon_v1 import verify
from orchestrator.omega_v18_0.coordinator_v1 import run_tick


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def pack_path() -> Path:
    return repo_root() / "campaigns" / "rsi_omega_daemon_v18_0" / "rsi_omega_daemon_pack_v1.json"


def state_dir_for_out(out_dir: Path) -> Path:
    return out_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state"


def run_tick_once(tmp_path: Path, *, tick_u64: int = 1, prev_state_dir: Path | None = None) -> tuple[dict[str, Any], Path]:
    return run_tick_with_pack(
        tmp_path=tmp_path,
        campaign_pack=pack_path(),
        tick_u64=tick_u64,
        prev_state_dir=prev_state_dir,
    )


def run_tick_with_pack(
    *,
    tmp_path: Path,
    campaign_pack: Path,
    tick_u64: int = 1,
    prev_state_dir: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    out_dir = tmp_path / f"rsi_omega_daemon_v18_0_tick_{tick_u64:04d}"
    prev_mode = os.environ.get("OMEGA_META_CORE_ACTIVATION_MODE")
    prev_allow = os.environ.get("OMEGA_ALLOW_SIMULATE_ACTIVATION")
    os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = "simulate"
    os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = "1"
    try:
        result = run_tick(
            campaign_pack=campaign_pack,
            out_dir=out_dir,
            tick_u64=tick_u64,
            prev_state_dir=prev_state_dir,
        )
    finally:
        if prev_mode is None:
            os.environ.pop("OMEGA_META_CORE_ACTIVATION_MODE", None)
        else:
            os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = prev_mode
        if prev_allow is None:
            os.environ.pop("OMEGA_ALLOW_SIMULATE_ACTIVATION", None)
        else:
            os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = prev_allow
    return result, state_dir_for_out(out_dir)


def latest_file(path: Path, pattern: str) -> Path:
    rows = sorted(path.glob(pattern))
    if not rows:
        raise FileNotFoundError(f"missing {pattern} under {path}")
    return rows[-1]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    path.write_text(text, encoding="utf-8")


def verify_valid(state_dir: Path) -> str:
    return verify(state_dir, mode="full")


__all__ = [
    "latest_file",
    "load_json",
    "pack_path",
    "repo_root",
    "run_tick_once",
    "run_tick_with_pack",
    "state_dir_for_out",
    "verify_valid",
    "write_json",
]
