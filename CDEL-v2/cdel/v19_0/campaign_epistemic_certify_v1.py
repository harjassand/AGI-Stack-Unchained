"""Campaign wrapper for epistemic cert replay checks (R5)."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..v18_0.omega_common_v1 import fail
from .epistemic.verify_epistemic_certs_v1 import verify_certs_state


def run(*, out_dir: Path) -> dict:
    state_root = out_dir.resolve() / "daemon" / "rsi_epistemic_reduce_v1" / "state"
    if not state_root.exists() or not state_root.is_dir():
        fail("MISSING_STATE_INPUT")
    cert_dir = state_root / "epistemic" / "certs"
    ecac_rows = sorted(cert_dir.glob("sha256_*.epistemic_ecac_v1.json"), key=lambda p: p.as_posix())
    if len(ecac_rows) != 1:
        fail("MISSING_STATE_INPUT")
    import json

    ecac_payload = json.loads(ecac_rows[0].read_text(encoding="utf-8"))
    if not isinstance(ecac_payload, dict):
        fail("SCHEMA_FAIL")
    objective_profile_id = str(ecac_payload.get("objective_profile_id", "")).strip()
    if not objective_profile_id:
        fail("SCHEMA_FAIL")
    result = verify_certs_state(state_root, objective_profile_id=objective_profile_id)
    return {"status": "OK", **result}


def main() -> None:
    parser = argparse.ArgumentParser(prog="campaign_epistemic_certify_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    _ = Path(args.campaign_pack)
    result = run(out_dir=Path(args.out_dir))
    print(result.get("status", "OK"))


if __name__ == "__main__":
    main()
