"""Verifier wrapper for epistemic cert replay checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..v18_0.omega_common_v1 import OmegaV18Error, fail
from .epistemic.verify_epistemic_certs_v1 import verify_certs_state


def _resolve_state(path: Path) -> Path:
    root = path.resolve()
    candidate = root / "daemon" / "rsi_epistemic_reduce_v1" / "state"
    if candidate.exists() and candidate.is_dir():
        return candidate
    if (root / "epistemic").is_dir():
        return root
    fail("SCHEMA_FAIL")
    return root


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        fail("MODE_UNSUPPORTED")
    state_root = _resolve_state(state_dir)
    cert_dir = state_root / "epistemic" / "certs"
    ecac_rows = sorted(cert_dir.glob("sha256_*.epistemic_ecac_v1.json"), key=lambda p: p.as_posix())
    if len(ecac_rows) != 1:
        fail("MISSING_STATE_INPUT")
    ecac_payload = json.loads(ecac_rows[0].read_text(encoding="utf-8"))
    if not isinstance(ecac_payload, dict):
        fail("SCHEMA_FAIL")
    objective_profile_id = str(ecac_payload.get("objective_profile_id", "")).strip()
    if not objective_profile_id:
        fail("SCHEMA_FAIL")
    verify_certs_state(state_root, objective_profile_id=objective_profile_id)
    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_epistemic_certify_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()
    try:
        print(verify(Path(args.state_dir), mode=str(args.mode)))
    except OmegaV18Error as exc:
        text = str(exc)
        if not text.startswith("INVALID:"):
            text = f"INVALID:{text}"
        print(text)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
