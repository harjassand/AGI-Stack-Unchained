#!/usr/bin/env python3
"""Verify failure_witness_index.json integrity."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha_and_bytes(path: Path) -> tuple[str, int]:
    data = _load_json(path)
    payload = _canonical_json_bytes(data)
    return _sha256_hex(payload), len(payload)


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if not args:
        print("usage: verify_failure_witness_index_v1_1.py <candidate_dir|failure_witness_index.json> [--out report.json]", file=sys.stderr)
        return 2
    target = Path(args[0])
    out_path: Path | None = None
    if "--out" in args:
        idx = args.index("--out")
        try:
            out_path = Path(args[idx + 1])
        except IndexError:
            print("--out requires a path", file=sys.stderr)
            return 2
    if target.is_dir():
        index_path = target / "failure_witness_index.json"
        base_dir = target
    else:
        index_path = target
        base_dir = target.parent
    if not index_path.exists():
        print("failure_witness_index.json not found", file=sys.stderr)
        return 1
    index = _load_json(index_path)
    errors: list[str] = []

    def _check_split(split: str, variant: str) -> None:
        entry = index.get(split, {}).get(variant, {})
        regimes_failed = entry.get("regimes_failed") or []
        files = entry.get("files") or {}
        total_bytes = int(entry.get("total_bytes", 0))
        recomputed_total = 0
        for regime_id in regimes_failed:
            pack = files.get(regime_id)
            if not isinstance(pack, dict):
                errors.append(f"missing pack for {split}/{variant}/{regime_id}")
                continue
            witness_dir = base_dir / "failure_witness" / split / variant / str(regime_id)
            ep = witness_dir / "episode_spec.json"
            ag = witness_dir / "agent_outputs.json"
            sc = witness_dir / "scorer_inputs.json"
            pack_total = 0
            for name, path in (("episode_spec", ep), ("agent_outputs", ag), ("scorer_inputs", sc)):
                if not path.exists():
                    errors.append(f"missing {name} for {split}/{variant}/{regime_id}")
                    continue
                sha, size = _canonical_sha_and_bytes(path)
                expected_sha = pack.get(f"{name}_sha256")
                if expected_sha != sha:
                    errors.append(f"sha mismatch {split}/{variant}/{regime_id}/{name}")
                recomputed_total += size
                pack_total += size
            expected_bytes = pack.get("bytes")
            if expected_bytes is None:
                errors.append(f"missing bytes field for {split}/{variant}/{regime_id}")
            else:
                if int(expected_bytes) != int(pack_total):
                    errors.append(f"bytes mismatch {split}/{variant}/{regime_id}")
        if recomputed_total != total_bytes:
            errors.append(f"total_bytes mismatch {split}/{variant}")

    for split in ("dev", "heldout"):
        for variant in ("base", "candidate"):
            _check_split(split, variant)

    ok = not errors
    report = {
        "format": "caoe_failure_witness_consistency_report_v1_1",
        "schema_version": 1,
        "ok": ok,
        "errors": errors,
        "index_path": str(index_path),
    }
    if out_path is None:
        out_path = base_dir / "failure_witness_consistency_report.json"
    out_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")
    sha = _sha256_hex(out_path.read_bytes())
    (out_path.parent / (out_path.stem + ".sha256")).write_text(sha + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
