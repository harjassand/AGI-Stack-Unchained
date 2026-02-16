#!/usr/bin/env python3
"""Dev-only proposer capability dry-run for v1_5r."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path


def _write_witness(path: Path) -> None:
    witness = {
        "schema": "failure_witness_v1",
        "schema_version": 1,
        "epoch_id": "epoch_dryrun",
        "subject": "base",
        "candidate_id": None,
        "family_id": "sha256:" + "0" * 64,
        "theta": {},
        "inst_hash": "sha256:" + "1" * 64,
        "failure_kind": "GOAL_FAIL",
        "trace_hashes": [],
        "shrink_proof_ref": None,
    }
    path.write_text(json.dumps(witness, sort_keys=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Proposer capability dry-run for v1_5r")
    parser.add_argument("--out-dir", required=True, help="output proposals directory")
    parser.add_argument("--proposer-cmd", required=True, help="command to invoke RE3 proposer")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    witness_path = out_dir / "failure_witness_v1.json"
    _write_witness(witness_path)

    cmd = shlex.split(args.proposer_cmd)
    cmd += ["--witness", str(witness_path), "--out-dir", str(out_dir)]
    subprocess.run(cmd, check=True)

    proposals = list(out_dir.glob("*.json"))
    if not proposals:
        raise SystemExit("no proposals produced by proposer")


if __name__ == "__main__":
    main()
