"""CLI entrypoint for RSI Omega daemon v18.0."""

from __future__ import annotations

import argparse
from pathlib import Path

from .omega_v18_0.coordinator_v1 import run_tick


def main() -> None:
    parser = argparse.ArgumentParser(prog="rsi_omega_daemon_v18_0")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--mode", required=True, choices=["once", "loop"])
    parser.add_argument("--tick_u64", required=False, type=int, default=1)
    parser.add_argument("--prev_state_dir", required=False)
    parser.add_argument("--ticks", required=False, type=int, default=1)
    args = parser.parse_args()

    if args.mode == "once":
        result = run_tick(
            campaign_pack=Path(args.campaign_pack),
            out_dir=Path(args.out_dir),
            tick_u64=int(args.tick_u64),
            prev_state_dir=Path(args.prev_state_dir) if args.prev_state_dir else None,
        )
        print(result.get("status", "OK"))
        if str(result.get("runaway_state", "")).strip() == "ACTIVE":
            print(f"Runaway State: ACTIVE (Level {int(result.get('runaway_level_u64', 0))})")
        for key, value in result.items():
            if key == "status":
                continue
            print(f"{key}: {value}")
        return

    prev_state_dir = Path(args.prev_state_dir) if args.prev_state_dir else None
    for offset in range(int(args.ticks)):
        tick = int(args.tick_u64) + offset
        out_dir = Path(str(args.out_dir).format(tick=tick))
        result = run_tick(
            campaign_pack=Path(args.campaign_pack),
            out_dir=out_dir,
            tick_u64=tick,
            prev_state_dir=prev_state_dir,
        )
        print(result.get("status", "OK"))
        if str(result.get("runaway_state", "")).strip() == "ACTIVE":
            print(f"Runaway State: ACTIVE (Level {int(result.get('runaway_level_u64', 0))})")
        for key, value in result.items():
            if key == "status":
                continue
            print(f"{key}: {value}")
        prev_state_dir = out_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state"
        if result.get("safe_halt"):
            break


if __name__ == "__main__":
    main()
