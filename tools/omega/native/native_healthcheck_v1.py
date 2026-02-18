#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.native.native_router_v1 import healthcheck_vectors


def _canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def main() -> None:
    ap = argparse.ArgumentParser(prog="native_healthcheck_v1")
    ap.add_argument("--op_id", required=True)
    ap.add_argument("--binary_path", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    receipt = healthcheck_vectors(str(args.op_id), Path(args.binary_path))
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(_canon_bytes(receipt))
    print(json.dumps({"status": receipt["result"], "receipt_id": receipt["receipt_id"], "binary_sha256": receipt["binary_sha256"]}, separators=(",", ":")))


if __name__ == "__main__":
    main()

