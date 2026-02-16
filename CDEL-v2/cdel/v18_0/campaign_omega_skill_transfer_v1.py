"""Analysis-only Omega campaign for legacy transfer skill reports."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .omega_common_v1 import load_canon_dict, repo_root
from .skills.skill_runner_v1 import discover_authoritative_state_root, run_skill_report


_CAMPAIGN_ID = "rsi_omega_skill_transfer_v1"
_SCHEMA_VERSION = "rsi_omega_skill_transfer_pack_v1"
_ADAPTER_MODULE = "cdel.v18_0.skills.transfer_v1_6r_adapter_v1"
_FIXED_REPORT_REL = Path("skills/reports/transfer/omega_skill_report_v1.json")


def _load_pack(path: Path) -> dict:
    payload = load_canon_dict(path)
    if str(payload.get("schema_version", "")).strip() != _SCHEMA_VERSION:
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    return payload


def run(*, campaign_pack: Path, out_dir: Path) -> None:
    pack = _load_pack(campaign_pack)
    root = repo_root()

    preferred_state_root: Path | None = None
    state_rel = str(pack.get("authoritative_state_root_rel", "")).strip()
    if state_rel:
        preferred_state_root = (root / state_rel).resolve()

    state_root = discover_authoritative_state_root(preferred_state_root)
    if state_root is None:
        state_root = (root / "daemon" / "rsi_omega_daemon_v18_0" / "state").resolve()

    config_dir = state_root.parent / "config"
    campaign_state_out = out_dir.resolve() / "daemon" / _CAMPAIGN_ID / "state"
    tick_u64 = max(0, int(str(os.environ.get("OMEGA_TICK_U64", "0")).strip() or "0"))

    run_skill_report(
        tick_u64=tick_u64,
        state_root=state_root,
        config_dir=config_dir,
        out_dir=campaign_state_out,
        adapter_module=_ADAPTER_MODULE,
        fixed_report_path=(root / _FIXED_REPORT_REL),
    )
    print("OK")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="campaign_omega_skill_transfer_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run(
        campaign_pack=Path(args.campaign_pack).resolve(),
        out_dir=Path(args.out_dir).resolve(),
    )


if __name__ == "__main__":
    main()
