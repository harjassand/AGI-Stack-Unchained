"""Persistent sealed evaluator worker for SAS-Science v13.0."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed
from .sas_science_dataset_v1 import load_dataset, load_manifest
from .sas_science_eval_v1 import compute_eval_report, compute_report_hash

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")


class SealedEvalWorkerError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise SealedEvalWorkerError(reason)


def _hash_json(payload: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(payload))


def _require_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        _fail(f"INVALID:{field}")
    return value


def _require_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"INVALID:{field}")
    return value


def _load_json_dict(path: Path) -> dict[str, Any]:
    obj = load_canon_json(path)
    if not isinstance(obj, dict):
        _fail("INVALID:SCHEMA_FAIL")
    return obj


class _WorkerCache:
    def __init__(self) -> None:
        self._dataset_cache: dict[tuple[str, str], tuple[dict[str, Any], Any]] = {}
        self._dataset_receipt_cache: dict[str, dict[str, Any]] = {}
        self._split_receipt_cache: dict[str, dict[str, Any]] = {}
        self._suitepack_cache: dict[str, dict[str, Any]] = {}
        self._perf_policy_cache: dict[str, dict[str, Any]] = {}
        self._ir_policy_cache: dict[str, dict[str, Any]] = {}

    def dataset(self, *, dataset_manifest_hash: str, dataset_csv_hash: str, dataset_manifest: Path, dataset_csv: Path) -> tuple[dict[str, Any], Any]:
        key = (dataset_manifest_hash, dataset_csv_hash)
        cached = self._dataset_cache.get(key)
        if cached is not None:
            return cached
        manifest = load_manifest(dataset_manifest)
        dataset = load_dataset(dataset_csv, manifest)
        out = (manifest, dataset)
        self._dataset_cache[key] = out
        return out

    def dataset_receipt(self, *, cache_key: str, path: Path) -> dict[str, Any]:
        cached = self._dataset_receipt_cache.get(cache_key)
        if cached is not None:
            return cached
        payload = _load_json_dict(path)
        self._dataset_receipt_cache[cache_key] = payload
        return payload

    def split_receipt(self, *, cache_key: str, path: Path) -> dict[str, Any]:
        cached = self._split_receipt_cache.get(cache_key)
        if cached is not None:
            return cached
        payload = _load_json_dict(path)
        self._split_receipt_cache[cache_key] = payload
        return payload

    def suitepack(self, *, cache_key: str, path: Path) -> dict[str, Any]:
        cached = self._suitepack_cache.get(cache_key)
        if cached is not None:
            return cached
        payload = _load_json_dict(path)
        self._suitepack_cache[cache_key] = payload
        return payload

    def perf_policy(self, *, cache_key: str, path: Path) -> dict[str, Any]:
        cached = self._perf_policy_cache.get(cache_key)
        if cached is not None:
            return cached
        payload = _load_json_dict(path)
        self._perf_policy_cache[cache_key] = payload
        return payload

    def ir_policy(self, *, cache_key: str, path: Path) -> dict[str, Any]:
        cached = self._ir_policy_cache.get(cache_key)
        if cached is not None:
            return cached
        payload = _load_json_dict(path)
        self._ir_policy_cache[cache_key] = payload
        return payload


def _parse_job(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SealedEvalWorkerError("INVALID:JOB_JSON") from exc
    if not isinstance(payload, dict):
        _fail("INVALID:JOB_SCHEMA")
    if payload.get("schema_version") != "sealed_science_eval_job_v1":
        _fail("INVALID:JOB_SCHEMA")

    cache_keys = payload.get("cache_keys")
    if not isinstance(cache_keys, dict):
        _fail("INVALID:JOB_SCHEMA")

    eval_kind = _require_str(payload.get("eval_kind"), field="eval_kind")
    if eval_kind not in ("DEV", "HELDOUT"):
        _fail("INVALID:eval_kind")

    lease_raw = payload.get("lease")
    lease: Path | None
    if lease_raw is None:
        lease = None
    elif isinstance(lease_raw, str) and lease_raw:
        lease = Path(lease_raw)
    else:
        _fail("INVALID:lease")
        return {}

    if eval_kind == "HELDOUT" and (lease is None or not lease.exists()):
        _fail("INVALID:lease")

    return {
        "schema_version": "sealed_science_eval_job_v1",
        "dataset_manifest": Path(_require_str(payload.get("dataset_manifest"), field="dataset_manifest")),
        "dataset_csv": Path(_require_str(payload.get("dataset_csv"), field="dataset_csv")),
        "dataset_receipt": Path(_require_str(payload.get("dataset_receipt"), field="dataset_receipt")),
        "split_receipt": Path(_require_str(payload.get("split_receipt"), field="split_receipt")),
        "theory_ir": Path(_require_str(payload.get("theory_ir"), field="theory_ir")),
        "fit_receipt": Path(_require_str(payload.get("fit_receipt"), field="fit_receipt")),
        "suitepack": Path(_require_str(payload.get("suitepack"), field="suitepack")),
        "perf_policy": Path(_require_str(payload.get("perf_policy"), field="perf_policy")),
        "ir_policy": Path(_require_str(payload.get("ir_policy"), field="ir_policy")),
        "eval_kind": eval_kind,
        "lease": lease,
        "cache_keys": {
            "dataset_manifest_hash": _require_sha256(
                cache_keys.get("dataset_manifest_hash"),
                field="cache_keys.dataset_manifest_hash",
            ),
            "dataset_csv_hash": _require_sha256(
                cache_keys.get("dataset_csv_hash"),
                field="cache_keys.dataset_csv_hash",
            ),
            "dataset_receipt_hash": _require_sha256(
                cache_keys.get("dataset_receipt_hash"),
                field="cache_keys.dataset_receipt_hash",
            ),
            "split_receipt_hash": _require_sha256(
                cache_keys.get("split_receipt_hash"),
                field="cache_keys.split_receipt_hash",
            ),
            "suitepack_hash": _require_sha256(
                cache_keys.get("suitepack_hash"),
                field="cache_keys.suitepack_hash",
            ),
            "perf_policy_hash": _require_sha256(
                cache_keys.get("perf_policy_hash"),
                field="cache_keys.perf_policy_hash",
            ),
            "ir_policy_hash": _require_sha256(
                cache_keys.get("ir_policy_hash"),
                field="cache_keys.ir_policy_hash",
            ),
        },
    }


def _run_job(job: dict[str, Any], *, cache: _WorkerCache) -> dict[str, Any]:
    cache_keys = dict(job["cache_keys"])

    _manifest, dataset = cache.dataset(
        dataset_manifest_hash=cache_keys["dataset_manifest_hash"],
        dataset_csv_hash=cache_keys["dataset_csv_hash"],
        dataset_manifest=Path(job["dataset_manifest"]),
        dataset_csv=Path(job["dataset_csv"]),
    )
    dataset_receipt = cache.dataset_receipt(
        cache_key=cache_keys["dataset_receipt_hash"],
        path=Path(job["dataset_receipt"]),
    )
    split_receipt = cache.split_receipt(
        cache_key=cache_keys["split_receipt_hash"],
        path=Path(job["split_receipt"]),
    )
    suitepack = cache.suitepack(
        cache_key=cache_keys["suitepack_hash"],
        path=Path(job["suitepack"]),
    )
    perf_policy = cache.perf_policy(
        cache_key=cache_keys["perf_policy_hash"],
        path=Path(job["perf_policy"]),
    )
    ir_policy = cache.ir_policy(
        cache_key=cache_keys["ir_policy_hash"],
        path=Path(job["ir_policy"]),
    )

    ir = _load_json_dict(Path(job["theory_ir"]))
    fit_receipt = _load_json_dict(Path(job["fit_receipt"]))

    eval_report = compute_eval_report(
        dataset=dataset,
        ir=ir,
        fit_receipt=fit_receipt,
        eval_kind=str(job["eval_kind"]),
        split_receipt=split_receipt,
    )
    eval_report_hash = compute_report_hash(eval_report)

    sealed_receipt = {
        "schema_version": "sealed_science_eval_receipt_v1",
        "receipt_id": "",
        "created_utc": "1970-01-01T00:00:00Z",
        "eval_kind": job["eval_kind"],
        "theory_id": ir.get("theory_id"),
        "fit_receipt_hash": fit_receipt.get("receipt_id", _hash_json(fit_receipt)),
        "dataset_receipt_hash": _hash_json(dataset_receipt),
        "split_receipt_hash": _hash_json(split_receipt),
        "suitepack_hash": _hash_json(suitepack),
        "perf_policy_hash": _hash_json(perf_policy),
        "ir_policy_hash": _hash_json(ir_policy),
        "eval_report_hash": eval_report_hash,
        "stdout_hash": sha256_prefixed(b""),
        "stderr_hash": sha256_prefixed(b""),
        "exit_code": 0,
        "network_used": False,
        "time_ms": 0,
        "memory_mb": 0,
    }
    sealed_receipt["receipt_id"] = _hash_json({k: v for k, v in sealed_receipt.items() if k != "receipt_id"})
    sealed_receipt_hash = sha256_prefixed(canon_bytes(sealed_receipt))
    work_cost_total = int(eval_report.get("workmeter", {}).get("work_cost_total", 0))

    return {
        "schema_version": "sealed_science_eval_result_v1",
        "eval_report": eval_report,
        "sealed_receipt": sealed_receipt,
        "eval_report_hash": eval_report_hash,
        "sealed_receipt_hash": sealed_receipt_hash,
        "work_cost_total": work_cost_total,
    }


def _worker_mode() -> None:
    cache = _WorkerCache()
    for raw_line in sys.stdin:
        raw = raw_line.strip()
        if not raw:
            continue
        job = _parse_job(raw)
        result = _run_job(job, cache=cache)
        sys.stdout.write(canon_bytes(result).decode("utf-8") + "\n")
        sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(prog="sealed_science_eval_worker_v1")
    parser.add_argument("--mode", required=True, choices=["worker"])
    args = parser.parse_args()
    try:
        if args.mode == "worker":
            _worker_mode()
        else:  # pragma: no cover
            raise SystemExit("unsupported mode")
    except Exception as exc:  # pragma: no cover - fail-closed worker boundary
        sys.stderr.write(f"sealed_science_eval_worker_v1_error:{exc}\n")
        sys.stderr.flush()
        raise SystemExit(2)


if __name__ == "__main__":
    main()
