"""Deterministic usable-capsule index helpers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ..common_v1 import canon_hash_obj, ensure_sha256, fail, validate_schema


def _index_path(state_root: Path) -> Path:
    return state_root / "epistemic" / "usable_capsules" / "index.jsonl"


def _canon_line(row: dict[str, Any]) -> str:
    try:
        return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    return ""


def _validate_row(row: dict[str, Any]) -> None:
    validate_schema(row, "epistemic_usable_capsule_index_row_v1")
    observed_hash = canon_hash_obj({k: v for k, v in row.items() if k != "row_hash"})
    if ensure_sha256(row.get("row_hash"), reason="SCHEMA_FAIL") != observed_hash:
        fail("NONDETERMINISTIC")
    _ = ensure_sha256(row.get("capsule_id"), reason="SCHEMA_FAIL")
    _ = ensure_sha256(row.get("distillate_graph_id"), reason="SCHEMA_FAIL")
    _ = ensure_sha256(row.get("cert_profile_id"), reason="SCHEMA_FAIL")
    prev = row.get("prev_row_hash")
    if prev is not None:
        _ = ensure_sha256(prev, reason="SCHEMA_FAIL")


def load_rows(state_root: Path) -> list[dict[str, Any]]:
    path = _index_path(state_root.resolve())
    if not path.exists() or not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            fail("SCHEMA_FAIL")
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        if _canon_line(row) != line:
            fail("NONDETERMINISTIC")
        _validate_row(row)
        rows.append(row)
    prev_hash: str | None = None
    for row in rows:
        if row.get("prev_row_hash") != prev_hash:
            fail("NONDETERMINISTIC")
        prev_hash = str(row.get("row_hash"))
    return rows


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(_canon_line(row) for row in rows).encode("utf-8")
    if payload:
        payload += b"\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def append_usable_index_row(
    *,
    state_root: Path,
    capsule_id: str,
    distillate_graph_id: str,
    usable_b: bool,
    cert_gate_status: str,
    cert_profile_id: str,
    reason_code: str,
) -> dict[str, Any]:
    state_root = state_root.resolve()
    capsule_id = ensure_sha256(capsule_id, reason="SCHEMA_FAIL")
    distillate_graph_id = ensure_sha256(distillate_graph_id, reason="SCHEMA_FAIL")
    cert_profile_id = ensure_sha256(cert_profile_id, reason="SCHEMA_FAIL")
    reason_code = str(reason_code).strip() or "UNKNOWN"
    cert_gate_status = str(cert_gate_status).strip().upper()
    if cert_gate_status not in {"PASS", "WARN", "BLOCKED"}:
        fail("SCHEMA_FAIL")

    rows = load_rows(state_root)
    for row in rows:
        if str(row.get("capsule_id", "")) != capsule_id:
            continue
        # Idempotent if all deterministic fields match.
        if (
            str(row.get("distillate_graph_id", "")) == distillate_graph_id
            and bool(row.get("usable_b")) is bool(usable_b)
            and str(row.get("cert_gate_status", "")) == cert_gate_status
            and str(row.get("cert_profile_id", "")) == cert_profile_id
            and str(row.get("reason_code", "")) == reason_code
        ):
            return dict(row)
        fail("NONDETERMINISTIC")

    prev_hash = str(rows[-1].get("row_hash")) if rows else None
    payload = {
        "schema_version": "epistemic_usable_capsule_index_row_v1",
        "row_hash": "sha256:" + ("0" * 64),
        "prev_row_hash": prev_hash,
        "capsule_id": capsule_id,
        "distillate_graph_id": distillate_graph_id,
        "usable_b": bool(usable_b),
        "cert_gate_status": cert_gate_status,
        "cert_profile_id": cert_profile_id,
        "reason_code": reason_code,
    }
    payload["row_hash"] = canon_hash_obj({k: v for k, v in payload.items() if k != "row_hash"})
    _validate_row(payload)
    rows.append(payload)
    _write_rows(_index_path(state_root), rows)
    return payload


def load_usable_capsule_ids(state_root: Path) -> set[str]:
    return {
        str(row.get("capsule_id", ""))
        for row in load_rows(state_root)
        if bool(row.get("usable_b", False))
    }


def load_usable_graph_ids(state_root: Path) -> set[str]:
    return {
        str(row.get("distillate_graph_id", ""))
        for row in load_rows(state_root)
        if bool(row.get("usable_b", False))
    }


def iter_usable_capsules(state_root: Path) -> list[Path]:
    root = state_root.resolve()
    out: list[Path] = []
    for capsule_id in sorted(load_usable_capsule_ids(root)):
        paths = sorted(
            (root / "epistemic" / "capsules").glob("sha256_*.epistemic_capsule_v1.json"),
            key=lambda p: p.as_posix(),
        )
        matched: Path | None = None
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                fail("SCHEMA_FAIL")
            if not isinstance(payload, dict):
                fail("SCHEMA_FAIL")
            if canon_hash_obj(payload) != "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]:
                fail("NONDETERMINISTIC")
            if str(payload.get("capsule_id", "")) != capsule_id:
                continue
            if matched is not None:
                fail("NONDETERMINISTIC")
            matched = path
        if matched is None:
            fail("MISSING_STATE_INPUT")
        out.append(matched)
    return out


def iter_usable_graphs(state_root: Path) -> list[Path]:
    root = state_root.resolve()
    out: list[Path] = []
    for graph_id in sorted(load_usable_graph_ids(root)):
        paths = sorted(
            (root / "epistemic" / "graphs").glob("sha256_*.qxwmr_graph_v1.json"),
            key=lambda p: p.as_posix(),
        )
        matched: Path | None = None
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                fail("SCHEMA_FAIL")
            if not isinstance(payload, dict):
                fail("SCHEMA_FAIL")
            if canon_hash_obj(payload) != "sha256:" + path.name.split(".", 1)[0].split("_", 1)[1]:
                fail("NONDETERMINISTIC")
            if str(payload.get("graph_id", "")) != graph_id:
                continue
            if matched is not None:
                fail("NONDETERMINISTIC")
            matched = path
        if matched is None:
            fail("MISSING_STATE_INPUT")
        out.append(matched)
    return out


__all__ = [
    "append_usable_index_row",
    "iter_usable_capsules",
    "iter_usable_graphs",
    "load_rows",
    "load_usable_capsule_ids",
    "load_usable_graph_ids",
]
