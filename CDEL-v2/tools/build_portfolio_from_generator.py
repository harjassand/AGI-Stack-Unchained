#!/usr/bin/env python3
"""Build v1_5r portfolios from a pinned generator spec."""

from __future__ import annotations

import argparse
from pathlib import Path

from cdel.v1_5r.portfolio.generator import build_from_generator, load_generator


def main() -> None:
    parser = argparse.ArgumentParser(description="Build v1_5r portfolios from generator spec")
    parser.add_argument("--generator", required=True, help="path to portfolio_generator_v1.json")
    parser.add_argument("--out-root", required=True, help="output directory root")
    args = parser.parse_args()

    generator = load_generator(Path(args.generator))
    out_root = Path(args.out_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    build_from_generator(generator, out_root)


if __name__ == "__main__":
    main()
