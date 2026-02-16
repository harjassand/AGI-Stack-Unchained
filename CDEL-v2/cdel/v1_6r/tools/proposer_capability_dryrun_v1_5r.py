"""Dev-only proposer capability dryrun for v1.5r."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from cdel.v1_5r.canon import hash_json, write_canon_json
from cdel.v1_5r.sr_cegar.witness import build_failure_witness


def _canon_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extension_root", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--python", default="python3")
    args = parser.parse_args()

    extension_root = Path(args.extension_root)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    witness_dir = out_dir / "witnesses"
    witness_dir.mkdir(parents=True, exist_ok=True)
    witness = build_failure_witness(
        epoch_id="dryrun",
        subject="candidate",
        candidate_id="dryrun_candidate",
        family_id="sha256:" + "0" * 64,
        theta={},
        inst_hash="sha256:" + "1" * 64,
        failure_kind="GOAL_FAIL",
        trace_hashes=["sha256:" + "2" * 64],
        shrink_proof_ref=None,
    )
    witness_hash = hash_json(witness)
    write_canon_json(witness_dir / f"{witness_hash.split(':', 1)[1]}.json", witness)
    witness_path = out_dir / "failure_witness_index_v1.json"
    witness_index = {
        "schema": "failure_witness_index_v1",
        "schema_version": 1,
        "witnesses": [witness_hash],
    }
    write_canon_json(witness_path, witness_index)

    proposals_dir = out_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(extension_root / "caoe_v1")

    cmd = [
        args.python,
        "-m",
        "v1_5r.cli",
        "propose-families",
        "--witness_index",
        str(witness_path),
        "--out_dir",
        str(proposals_dir),
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "proposer dryrun failed")

    proposals = list(proposals_dir.glob("*.json"))
    if not proposals:
        raise SystemExit("proposer dryrun produced no family proposals")


if __name__ == "__main__":
    main()
