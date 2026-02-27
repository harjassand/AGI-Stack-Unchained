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

from tools.mission_control.mission_pipeline_v1 import replay_verify_evidence_pack


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay-verify mission evidence pack.")
    parser.add_argument("--evidence_pack_id", required=True)
    args = parser.parse_args()

    result = replay_verify_evidence_pack(args.evidence_pack_id)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
