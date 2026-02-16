#!/usr/bin/env python3
"""Print failure witness byte totals and MDL totals from a CDEL candidate directory."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: mdl_failure_witness_summary_v1_1.py <cdel_candidate_dir>", file=sys.stderr)
        return 2
    cand_dir = Path(sys.argv[1])
    idx_path = cand_dir / "failure_witness_index.json"
    ev_path = cand_dir / "evidence_report.json"
    if not idx_path.exists():
        print(f"missing {idx_path}", file=sys.stderr)
        return 1
    if not ev_path.exists():
        print(f"missing {ev_path}", file=sys.stderr)
        return 1
    index = _load_json(idx_path)
    evidence = _load_json(ev_path)
    base_mdl = evidence.get("base_metrics", {}).get("c_mdl", {})
    cand_mdl = evidence.get("candidate_metrics", {}).get("c_mdl", {})

    def _section(split: str, variant: str) -> int:
        return int(index.get(split, {}).get(variant, {}).get("total_bytes", 0))

    for split in ("dev", "heldout"):
        base_bytes = _section(split, "base")
        cand_bytes = _section(split, "candidate")
        base_bits = base_mdl.get(f"{split}_tml_bits")
        cand_bits = cand_mdl.get(f"{split}_tml_bits")
        print(f"{split} base failure_witness_bytes: {base_bytes}")
        print(f"{split} cand failure_witness_bytes: {cand_bytes}")
        print(f"{split} base total_bits: {base_bits}")
        print(f"{split} cand total_bits: {cand_bits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
