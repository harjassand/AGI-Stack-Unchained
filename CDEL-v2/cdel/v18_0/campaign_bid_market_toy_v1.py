"""Deterministic toy campaign for bid-market end-to-end tests (v1).

This campaign is intentionally trivial: it only writes a single marker file into
its declared `state_dir_rel` under `--out_dir`.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .omega_common_v1 import fail, load_canon_dict, require_relpath


def _load_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != "rsi_bid_market_toy_pack_v1":
        fail("SCHEMA_FAIL")
    return payload


def _campaign_id_from_pack_path(campaign_pack: Path) -> str:
    # For repo-local packs: campaigns/<campaign_id>/<pack_file>.
    cid = campaign_pack.resolve().parent.name
    cid = str(cid).strip()
    if not cid:
        fail("SCHEMA_FAIL")
    return cid


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    _ = _load_pack(campaign_pack)
    tick_u64 = int(os.environ.get("OMEGA_TICK_U64", "0"))
    campaign_id = _campaign_id_from_pack_path(campaign_pack)

    state_dir_rel = require_relpath(f"daemon/{campaign_id}/state")
    state_root = out_dir.resolve() / state_dir_rel
    state_root.mkdir(parents=True, exist_ok=True)

    marker = {
        "schema_version": "bid_market_toy_marker_v1",
        "campaign_id": campaign_id,
        "tick_u64": int(max(0, tick_u64)),
    }
    (state_root / "bid_market_toy_marker_v1.json").write_text(
        json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="campaign_bid_market_toy_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(campaign_pack=Path(args.campaign_pack), out_dir=Path(args.out_dir))


if __name__ == "__main__":
    main()

