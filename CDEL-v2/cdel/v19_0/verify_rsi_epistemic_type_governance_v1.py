"""Verifier wrapper for epistemic type-governance campaign outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..v18_0.omega_common_v1 import OmegaV18Error, fail
from .epistemic.verify_epistemic_type_governance_v1 import verify_type_governance_state



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
    result = verify_type_governance_state(state_root)
    if str(result.get("outcome", "")) != "ACCEPT":
        fail("TYPE_GOVERNANCE_FAIL")
    return "VALID"



def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_epistemic_type_governance_v1")
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
