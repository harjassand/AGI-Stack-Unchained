"""Deterministic Polymath SIP ingestion L0 campaign (v1)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .omega_common_v1 import fail, load_canon_dict, repo_root, validate_schema
from .polymath_sip_ingestion_l0_v1 import run_sip_ingestion_l0

_PACK_SCHEMA = "rsi_polymath_sip_ingestion_l0_pack_v1"


def _tick_from_env(default_u64: int = 0) -> int:
    raw = str(os.environ.get("OMEGA_TICK_U64", "")).strip()
    if not raw:
        return int(max(0, int(default_u64)))
    try:
        value = int(raw)
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    if value < 0:
        fail("SCHEMA_FAIL")
    return int(value)


def _load_pack(path: Path) -> dict[str, object]:
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != _PACK_SCHEMA:
        fail("SCHEMA_FAIL")
    validate_schema(payload, _PACK_SCHEMA)
    return payload


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    pack = _load_pack(campaign_pack)
    state_root = out_dir.resolve() / "daemon" / "rsi_polymath_sip_ingestion_l0_v1" / "state"
    state_root.mkdir(parents=True, exist_ok=True)

    _ = run_sip_ingestion_l0(
        config=pack,
        repo_root_path=repo_root(),
        state_root=state_root,
        tick_u64=_tick_from_env(),
    )

    print("OK")


def main() -> None:
    parser = argparse.ArgumentParser(prog="campaign_polymath_sip_ingestion_l0_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    run(campaign_pack=Path(args.campaign_pack), out_dir=Path(args.out_dir))


if __name__ == "__main__":
    main()
