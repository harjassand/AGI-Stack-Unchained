"""Omega-dispatchable EUDRS-U bootstrap producer: qxrl_train v1."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a script: `python orchestrator/rsi_eudrs_u_qxrl_train_v1.py ...`.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_CDEL_ROOT = _REPO_ROOT / "CDEL-v2"
if _CDEL_ROOT.is_dir() and str(_CDEL_ROOT) not in sys.path:
    sys.path.insert(0, str(_CDEL_ROOT))

from cdel.v18_0.omega_common_v1 import fail, load_canon_dict  # noqa: E402

from orchestrator.common.eudrs_u_bootstrap_producer_v1 import (  # noqa: E402
    emit_eudrs_u_bootstrap_promotion_bundle_v1,
)


_CAMPAIGN_ID = "rsi_eudrs_u_qxrl_train_v1"
_PACK_SCHEMA = "rsi_eudrs_u_qxrl_train_pack_v1"


def _load_pack(path: Path) -> dict:
    payload = load_canon_dict(path)
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if str(payload.get("schema_version", "")).strip() != _PACK_SCHEMA:
        fail("SCHEMA_FAIL")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=_CAMPAIGN_ID)
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir).resolve()
    _load_pack(Path(args.campaign_pack).resolve())

    state_dir = (out_dir / "daemon" / _CAMPAIGN_ID / "state").resolve()
    emit_eudrs_u_bootstrap_promotion_bundle_v1(state_dir=state_dir, producer_kind="qxrl_train")

    sys.stdout.write("OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
