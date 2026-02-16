#!/usr/bin/env python3
"""Update the pyut heldout config hash only."""

from __future__ import annotations

import argparse

from pathlib import Path

from orchestrator.heldout_rotation import update_heldout_config_hash


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update pyut heldout config hash")
    parser.add_argument("--heldout-hash", required=True)
    parser.add_argument("--heldout-config", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    update_heldout_config_hash(config_path=Path(args.heldout_config), suite_hash=args.heldout_hash)
    print(
        f"Updated heldout config hash to {args.heldout_hash}. "
        "Deploy suite bytes via CDEL_SUITES_DIR."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
