"""Minimal Omega subverifier for rsi_agi_orchestrator_llm_v1."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cdel.v1_7r.canon import load_canon_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_rsi_agi_orchestrator_llm_v1")
    parser.add_argument("--mode", required=True, choices=["full", "fast"])
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)
    if not state_dir.exists() or not state_dir.is_dir():
        sys.stdout.write("INVALID:MISSING_STATE_INPUT\n")
        return 1

    evidence = state_dir / "agi_orchestrator_llm_evidence_v1.json"
    if not evidence.exists() or not evidence.is_file():
        sys.stdout.write("INVALID:MISSING_EVIDENCE\n")
        return 1

    # Fail closed if the evidence isn't canonical JSON.
    _ = load_canon_json(evidence)
    sys.stdout.write("VALID\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

