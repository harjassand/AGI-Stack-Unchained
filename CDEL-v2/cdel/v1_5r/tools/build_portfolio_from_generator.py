"""Build v1.5r portfolios from a generator spec."""

from __future__ import annotations

import argparse
from pathlib import Path

from cdel.v1_5r.portfolio.generator import build_from_generator, load_generator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator", required=True)
    parser.add_argument("--out_root", required=True)
    args = parser.parse_args()

    generator = load_generator(Path(args.generator))
    build_from_generator(generator, Path(args.out_root))


if __name__ == "__main__":
    main()
