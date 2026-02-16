"""Fail-closed verifier for polymath scout campaign artifacts (v1)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from .omega_common_v1 import OmegaV18Error, canon_hash_obj, fail, hash_file_stream, load_canon_dict, load_jsonl, repo_root, validate_schema


def _resolve_state(path: Path) -> Path:
    root = path.resolve()
    candidates = [
        root / "daemon" / "rsi_polymath_scout_v1" / "state",
        root,
    ]
    for candidate in candidates:
        if (candidate / "reports").exists() and (candidate / "reports").is_dir():
            return candidate
    fail("SCHEMA_FAIL")
    return root


def _subrun_root(state_root: Path) -> Path:
    return state_root.parents[2]


def _resolve_store_roots(*, subrun_root: Path) -> list[Path]:
    out: list[Path] = []
    env_root_raw = str(os.environ.get("OMEGA_POLYMATH_STORE_ROOT", "")).strip()
    if env_root_raw:
        env_root = Path(env_root_raw).expanduser().resolve()
        if env_root.exists() and env_root.is_dir():
            out.append(env_root)
    else:
        repo_cache_root = (repo_root() / ".omega_cache" / "polymath" / "store").resolve()
        if repo_cache_root.exists() and repo_cache_root.is_dir():
            out.append(repo_cache_root)

    fallback = (subrun_root / "polymath" / "store").resolve()
    if fallback.exists() and fallback.is_dir():
        out.append(fallback)

    seen: set[str] = set()
    uniq: list[Path] = []
    for row in out:
        key = row.as_posix()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(row)
    if not uniq:
        fail("MISSING_STATE_INPUT")
    return uniq


def _receipt_hash_map(store_roots: list[Path]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    found_any = False
    for store_root in store_roots:
        receipts_dir = store_root / "receipts"
        if not receipts_dir.exists() or not receipts_dir.is_dir():
            continue
        found_any = True
        for path in sorted(receipts_dir.rglob("*.json"), key=lambda row: row.as_posix()):
            payload = load_canon_dict(path)
            validate_schema(payload, "polymath_fetch_receipt_v1")
            out[canon_hash_obj(payload)] = payload
    if not found_any:
        fail("MISSING_STATE_INPUT")
    return out


def _expected_blob_path(*, store_roots: list[Path], sha256: str) -> Path:
    if not isinstance(sha256, str) or not sha256.startswith("sha256:"):
        fail("SCHEMA_FAIL")
    digest = sha256.split(":", 1)[1]
    if len(digest) != 64:
        fail("SCHEMA_FAIL")
    for store_root in store_roots:
        candidate = store_root / "blobs" / "sha256" / digest
        if candidate.exists() and candidate.is_file():
            return candidate
    fail("MISSING_STATE_INPUT")
    return Path(".")


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        fail("MODE_UNSUPPORTED")
    state_root = _resolve_state(state_dir)
    subrun_root = _subrun_root(state_root)

    void_path = subrun_root / "polymath" / "registry" / "polymath_void_report_v1.jsonl"
    status_path = subrun_root / "polymath" / "registry" / "polymath_scout_status_v1.json"
    store_roots = _resolve_store_roots(subrun_root=subrun_root)

    if not void_path.exists() or not void_path.is_file():
        fail("MISSING_STATE_INPUT")
    if not status_path.exists() or not status_path.is_file():
        fail("MISSING_STATE_INPUT")

    status_payload = load_canon_dict(status_path)
    validate_schema(status_payload, "polymath_scout_status_v1")

    rows = load_jsonl(void_path)
    top_void_q32 = 0
    topics: set[str] = set()
    evidence_sha256s: set[str] = set()
    receipt_map = _receipt_hash_map(store_roots)

    for row in rows:
        validate_schema(row, "polymath_void_report_v1")
        topic_id = str(row.get("topic_id", "")).strip()
        if topic_id:
            topics.add(topic_id)
        void_obj = row.get("void_score_q32")
        if isinstance(void_obj, dict):
            top_void_q32 = max(top_void_q32, max(0, int(void_obj.get("q", 0))))

        source_evidence = row.get("source_evidence")
        if not isinstance(source_evidence, list):
            fail("SCHEMA_FAIL")
        for evidence in source_evidence:
            if not isinstance(evidence, dict):
                fail("SCHEMA_FAIL")
            receipt_sha = str(evidence.get("receipt_sha256", "")).strip()
            blob_sha = str(evidence.get("sha256", "")).strip()
            if receipt_sha not in receipt_map:
                fail("MISSING_STATE_INPUT")
            receipt_payload = receipt_map[receipt_sha]
            if str(receipt_payload.get("sha256", "")).strip() != blob_sha:
                fail("NONDETERMINISTIC")
            blob_path = _expected_blob_path(store_roots=store_roots, sha256=blob_sha)
            if not blob_path.exists() or not blob_path.is_file():
                fail("MISSING_STATE_INPUT")
            if hash_file_stream(blob_path) != blob_sha:
                fail("NONDETERMINISTIC")
            evidence_sha256s.add(blob_sha)

    expected_sources = sorted(evidence_sha256s)
    actual_sources = sorted({str(value).strip() for value in status_payload.get("sources_sha256s", []) if str(value).strip()})
    if expected_sources != actual_sources:
        fail("NONDETERMINISTIC")

    if int(status_payload.get("rows_written_u64", -1)) != int(len(rows)):
        fail("NONDETERMINISTIC")
    status_top_void = status_payload.get("top_void_score_q32")
    if not isinstance(status_top_void, dict):
        fail("SCHEMA_FAIL")
    if int(status_top_void.get("q", -1)) != int(top_void_q32):
        fail("NONDETERMINISTIC")
    if int(status_payload.get("topics_scanned_u64", -1)) != int(len(topics)):
        fail("NONDETERMINISTIC")

    scout_run_id = str(status_payload.get("scout_run_id", ""))
    no_id = dict(status_payload)
    no_id.pop("scout_run_id", None)
    if scout_run_id != canon_hash_obj(no_id):
        fail("NONDETERMINISTIC")

    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_rsi_polymath_scout_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        print(verify(Path(args.state_dir), mode=str(args.mode)))
    except OmegaV18Error as exc:
        msg = str(exc)
        if not msg.startswith("INVALID:"):
            msg = f"INVALID:{msg}"
        print(msg)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
