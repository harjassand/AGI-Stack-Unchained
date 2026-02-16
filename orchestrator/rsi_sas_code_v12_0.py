"""CLI entrypoint for SAS-CODE v12.0 with Omega dispatch flags."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .sas_code_v12_0.controller_v1 import run_sas_code


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(prog="rsi_sas_code_v12_0")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    os.environ["AGI_ROOT"] = str(out_dir)

    sas_root = out_dir / "daemon" / "rsi_sas_code_v12_0"
    control_dir = sas_root / "state" / "control"
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "ENABLE_RESEARCH").write_text("enable", encoding="utf-8")
    (control_dir / "ENABLE_SAS_CODE").write_text("enable", encoding="utf-8")

    lease_src = _repo_root() / "campaigns" / "rsi_sas_code_v12_0" / "sas_code_lease_token_v1.json"
    if not lease_src.is_file():
        print("MISSING_LEASE", file=sys.stderr)
        raise SystemExit(1)
    (control_dir / "SAS_CODE_LEASE.json").write_bytes(lease_src.read_bytes())

    try:
        run_sas_code(sas_code_root=sas_root, pack_path=Path(args.campaign_pack))
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED:{exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("OK")


if __name__ == "__main__":
    main()
