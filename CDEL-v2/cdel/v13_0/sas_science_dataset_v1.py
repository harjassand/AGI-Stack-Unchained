"""Dataset ingest and split logic for SAS-Science v13.0."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from .sas_science_math_v1 import parse_q32_obj, q32_from_decimal_str, Q32MathError


class SASScienceDatasetError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise SASScienceDatasetError(reason)


def _now_utc() -> str:
    # Deterministic timestamp to keep content-addressed artifacts stable.
    return "1970-01-01T00:00:00Z"


@dataclass
class ScienceDataset:
    manifest: dict[str, Any]
    times_q32: list[int]
    positions_q32: dict[str, list[list[int]]]
    dt_q32: int


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = load_canon_json(path)
    except CanonError:
        _fail("INVALID:SCHEMA_FAIL")
    if not isinstance(manifest, dict) or manifest.get("manifest_version") != "sas_science_dataset_manifest_v1":
        _fail("INVALID:SCHEMA_FAIL")
    bodies = manifest.get("bodies")
    if not isinstance(bodies, list) or not bodies:
        _fail("INVALID:SCHEMA_FAIL")
    dim = manifest.get("dim")
    if dim not in (2, 3):
        _fail("INVALID:SCHEMA_FAIL")
    return manifest


def compute_manifest_hash(manifest: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(manifest))


def _required_columns(manifest: dict[str, Any]) -> list[str]:
    bodies = manifest.get("bodies") or []
    dim = int(manifest.get("dim") or 0)
    cols = ["t"]
    for body in bodies:
        cols.append(f"{body}_x")
        cols.append(f"{body}_y")
        if dim == 3:
            cols.append(f"{body}_z")
    frame_kind = manifest.get("frame_kind")
    if frame_kind == "BARYCENTRIC_WITH_SUN_ROW_V1":
        if "Sun" not in bodies:
            cols.append("Sun_x")
            cols.append("Sun_y")
            if dim == 3:
                cols.append("Sun_z")
    return cols


def _scan_forbidden(csv_bytes: bytes, manifest: dict[str, Any]) -> None:
    sec = manifest.get("security") or {}
    if not sec.get("forbidden_string_scan"):
        return
    forbidden = sec.get("forbidden_strings") or []
    if not isinstance(forbidden, list):
        _fail("INVALID:SCHEMA_FAIL")
    hay = csv_bytes.lower()
    for raw in forbidden:
        if not isinstance(raw, str):
            continue
        needle = raw.lower().encode("utf-8")
        if needle and needle in hay:
            _fail(f"INVALID:DATASET_FORBIDDEN_STRING:{raw}")


def load_csv(path: Path, manifest: dict[str, Any]) -> tuple[list[str], list[list[str]]]:
    csv_bytes = path.read_bytes()
    _scan_forbidden(csv_bytes, manifest)
    try:
        text = csv_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SASScienceDatasetError("INVALID:SCHEMA_FAIL") from exc
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        _fail("INVALID:SCHEMA_FAIL")
    header = rows[0]
    data_rows = rows[1:]
    if not header:
        _fail("INVALID:SCHEMA_FAIL")
    return header, data_rows


def _parse_rows(header: list[str], rows: list[list[str]], manifest: dict[str, Any]) -> ScienceDataset:
    required = _required_columns(manifest)
    if set(header) != set(required):
        _fail("INVALID:SCHEMA_FAIL")
    col_index = {name: idx for idx, name in enumerate(header)}
    bodies = manifest.get("bodies") or []
    dim = int(manifest.get("dim") or 0)

    positions: dict[str, list[list[int]]] = {b: [] for b in bodies}
    # include Sun if present
    if "Sun" in [c.split("_")[0] for c in header] and "Sun" not in positions:
        positions["Sun"] = []

    times: list[int] = []
    for row in rows:
        if not row:
            continue
        if len(row) != len(header):
            _fail("INVALID:SCHEMA_FAIL")
        try:
            t_q = q32_from_decimal_str(row[col_index["t"]])
        except Q32MathError:
            _fail("INVALID:SCHEMA_FAIL")
        times.append(t_q)
        for body in positions.keys():
            coords: list[int] = []
            for axis in ("x", "y", "z")[:dim]:
                key = f"{body}_{axis}"
                if key not in col_index:
                    _fail("INVALID:SCHEMA_FAIL")
                try:
                    coords.append(q32_from_decimal_str(row[col_index[key]]))
                except Q32MathError:
                    _fail("INVALID:SCHEMA_FAIL")
            positions[body].append(coords)

    if len(times) < 3:
        _fail("INVALID:SCHEMA_FAIL")
    # uniform dt
    dt_q = times[1] - times[0]
    policy = manifest.get("timestep_policy") or {}
    if policy.get("require_uniform_dt"):
        tol_q = parse_q32_obj(policy.get("uniform_dt_tolerance_q32"))
        for idx in range(2, len(times)):
            dt_i = times[idx] - times[idx - 1]
            if abs(int(dt_i) - int(dt_q)) > int(tol_q):
                _fail("INVALID:SCHEMA_FAIL")

    return ScienceDataset(manifest=manifest, times_q32=times, positions_q32=positions, dt_q32=dt_q)


def load_dataset(csv_path: Path, manifest: dict[str, Any]) -> ScienceDataset:
    header, rows = load_csv(csv_path, manifest)
    return _parse_rows(header, rows, manifest)


def compute_dataset_receipt(
    *,
    manifest: dict[str, Any],
    csv_bytes: bytes,
    row_count: int,
) -> dict[str, Any]:
    manifest_hash = compute_manifest_hash(manifest)
    csv_sha = sha256_prefixed(csv_bytes)
    dataset_id = sha256_prefixed(canon_bytes({"manifest_hash": manifest_hash, "csv_sha256": csv_sha}))
    receipt = {
        "schema_version": "sas_science_dataset_receipt_v1",
        "created_utc": _now_utc(),
        "dataset_id": dataset_id,
        "manifest_hash": manifest_hash,
        "csv_sha256": csv_sha,
        "row_count": int(row_count),
        "dim": int(manifest.get("dim") or 0),
        "bodies": list(manifest.get("bodies") or []),
    }
    return receipt


def compute_split_receipt(
    *,
    manifest: dict[str, Any],
    dataset_id: str,
    row_count: int,
) -> dict[str, Any]:
    split_policy = manifest.get("split_policy") or {}
    split_policy_hash = sha256_prefixed(canon_bytes(split_policy))
    dev_frac_q = parse_q32_obj(split_policy.get("dev_fraction_q32"))
    dev_count = (int(row_count) * int(dev_frac_q)) // (1 << 32)
    if dev_count < 1 or dev_count >= row_count:
        _fail("INVALID:SCHEMA_FAIL")
    dev_start = 0
    dev_end = dev_count - 1
    held_start = dev_count
    held_end = row_count - 1
    guard = int(split_policy.get("guard_steps") or 0)
    dev_eval_start = dev_start + guard
    dev_eval_end = dev_end - guard
    held_eval_start = held_start + guard
    held_eval_end = held_end - guard

    if dev_eval_start < 1 or dev_eval_end > row_count - 2 or dev_eval_start > dev_eval_end:
        _fail("INVALID:SCHEMA_FAIL")
    if held_eval_start < 1 or held_eval_end > row_count - 2 or held_eval_start > held_eval_end:
        _fail("INVALID:SCHEMA_FAIL")

    payload = {
        "dataset_id": dataset_id,
        "split_policy_hash": split_policy_hash,
        "row_count": int(row_count),
        "dev_range_start": dev_start,
        "dev_range_end": dev_end,
        "heldout_range_start": held_start,
        "heldout_range_end": held_end,
        "guard_steps": guard,
        "dev_eval_start": dev_eval_start,
        "dev_eval_end": dev_eval_end,
        "heldout_eval_start": held_eval_start,
        "heldout_eval_end": held_eval_end,
    }
    split_id = sha256_prefixed(canon_bytes(payload))
    receipt = {
        "schema_version": "sas_science_split_receipt_v1",
        "created_utc": _now_utc(),
        "split_id": split_id,
        **payload,
    }
    return receipt


__all__ = [
    "ScienceDataset",
    "load_manifest",
    "compute_manifest_hash",
    "load_dataset",
    "compute_dataset_receipt",
    "compute_split_receipt",
    "SASScienceDatasetError",
]
