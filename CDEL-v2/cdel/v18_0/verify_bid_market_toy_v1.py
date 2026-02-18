"""Toy verifier for bid-market end-to-end tests (v1)."""

from __future__ import annotations

import argparse
from pathlib import Path


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        return "INVALID:MODE_UNSUPPORTED"
    root = state_dir.resolve()
    if not root.exists() or not root.is_dir():
        return "INVALID:MISSING_STATE_INPUT"
    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_bid_market_toy_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()
    print(verify(Path(args.state_dir), mode=str(args.mode)))


if __name__ == "__main__":
    main()

