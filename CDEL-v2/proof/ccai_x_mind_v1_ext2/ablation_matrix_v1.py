#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from cdel.canon.json_canon_v1 import canon_bytes, loads, sha256_hex


def _load_json(path: Path) -> dict[str, Any]:
    data = loads(path.read_bytes())
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _hash_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _run_info(run_dir: Path) -> dict[str, Any]:
    eval_path = run_dir / "eval_result.json"
    eval_obj = _load_json(eval_path)
    receipt_path = run_dir / "receipt.json"
    return {
        "status": str(eval_obj.get("status", "")),
        "fail_code": str(eval_obj.get("fail_reason", {}).get("code", "")),
        "eval_result_sha256": _hash_file(eval_path),
        "receipt_present": receipt_path.exists(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="ccai-x-mind-ablation-matrix")
    parser.add_argument("--baseline_dir", required=True)
    parser.add_argument("--ablations_root", required=True)
    parser.add_argument("--expected_map", required=True)
    parser.add_argument("--out_path", required=True)
    args = parser.parse_args()

    baseline = _run_info(Path(args.baseline_dir))
    expected = _load_json(Path(args.expected_map))
    ablations: dict[str, Any] = {}
    for key, code in expected.items():
        run_dir = Path(args.ablations_root) / key
        info = _run_info(run_dir)
        info["expected_fail_code"] = code
        ablations[key] = info

    payload = {
        "format": "ccai_x_mind_ablation_matrix_v1",
        "schema_version": "1",
        "baseline": baseline,
        "ablations": ablations,
    }
    out_path = Path(args.out_path)
    out_path.write_bytes(canon_bytes(payload))


if __name__ == "__main__":
    main()
