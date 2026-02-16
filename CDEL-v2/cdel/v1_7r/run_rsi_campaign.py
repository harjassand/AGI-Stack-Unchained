"""Entry point for RSI demon v3 campaigns."""

from __future__ import annotations

import argparse
from pathlib import Path

from .demon.run import run_campaign


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RSI demon v3 campaign")
    parser.add_argument("--mode", default="real")
    parser.add_argument("--strict-rsi", action="store_true", dest="strict")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()

    run_campaign(
        campaign_pack=Path(args.campaign_pack),
        out_dir=Path(args.out_dir),
        mode=str(args.mode),
        strict=bool(args.strict),
    )


if __name__ == "__main__":
    main()
