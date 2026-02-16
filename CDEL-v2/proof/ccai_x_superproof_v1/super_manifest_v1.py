#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

CDEL_ROOT = Path(__file__).resolve().parents[2]
if (CDEL_ROOT / "cdel").is_dir():
    sys.path.insert(0, str(CDEL_ROOT))

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


def _collect_receipts(root: Path) -> list[dict[str, str]]:
    receipts: list[dict[str, str]] = []
    for path in sorted(root.rglob("receipt.json")):
        receipts.append({"path": str(path.relative_to(root)), "sha256": _hash_file(path)})
    return receipts


def main() -> None:
    parser = argparse.ArgumentParser(prog="ccai-x-superproof-manifest")
    parser.add_argument("--out_path", required=True)
    parser.add_argument("--baseline_dir", required=True)
    parser.add_argument("--ext2_dir", required=True)
    parser.add_argument("--mind_v2_dir", required=True)
    parser.add_argument("--commands_json", required=True)
    parser.add_argument("--plan_ids_json", required=True)
    parser.add_argument("--verifier_paths_json", required=True)
    parser.add_argument("--mind_v2_rsi_dir", default=None)
    args = parser.parse_args()

    baseline_dir = Path(args.baseline_dir)
    ext2_dir = Path(args.ext2_dir)
    mind_v2_dir = Path(args.mind_v2_dir)
    mind_v2_rsi_dir = Path(args.mind_v2_rsi_dir) if args.mind_v2_rsi_dir else None

    commands = json.loads(Path(args.commands_json).read_text(encoding="utf-8"))
    plan_ids = json.loads(Path(args.plan_ids_json).read_text(encoding="utf-8"))
    verifier_paths = json.loads(Path(args.verifier_paths_json).read_text(encoding="utf-8"))

    repo_root = Path(__file__).resolve().parents[3]

    manifests = {
        "mind_v1_baseline": {
            "path": "mind_v1_baseline/proof_manifest_run1.json",
            "sha256": _hash_file(baseline_dir / "proof_manifest_run1.json"),
        },
        "mind_v1_ext2": {
            "path": "mind_v1_ext2/rsi_success_manifest.json",
            "sha256": _hash_file(ext2_dir / "rsi_success_manifest.json"),
        },
        "mind_v2_structure": {
            "path": "mind_v2/mind_v2_manifest_run1.json",
            "sha256": _hash_file(mind_v2_dir / "mind_v2_manifest_run1.json"),
        },
    }

    if mind_v2_rsi_dir is not None:
        manifests["mind_v2_rsi"] = {
            "path": "mind_v2_rsi/mind_v2_rsi_success_manifest.json",
            "sha256": _hash_file(mind_v2_rsi_dir / "mind_v2_rsi_success_manifest.json"),
        }

    receipt_hashes = {
        "mind_v1_baseline": _collect_receipts(baseline_dir),
        "mind_v1_ext2": _collect_receipts(ext2_dir),
        "mind_v2_structure": _collect_receipts(mind_v2_dir),
    }
    if mind_v2_rsi_dir is not None:
        receipt_hashes["mind_v2_rsi"] = _collect_receipts(mind_v2_rsi_dir)

    verifier_hashes = {name: _hash_file(Path(path)) for name, path in verifier_paths.items()}

    payload: dict[str, Any] = {
        "format": "ccai_x_superproof_manifest_v1",
        "schema_version": "1",
        "tool_versions": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "genesis_git_sha": _git_sha(repo_root / "Genesis"),
            "agi_system_git_sha": _git_sha(repo_root / "agi-system"),
            "cdel_git_sha": _git_sha(repo_root / "CDEL-v2"),
        },
        "commands": commands,
        "plan_ids": plan_ids,
        "manifests": manifests,
        "receipt_hashes": receipt_hashes,
        "verifier_paths": verifier_paths,
        "verifier_sha256": verifier_hashes,
    }

    baseline_receipts_path = ext2_dir / "baseline_mind_v1" / "baseline_receipts.json"
    if baseline_receipts_path.is_file():
        payload["baseline_receipts_ext2"] = {
            "path": "mind_v1_ext2/baseline_mind_v1/baseline_receipts.json",
            "sha256": _hash_file(baseline_receipts_path),
        }

    non_regression_path = mind_v2_dir / "non_regression_receipts.json"
    if non_regression_path.is_file():
        payload["baseline_receipts_mind_v2"] = {
            "path": "mind_v2/non_regression_receipts.json",
            "sha256": _hash_file(non_regression_path),
        }

    out_path = Path(args.out_path)
    out_path.write_bytes(canon_bytes(payload))


if __name__ == "__main__":
    main()
