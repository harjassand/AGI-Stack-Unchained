#!/usr/bin/env python3
"""Deterministic polymath refinery proposer (v1)."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import write_canon_json, write_jsonl_line
from cdel.v18_0.campaign_polymath_conquer_domain_v1 import (
    _majority_predictions,
    _metric_q32,
    _search_best_config,
    _split_train_val,
    _target_binary,
)
from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict, validate_schema
from tools.polymath.polymath_dataset_fetch_v1 import load_blob_bytes

_PROPOSER_SUMMARY_SCHEMA_VERSION = "OMEGA_POLYMATH_REFINERY_PROPOSER_SUMMARY_v1"
_DEFAULT_SUMMARY_BASENAME = "OMEGA_POLYMATH_REFINERY_PROPOSER_SUMMARY_v1.json"
_SKIP_REASON_ORDER = (
    "REGISTRY_NOT_ACTIVE",
    "NOT_READY_FOR_CONQUER",
    "CONQUERED_ALREADY",
    "DOMAIN_PACK_MISSING",
    "DOMAIN_PACK_SCHEMA_FAIL",
    "MISSING_STORE_BLOBS",
    "TASKS_EMPTY",
    "SPLIT_MISSING",
    "TRAIN_SHA_MISSING",
    "TEST_SHA_MISSING",
    "POLICY_BLOCKED",
    "SIZE_BLOCKED",
    "INTERNAL_ERROR",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _load_registry_rows(path: Path) -> list[dict[str, Any]]:
    payload = load_canon_dict(path)
    validate_schema(payload, "polymath_domain_registry_v1")
    rows = payload.get("domains")
    if not isinstance(rows, list):
        raise RuntimeError("registry domains must be list")
    out = [row for row in rows if isinstance(row, dict)]
    out.sort(key=lambda row: str(row.get("domain_id", "")))
    return out


def _default_summary_path() -> Path:
    return (Path.cwd() / _DEFAULT_SUMMARY_BASENAME).resolve()


def _blob_path(store_root: Path, sha256: str) -> Path:
    if not isinstance(sha256, str) or not sha256.startswith("sha256:"):
        raise RuntimeError("invalid sha256")
    digest = sha256.split(":", 1)[1].strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise RuntimeError("invalid sha256")
    return store_root / "blobs" / "sha256" / digest


def _required_sha256s(*, domain_pack: dict[str, Any], train_sha256: str, test_sha256: str) -> list[str]:
    out = {str(train_sha256), str(test_sha256)}
    dataset_artifacts = domain_pack.get("dataset_artifacts")
    if isinstance(dataset_artifacts, list):
        for row in dataset_artifacts:
            if not isinstance(row, dict):
                continue
            value = str(row.get("sha256", "")).strip()
            if value.startswith("sha256:"):
                out.add(value)
    return sorted(out)


def _missing_sha256s(*, store_root: Path, required_sha256s: list[str]) -> list[str]:
    missing: list[str] = []
    for sha256 in required_sha256s:
        try:
            blob = _blob_path(store_root, sha256)
        except Exception:  # noqa: BLE001
            missing.append(sha256)
            continue
        if not blob.exists() or not blob.is_file():
            missing.append(sha256)
    return sorted(missing)


def _empty_skip_reason_counts() -> dict[str, int]:
    return {reason: 0 for reason in _SKIP_REASON_ORDER}


def _summary_base(
    *,
    store_root: Path,
    registry_path: Path,
    max_domains: int,
    workers: int,
) -> dict[str, Any]:
    return {
        "schema_version": _PROPOSER_SUMMARY_SCHEMA_VERSION,
        "created_at_utc": _utc_now_iso(),
        "store_root": store_root.as_posix(),
        "registry_path": registry_path.as_posix(),
        "max_domains_u64": int(max(0, int(max_domains))),
        "workers_u64": int(max(1, int(workers))),
        "domains_seen_u64": 0,
        "domains_eligible_u64": 0,
        "proposals_generated_u64": 0,
        "domains_skipped_by_reason": _empty_skip_reason_counts(),
        "skip_samples": [],
        "errors": [],
    }


def _write_summary(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")


def _short_exc(exc: Exception) -> str:
    detail = str(exc).strip() or exc.__class__.__name__
    if len(detail) > 512:
        return detail[:509] + "..."
    return detail


def _skip_row(*, domain_id: str, reason: str, detail: str) -> dict[str, str]:
    return {
        "domain_id": str(domain_id),
        "reason": str(reason),
        "detail": str(detail),
    }


def _error_row(*, domain_id: str, detail: str) -> dict[str, str]:
    return {
        "domain_id": str(domain_id),
        "error_code": "EXCEPTION",
        "detail": str(detail),
    }


def _build_proposal(
    *,
    store_root: Path,
    domain_index: int,
    domain_id: str,
    train_sha256: str,
    metric_id: str,
) -> dict[str, Any]:
    train_rows_raw = load_blob_bytes(sha256=train_sha256, store_root=store_root)
    train_rows_payload = json.loads(train_rows_raw.decode("utf-8"))
    if not isinstance(train_rows_payload, list):
        raise RuntimeError("train rows payload must be list")
    train_rows = [row for row in train_rows_payload if isinstance(row, dict)]
    if not train_rows:
        raise RuntimeError("train rows payload is empty")

    best = _search_best_config(train_rows=train_rows, metric_id=metric_id)
    _, val_split = _split_train_val(train_rows)
    val_targets = [_target_binary(row) for row in val_split]
    baseline_preds = _majority_predictions(val_targets)
    baseline_val_metric_q32 = int(_metric_q32(metric_id, baseline_preds, val_targets))

    payload_no_id = {
        "schema_version": "polymath_refinery_proposal_v1",
        "domain_id": domain_id,
        "train_sha256": train_sha256,
        "config_id": str(best["config_id"]),
        "config": dict(best["config"]),
        "val_metric_q32": int(best["val_metric_q32"]),
        "model_complexity_u64": int(best["model_complexity_u64"]),
        "baseline_val_metric_q32": int(baseline_val_metric_q32),
        "expected_val_delta_q32": int(int(best["val_metric_q32"]) - int(baseline_val_metric_q32)),
    }
    proposal_id = canon_hash_obj(payload_no_id)
    proposal_payload = dict(payload_no_id)
    proposal_payload["proposal_id"] = proposal_id
    return {
        "domain_index": int(domain_index),
        "domain_id": domain_id,
        "train_sha256": train_sha256,
        "proposal_id": proposal_id,
        "proposal_payload": proposal_payload,
        "expected_val_delta_q32": int(payload_no_id["expected_val_delta_q32"]),
        "val_metric_q32": int(payload_no_id["val_metric_q32"]),
    }


def _evaluate_domain(
    *,
    repo_root: Path,
    store_root: Path,
    domain_index: int,
    row: dict[str, Any],
) -> dict[str, Any]:
    domain_id = str(row.get("domain_id", "")).strip()
    status = str(row.get("status", "")).strip()
    ready_reason = str(row.get("ready_for_conquer_reason", "")).strip()
    if status == "BLOCKED_POLICY" or ready_reason == "BLOCKED_POLICY":
        return {"kind": "skip", "skip": _skip_row(domain_id=domain_id, reason="POLICY_BLOCKED", detail="blocked by policy")}
    if status == "BLOCKED_SIZE" or ready_reason == "BLOCKED_SIZE":
        return {"kind": "skip", "skip": _skip_row(domain_id=domain_id, reason="SIZE_BLOCKED", detail="blocked by size")}
    if status != "ACTIVE":
        return {
            "kind": "skip",
            "skip": _skip_row(
                domain_id=domain_id,
                reason="REGISTRY_NOT_ACTIVE",
                detail=f"status={status or '<empty>'}",
            ),
        }
    if bool(row.get("conquered_b", False)):
        return {
            "kind": "skip",
            "skip": _skip_row(domain_id=domain_id, reason="CONQUERED_ALREADY", detail="conquered_b=true"),
        }
    if not bool(row.get("ready_for_conquer", False)):
        return {
            "kind": "skip",
            "skip": _skip_row(
                domain_id=domain_id,
                reason="NOT_READY_FOR_CONQUER",
                detail=f"ready_for_conquer=false reason={ready_reason or '<empty>'}",
            ),
        }

    domain_pack_rel = str(row.get("domain_pack_rel", "")).strip()
    if not domain_pack_rel:
        return {
            "kind": "skip",
            "skip": _skip_row(domain_id=domain_id, reason="DOMAIN_PACK_MISSING", detail="domain_pack_rel missing"),
        }
    domain_pack_path = (repo_root / domain_pack_rel).resolve()
    if not domain_pack_path.exists() or not domain_pack_path.is_file():
        return {
            "kind": "skip",
            "skip": _skip_row(
                domain_id=domain_id,
                reason="DOMAIN_PACK_MISSING",
                detail=f"path_missing={domain_pack_rel}",
            ),
        }

    domain_pack = load_canon_dict(domain_pack_path)
    if str(domain_pack.get("schema_version", "")).strip() != "polymath_domain_pack_v1":
        return {
            "kind": "skip",
            "skip": _skip_row(
                domain_id=domain_id,
                reason="DOMAIN_PACK_SCHEMA_FAIL",
                detail="schema_version mismatch",
            ),
        }
    tasks = domain_pack.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return {"kind": "skip", "skip": _skip_row(domain_id=domain_id, reason="TASKS_EMPTY", detail="tasks empty")}
    task = tasks[0]
    if not isinstance(task, dict):
        return {
            "kind": "skip",
            "skip": _skip_row(
                domain_id=domain_id,
                reason="DOMAIN_PACK_SCHEMA_FAIL",
                detail="tasks[0] must be object",
            ),
        }
    split = task.get("split")
    if not isinstance(split, dict):
        return {
            "kind": "skip",
            "skip": _skip_row(domain_id=domain_id, reason="SPLIT_MISSING", detail="tasks[0].split missing"),
        }

    train_sha256 = str(split.get("train_sha256", "")).strip()
    test_sha256 = str(split.get("test_sha256", "")).strip()
    if not train_sha256:
        return {
            "kind": "skip",
            "skip": _skip_row(
                domain_id=domain_id,
                reason="TRAIN_SHA_MISSING",
                detail="tasks[0].split.train_sha256 missing",
            ),
        }
    if not test_sha256:
        return {
            "kind": "skip",
            "skip": _skip_row(
                domain_id=domain_id,
                reason="TEST_SHA_MISSING",
                detail="tasks[0].split.test_sha256 missing",
            ),
        }

    try:
        validate_schema(domain_pack, "polymath_domain_pack_v1")
    except Exception as exc:  # noqa: BLE001
        return {
            "kind": "skip",
            "skip": _skip_row(
                domain_id=domain_id,
                reason="DOMAIN_PACK_SCHEMA_FAIL",
                detail=_short_exc(exc),
            ),
        }

    required_sha = _required_sha256s(domain_pack=domain_pack, train_sha256=train_sha256, test_sha256=test_sha256)
    missing_sha = _missing_sha256s(store_root=store_root, required_sha256s=required_sha)
    if missing_sha:
        missing_preview = ";".join(missing_sha[:10])
        return {
            "kind": "skip",
            "skip": _skip_row(
                domain_id=domain_id,
                reason="MISSING_STORE_BLOBS",
                detail=f"missing_sha256s={missing_preview}",
            ),
        }

    metric_id = str(task.get("metric", "")).strip()
    if not metric_id:
        return {
            "kind": "skip",
            "skip": _skip_row(
                domain_id=domain_id,
                reason="DOMAIN_PACK_SCHEMA_FAIL",
                detail="tasks[0].metric missing",
            ),
        }

    proposal = _build_proposal(
        store_root=store_root,
        domain_index=domain_index,
        domain_id=domain_id,
        train_sha256=train_sha256,
        metric_id=metric_id,
    )
    return {"kind": "proposal", "proposal": proposal}


def run(
    *,
    registry_path: Path,
    store_root: Path,
    workers: int,
    max_domains: int,
    summary_path: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    resolved_repo_root = repo_root.resolve() if repo_root is not None else _REPO_ROOT
    resolved_store_root = store_root.expanduser().resolve()
    resolved_store_root.mkdir(parents=True, exist_ok=True)
    resolved_registry_path = registry_path.expanduser().resolve()
    resolved_summary_path = (
        summary_path.expanduser().resolve() if summary_path is not None else _default_summary_path()
    )

    workers_u64 = max(1, int(workers))
    summary = _summary_base(
        store_root=resolved_store_root,
        registry_path=resolved_registry_path,
        max_domains=max_domains,
        workers=workers_u64,
    )

    proposals_dir = resolved_store_root / "refinery" / "proposals"
    index_dir = resolved_store_root / "refinery" / "indexes"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / "domain_train_to_best.jsonl"
    if not index_path.exists():
        index_path.write_text("", encoding="utf-8")

    results: list[dict[str, Any]] = []
    skip_rows: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    try:
        domains = _load_registry_rows(resolved_registry_path)
        if int(max_domains) > 0:
            domains = domains[: int(max_domains)]
        summary["domains_seen_u64"] = int(len(domains))

        by_worker: dict[int, list[tuple[int, dict[str, Any]]]] = {idx: [] for idx in range(workers_u64)}
        for domain_index, row in enumerate(domains):
            by_worker[int(domain_index) % workers_u64].append((int(domain_index), row))

        def _run_bucket(bucket_rows: list[tuple[int, dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]]]:
            bucket_results: list[dict[str, Any]] = []
            bucket_skips: list[dict[str, str]] = []
            bucket_errors: list[dict[str, str]] = []
            for domain_index, row in bucket_rows:
                domain_id = str(row.get("domain_id", "")).strip()
                try:
                    evaluated = _evaluate_domain(
                        repo_root=resolved_repo_root,
                        store_root=resolved_store_root,
                        domain_index=domain_index,
                        row=row,
                    )
                    if str(evaluated.get("kind", "")) == "proposal":
                        proposal = evaluated.get("proposal")
                        if isinstance(proposal, dict):
                            bucket_results.append(proposal)
                        else:
                            bucket_skips.append(
                                _skip_row(
                                    domain_id=domain_id,
                                    reason="INTERNAL_ERROR",
                                    detail="proposal payload missing",
                                )
                            )
                            bucket_errors.append(_error_row(domain_id=domain_id, detail="proposal payload missing"))
                        continue
                    skip = evaluated.get("skip")
                    if isinstance(skip, dict):
                        bucket_skips.append(
                            _skip_row(
                                domain_id=str(skip.get("domain_id", "")),
                                reason=str(skip.get("reason", "")),
                                detail=str(skip.get("detail", "")),
                            )
                        )
                        continue
                    bucket_skips.append(
                        _skip_row(
                            domain_id=domain_id,
                            reason="INTERNAL_ERROR",
                            detail="invalid evaluation result",
                        )
                    )
                    bucket_errors.append(_error_row(domain_id=domain_id, detail="invalid evaluation result"))
                except Exception as exc:  # noqa: BLE001
                    detail = f"{exc.__class__.__name__}: {_short_exc(exc)}"
                    bucket_skips.append(_skip_row(domain_id=domain_id, reason="INTERNAL_ERROR", detail=detail))
                    bucket_errors.append(_error_row(domain_id=domain_id, detail=detail))
            return bucket_results, bucket_skips, bucket_errors

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers_u64) as pool:
            futs = [pool.submit(_run_bucket, by_worker[idx]) for idx in range(workers_u64)]
            for fut in futs:
                bucket_results, bucket_skips, bucket_errors = fut.result()
                results.extend(bucket_results)
                skip_rows.extend(bucket_skips)
                errors.extend(bucket_errors)

        results.sort(key=lambda row: int(row.get("domain_index", 0)))
        for row in results:
            proposal_id = str(row["proposal_id"])
            payload = dict(row["proposal_payload"])
            write_canon_json(
                proposals_dir / f"{proposal_id}.polymath_refinery_proposal_v1.json",
                payload,
            )
            write_jsonl_line(
                index_path,
                {
                    "schema_version": "polymath_refinery_domain_train_best_v1",
                    "domain_id": str(row["domain_id"]),
                    "train_sha256": str(row["train_sha256"]),
                    "proposal_id": proposal_id,
                    "val_metric_q32": int(row["val_metric_q32"]),
                },
            )

        reason_counts = _empty_skip_reason_counts()
        for row in skip_rows:
            reason = str(row.get("reason", "INTERNAL_ERROR"))
            if reason not in reason_counts:
                reason = "INTERNAL_ERROR"
            reason_counts[reason] = int(reason_counts.get(reason, 0)) + 1

        skip_rows_sorted = sorted(
            skip_rows,
            key=lambda row: (
                str(row.get("domain_id", "")),
                str(row.get("reason", "")),
                str(row.get("detail", "")),
            ),
        )
        errors_sorted = sorted(
            errors,
            key=lambda row: (
                str(row.get("domain_id", "")),
                str(row.get("error_code", "")),
                str(row.get("detail", "")),
            ),
        )

        summary["domains_eligible_u64"] = int(len(results))
        summary["proposals_generated_u64"] = int(len(results))
        summary["domains_skipped_by_reason"] = reason_counts
        summary["skip_samples"] = [
            {
                "domain_id": str(row.get("domain_id", "")),
                "reason": str(row.get("reason", "")),
                "detail": str(row.get("detail", "")),
            }
            for row in skip_rows_sorted[:10]
        ]
        summary["errors"] = [
            {
                "domain_id": str(row.get("domain_id", "")),
                "error_code": str(row.get("error_code", "EXCEPTION")),
                "detail": str(row.get("detail", "")),
            }
            for row in errors_sorted
        ]
    except Exception as exc:  # noqa: BLE001
        reason_counts = summary.get("domains_skipped_by_reason")
        if not isinstance(reason_counts, dict):
            reason_counts = _empty_skip_reason_counts()
        reason_counts["INTERNAL_ERROR"] = int(reason_counts.get("INTERNAL_ERROR", 0)) + 1
        summary["domains_skipped_by_reason"] = reason_counts
        summary["errors"] = list(summary.get("errors", [])) + [
            _error_row(domain_id="", detail=f"{exc.__class__.__name__}: {_short_exc(exc)}")
        ]
        _write_summary(resolved_summary_path, summary)
        raise

    _write_summary(resolved_summary_path, summary)
    return {
        "summary_path": resolved_summary_path,
        "summary": summary,
    }


def _write_fatal_summary(
    *,
    summary_path: Path,
    registry_path: Path,
    store_root: Path,
    workers: int,
    max_domains: int,
    exc: Exception,
) -> None:
    summary = _summary_base(
        store_root=store_root,
        registry_path=registry_path,
        max_domains=max_domains,
        workers=workers,
    )
    reason_counts = summary.get("domains_skipped_by_reason")
    if isinstance(reason_counts, dict):
        reason_counts["INTERNAL_ERROR"] = int(reason_counts.get("INTERNAL_ERROR", 0)) + 1
    summary["errors"] = [_error_row(domain_id="", detail=f"{exc.__class__.__name__}: {_short_exc(exc)}")]
    _write_summary(summary_path, summary)


def main() -> None:
    parser = argparse.ArgumentParser(prog="polymath_refinery_proposer_v1")
    parser.add_argument("--registry_path", required=True)
    parser.add_argument("--store_root", required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--max_domains", type=int, default=32)
    parser.add_argument("--summary_path", default="")
    args = parser.parse_args()

    resolved_registry_path = Path(args.registry_path).expanduser().resolve()
    resolved_store_root = Path(args.store_root).expanduser().resolve()
    workers = max(1, int(args.workers))
    max_domains = max(0, int(args.max_domains))
    resolved_summary_path = (
        Path(str(args.summary_path)).expanduser().resolve()
        if str(args.summary_path).strip()
        else _default_summary_path()
    )

    try:
        result = run(
            registry_path=resolved_registry_path,
            store_root=resolved_store_root,
            workers=workers,
            max_domains=max_domains,
            summary_path=resolved_summary_path,
        )
    except Exception as exc:  # noqa: BLE001
        if not resolved_summary_path.exists() or not resolved_summary_path.is_file():
            _write_fatal_summary(
                summary_path=resolved_summary_path,
                registry_path=resolved_registry_path,
                store_root=resolved_store_root,
                workers=workers,
                max_domains=max_domains,
                exc=exc,
            )
        print(resolved_summary_path.as_posix())
        raise SystemExit(2)
    print(Path(result["summary_path"]).as_posix())


if __name__ == "__main__":
    main()
