"""Campaign entrypoint for epistemic type-governance checks (R4)."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..v18_0.omega_common_v1 import fail
from .epistemic.verify_epistemic_type_governance_v1 import verify_type_governance_state



def run(*, out_dir: Path) -> dict:
    state_root = out_dir.resolve() / "daemon" / "rsi_epistemic_reduce_v1" / "state"
    if not state_root.exists() or not state_root.is_dir():
        fail("MISSING_STATE_INPUT")
    result = verify_type_governance_state(state_root)
    if str(result.get("outcome", "")) != "ACCEPT":
        fail("TYPE_GOVERNANCE_FAIL")
    return {"status": "OK", **result}



def main() -> None:
    parser = argparse.ArgumentParser(prog="campaign_epistemic_type_governance_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    _ = Path(args.campaign_pack)
    result = run(out_dir=Path(args.out_dir))
    print(result.get("status", "OK"))


if __name__ == "__main__":
    main()
