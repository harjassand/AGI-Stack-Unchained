"""Sealed evaluator entrypoint for SAS-Science v13.0."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from .sas_science_dataset_v1 import load_manifest, load_dataset
from .sas_science_eval_v1 import compute_eval_report, compute_report_hash


def _hash_json(payload: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(payload))


def main() -> None:
    parser = argparse.ArgumentParser(prog="sealed_science_eval_v1")
    parser.add_argument("--dataset_manifest", required=True)
    parser.add_argument("--dataset_csv", required=True)
    parser.add_argument("--dataset_receipt", required=True)
    parser.add_argument("--split_receipt", required=True)
    parser.add_argument("--theory_ir", required=True)
    parser.add_argument("--fit_receipt", required=True)
    parser.add_argument("--suitepack", required=True)
    parser.add_argument("--perf_policy", required=True)
    parser.add_argument("--ir_policy", required=True)
    parser.add_argument("--eval_kind", required=True, choices=["DEV", "HELDOUT"])
    parser.add_argument("--out_eval", required=True)
    parser.add_argument("--out_sealed", required=True)
    parser.add_argument("--lease", required=False)
    args = parser.parse_args()

    # Deterministic timing metadata for reproducible receipts.
    start = time.monotonic()

    if args.eval_kind == "HELDOUT":
        if not args.lease or not Path(args.lease).exists():
            raise SystemExit("missing lease")

    manifest = load_manifest(Path(args.dataset_manifest))
    dataset = load_dataset(Path(args.dataset_csv), manifest)

    dataset_receipt = load_canon_json(Path(args.dataset_receipt))
    split_receipt = load_canon_json(Path(args.split_receipt))
    ir = load_canon_json(Path(args.theory_ir))
    fit_receipt = load_canon_json(Path(args.fit_receipt))
    suitepack = load_canon_json(Path(args.suitepack))
    perf_policy = load_canon_json(Path(args.perf_policy))
    ir_policy = load_canon_json(Path(args.ir_policy))

    eval_report = compute_eval_report(
        dataset=dataset,
        ir=ir,
        fit_receipt=fit_receipt,
        eval_kind=args.eval_kind,
        split_receipt=split_receipt,
    )

    out_eval_path = Path(args.out_eval)
    write_canon_json(out_eval_path, eval_report)

    eval_hash = compute_report_hash(eval_report)
    receipt = {
        "schema_version": "sealed_science_eval_receipt_v1",
        "receipt_id": "",
        "created_utc": "1970-01-01T00:00:00Z",
        "eval_kind": args.eval_kind,
        "theory_id": ir.get("theory_id"),
        "fit_receipt_hash": fit_receipt.get("receipt_id", _hash_json(fit_receipt)),
        "dataset_receipt_hash": _hash_json(dataset_receipt),
        "split_receipt_hash": _hash_json(split_receipt),
        "suitepack_hash": _hash_json(suitepack),
        "perf_policy_hash": _hash_json(perf_policy),
        "ir_policy_hash": _hash_json(ir_policy),
        "eval_report_hash": eval_hash,
        "stdout_hash": sha256_prefixed(b""),
        "stderr_hash": sha256_prefixed(b""),
        "exit_code": 0,
        "network_used": False,
        "time_ms": 0,
        "memory_mb": 0,
    }
    receipt["receipt_id"] = _hash_json({k: v for k, v in receipt.items() if k != "receipt_id"})

    out_sealed_path = Path(args.out_sealed)
    write_canon_json(out_sealed_path, receipt)


if __name__ == "__main__":
    main()
