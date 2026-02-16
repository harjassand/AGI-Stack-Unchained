"""CLI entrypoint for flagship code RSI v1."""

from __future__ import annotations

import argparse
import sys

from ..domains.flagship_code_rsi_v1.domain import run_flagship
from ..domains.flagship_code_rsi_v1.replay_v1 import replay_run, verify_run


def _cmd_run(args: argparse.Namespace) -> int:
    run_timeout = args.run_wall_timeout_s if args.run_wall_timeout_s is not None else args.wall_timeout_s
    run_flagship(
        args.config,
        args.epochs,
        heldout=args.heldout,
        wall_timeout_s=run_timeout,
        epoch_wall_timeout_s=args.epoch_wall_timeout_s,
        calibrate_only=args.calibrate_only,
    )
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    ok, errors = replay_run(args.run_dir)
    if not ok:
        for e in errors:
            print(e)
        return 1
    print("OK")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    ok, errors = verify_run(args.run_dir)
    if not ok:
        for e in errors:
            print(e)
        return 1
    print("OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="flagship_code_rsi_v1")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run_flagship")
    run_p.add_argument("--config", required=True)
    run_p.add_argument("--epochs", type=int, default=10)
    run_p.add_argument("--heldout", action="store_true")
    run_p.add_argument("--wall_timeout_s", type=int, default=0)
    run_p.add_argument("--run_wall_timeout_s", type=int, default=None)
    run_p.add_argument("--epoch_wall_timeout_s", type=int, default=None)
    run_p.add_argument("--calibrate_only", action="store_true")
    run_p.set_defaults(func=_cmd_run)

    replay_p = sub.add_parser("replay_flagship")
    replay_p.add_argument("--run_dir", required=True)
    replay_p.set_defaults(func=_cmd_replay)

    verify_p = sub.add_parser("verify_flagship")
    verify_p.add_argument("--run_dir", required=True)
    verify_p.set_defaults(func=_cmd_verify)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
