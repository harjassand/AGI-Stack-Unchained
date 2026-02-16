"""CLI entry for v7.0 alignment runs."""

from __future__ import annotations

import argparse
from pathlib import Path

from orchestrator.superego_v7_0.alignment_runner_v1 import run_alignment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alignment_pack", required=True)
    parser.add_argument("--out_alignment_dir", required=True)
    args = parser.parse_args()

    run_alignment(alignment_pack_path=Path(args.alignment_pack), out_alignment_dir=Path(args.out_alignment_dir))


if __name__ == "__main__":
    main()
