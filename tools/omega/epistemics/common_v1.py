"""Common helpers for RE0 epistemic sidecar tools."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator


_SHA256_RE = "sha256:"


class EpistemicError(RuntimeError):
    """Fail-closed error for epistemic sidecar operations."""


def fail(reason: str) -> None:
    raise EpistemicError(reason)


def canon_bytes(payload: Any) -> bytes:
    try:
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except Exception as exc:  # noqa: BLE001
        raise EpistemicError("CANON_FAIL") from exc
    return text.encode("utf-8")


def canon_hash_obj(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canon_bytes(payload)).hexdigest()


def hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def deterministic_nonce_u64(*, source_uri: str, raw_blob_id: str, fetch_contract_id: str) -> int:
    blob = (
        str(source_uri).encode("utf-8")
        + b"\x00"
        + str(raw_blob_id).encode("utf-8")
        + b"\x00"
        + str(fetch_contract_id).encode("utf-8")
    )
    digest = hashlib.sha256(blob).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def ensure_sha256(value: Any) -> str:
    text = str(value).strip()
    if len(text) != 71 or not text.startswith(_SHA256_RE):
        fail("SCHEMA_FAIL")
    digest = text.split(":", 1)[1]
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        fail("SCHEMA_FAIL")
    return text


def load_canon_dict(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise EpistemicError("SCHEMA_FAIL") from exc
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    if canon_bytes(payload) != path.read_bytes().rstrip(b"\n"):
        fail("NONDETERMINISTIC")
    return payload


def fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        fsync_dir(path.parent)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def atomic_write_canon_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_bytes(path, canon_bytes(payload) + b"\n")


def append_jsonl_line_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = canon_bytes(payload) + b"\n"
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp)
    try:
        existing = b""
        if path.exists():
            existing = path.read_bytes()
        with os.fdopen(fd, "wb") as handle:
            if existing:
                handle.write(existing)
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        fsync_dir(path.parent)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception as exc:  # noqa: BLE001
            raise EpistemicError("SCHEMA_FAIL") from exc
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        if canon_bytes(row) != line.encode("utf-8"):
            fail("NONDETERMINISTIC")
        rows.append(row)
    return rows


def row_hash_without_row_hash(row: dict[str, Any]) -> str:
    no_hash = dict(row)
    no_hash.pop("row_hash", None)
    return canon_hash_obj(no_hash)


def verify_index_chain(rows: list[dict[str, Any]]) -> None:
    prev: str | None = None
    for row in rows:
        row_hash = ensure_sha256(row.get("row_hash"))
        prev_row_hash = row.get("prev_row_hash")
        if prev is None:
            if prev_row_hash is not None:
                fail("INDEX_CHAIN_MISMATCH")
        else:
            if ensure_sha256(prev_row_hash) != prev:
                fail("INDEX_CHAIN_MISMATCH")
        if row_hash_without_row_hash(row) != row_hash:
            fail("INDEX_CHAIN_MISMATCH")
        prev = row_hash


def append_index_row(index_path: Path, row: dict[str, Any]) -> dict[str, Any]:
    rows = load_jsonl(index_path)
    verify_index_chain(rows)
    prev_hash = rows[-1]["row_hash"] if rows else None
    out = dict(row)
    out["prev_row_hash"] = prev_hash
    out["row_hash"] = row_hash_without_row_hash(out)
    append_jsonl_line_atomic(index_path, out)
    return out


def fsync_tree_files(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        if path.is_symlink():
            continue
        if path.is_file():
            fsync_file(path)


@contextlib.contextmanager
def file_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = [
    "EpistemicError",
    "append_index_row",
    "atomic_write_bytes",
    "atomic_write_canon_json",
    "canon_bytes",
    "canon_hash_obj",
    "deterministic_nonce_u64",
    "ensure_sha256",
    "fail",
    "file_lock",
    "fsync_dir",
    "fsync_tree_files",
    "hash_file",
    "hash_bytes",
    "load_canon_dict",
    "load_jsonl",
    "row_hash_without_row_hash",
    "verify_index_chain",
]
