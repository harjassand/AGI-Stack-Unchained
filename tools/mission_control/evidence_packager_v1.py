from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from tools.mission_control.mission_pipeline_v1 import build_evidence_pack


def main() -> None:
    parser = argparse.ArgumentParser(description="Build mission_evidence_pack_v1 for a mission id.")
    parser.add_argument("--mission_id", required=True)
    args = parser.parse_args()

    pack, evidence_pack_id = build_evidence_pack(args.mission_id)
    out = {
        "ok_b": True,
        "mission_id": args.mission_id,
        "evidence_pack_id": evidence_pack_id,
        "evidence_pack": pack,
    }
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
