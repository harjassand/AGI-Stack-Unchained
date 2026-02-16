"""Omega-dispatchable EUDRS-U producer: train v1 (DMPL Phase 4).

Producer code is untrusted (RE3). It MUST only emit content-addressed artifacts
and a promotion bundle that points at additive registry outputs.

Verification and determinism-critical recomputation live in RE2:
  cdel.v18_0.eudrs_u.verify_eudrs_u_promotion_v1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a script: `python orchestrator/rsi_eudrs_u_train_v1.py ...`.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_CDEL_ROOT = _REPO_ROOT / "CDEL-v2"
if _CDEL_ROOT.is_dir() and str(_CDEL_ROOT) not in sys.path:
    sys.path.insert(0, str(_CDEL_ROOT))

from cdel.v18_0.omega_common_v1 import fail, load_canon_dict  # noqa: E402

from orchestrator.common.eudrs_u_dmpl_phase4_producer_v1 import emit_dmpl_phase4_promotion_bundle_v1  # noqa: E402


_CAMPAIGN_ID = "rsi_eudrs_u_train_v1"


def _load_pack(path: Path) -> dict:
    payload = load_canon_dict(path)
    if not isinstance(payload, dict):
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
    emit_dmpl_phase4_promotion_bundle_v1(state_dir=state_dir, producer_kind="train")

    sys.stdout.write("OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
