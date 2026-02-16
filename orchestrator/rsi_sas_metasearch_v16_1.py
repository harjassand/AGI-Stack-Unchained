"""CLI entrypoint for SAS-Metasearch v16.1."""

from __future__ import annotations

import argparse
from pathlib import Path

from .metasearch_v16_1.coordinator_v16_1 import run_sas_metasearch


def main() -> None:
    parser = argparse.ArgumentParser(prog="rsi_sas_metasearch_v16_1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()

    result = run_sas_metasearch(
        campaign_pack=Path(args.campaign_pack),
        out_dir=Path(args.out_dir),
        campaign_tag="rsi_sas_metasearch_v16_1",
    )
    print(result.get("status", "OK"))
    for key, value in result.items():
        if key == "status":
            continue
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
