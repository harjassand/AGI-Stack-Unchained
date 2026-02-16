"""CLI entrypoint for SAS-MATH v11.0."""

from __future__ import annotations

import argparse
from pathlib import Path

from .sas_math_v11_0.controller_v1 import run_sas_math


def main() -> None:
    parser = argparse.ArgumentParser(prog="rsi_sas_math_v11_0")
    parser.add_argument("--sas_math_pack", required=True)
    parser.add_argument("--sas_math_root", required=True)
    args = parser.parse_args()

    result = run_sas_math(sas_math_root=Path(args.sas_math_root), pack_path=Path(args.sas_math_pack))
    print(result.get("status", "OK"))
    for key, value in result.items():
        if key == "status":
            continue
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
