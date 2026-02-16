#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from cdel.canon.json_canon_v1 import canon_bytes, loads, sha256_hex


def _hash_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _load_json(path: Path) -> dict[str, Any]:
    data = loads(path.read_bytes())
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _git_sha(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "UNKNOWN"


def _collect_receipts(run_dir: Path) -> list[dict[str, str]]:
    receipts: list[dict[str, str]] = []
    for path in sorted(run_dir.rglob("receipt.json")):
        receipts.append({"path": str(path.relative_to(run_dir)), "sha256": _hash_file(path)})
    return receipts


def main() -> None:
    parser = argparse.ArgumentParser(prog="ccai-x-mind-rsi-success-manifest")
    parser.add_argument("--rsi_dir", required=True)
    parser.add_argument("--candidate_tar", required=True)
    parser.add_argument("--ablation_matrix", required=True)
    parser.add_argument("--out_path", required=True)
    parser.add_argument("--baseline_receipts", default=None)
    args = parser.parse_args()

    rsi_dir = Path(args.rsi_dir)
    metrics = _load_json(rsi_dir / "rsi_metrics.json")
    learning_state = _load_json(rsi_dir / "learning_state.json")
    receipts = _collect_receipts(rsi_dir)

    repo_root = Path(__file__).resolve().parents[3]
    payload = {
        "format": "ccai_x_mind_rsi_success_manifest_v1",
        "schema_version": "1",
        "tool_versions": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "genesis_git_sha": _git_sha(repo_root / "Genesis"),
            "agi_system_git_sha": _git_sha(repo_root / "agi-system"),
            "cdel_git_sha": _git_sha(repo_root / "CDEL-v2"),
        },
        "candidate_tar_sha256": _hash_file(Path(args.candidate_tar)),
        "rsi_metrics": metrics,
        "learning_state": learning_state,
        "learning_state_sha256": _hash_file(rsi_dir / "learning_state.json"),
        "receipt_hashes": receipts,
        "ablation_matrix_sha256": _hash_file(Path(args.ablation_matrix)),
    }
    if args.baseline_receipts:
        baseline_path = Path(args.baseline_receipts)
        if baseline_path.is_file():
            payload["baseline_receipts"] = _load_json(baseline_path).get("receipts", [])

    out_path = Path(args.out_path)
    out_path.write_bytes(canon_bytes(payload))


if __name__ == "__main__":
    main()
