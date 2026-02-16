"""Deterministic stub devscreen runner (v1)."""

from __future__ import annotations

import argparse
import json
import os


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out_dir", default=".")
    args, _ = parser.parse_known_args()

    out_dir = args.out_dir or "."
    os.makedirs(out_dir, exist_ok=True)

    m_bp = 7000 + (int(args.seed) % 1000)
    payload = {"pass_rates": {"dev": {"C": m_bp}}}

    path = os.path.join(out_dir, "ceiling_ladder_summary.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, sort_keys=True)


if __name__ == "__main__":
    main()
