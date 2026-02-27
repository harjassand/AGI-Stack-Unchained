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

from tools.mission_control.mission_pipeline_v1 import run_compile_execute_and_pack


def _load_request(raw: str) -> dict:
    candidate = Path(raw)
    try:
        is_file = candidate.exists() and candidate.is_file()
    except OSError:
        is_file = False
    if is_file:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    else:
        payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("MISSION_REQUEST_INVALID")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Mission Control e2e harness v1")
    parser.add_argument("--mission_request", required=True, help="JSON string or path")
    parser.add_argument("--max_ticks_u64", type=int, default=128)
    parser.add_argument("--dev_mode", type=int, default=1)
    args = parser.parse_args()

    mission_request = _load_request(args.mission_request)
    result = run_compile_execute_and_pack(
        mission_request,
        max_ticks_u64=max(1, int(args.max_ticks_u64)),
        dev_mode=bool(int(args.dev_mode)),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
