"""CLI entrypoint for the APA v1 campaign."""

from __future__ import annotations

import argparse
from pathlib import Path

from tools.arena.proposer_arena_v1 import run


def main() -> None:
    parser = argparse.ArgumentParser(prog="rsi_proposer_arena_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(
        campaign_pack=Path(args.campaign_pack).resolve(),
        out_dir=Path(args.out_dir).resolve(),
    )


if __name__ == "__main__":
    main()

