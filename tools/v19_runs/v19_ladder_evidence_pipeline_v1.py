#!/usr/bin/env python3
"""Deterministic v19 ladder evidence condenser (post-run telemetry only)."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
_ORDERED_PATHS = [str(REPO_ROOT), str(REPO_ROOT / "CDEL-v2")]
for _path in _ORDERED_PATHS:
    while _path in sys.path:
        sys.path.remove(_path)
for _path in reversed(_ORDERED_PATHS):
    sys.path.insert(0, _path)

from cdel.v1_7r.canon import CanonError, canon_bytes, hash_json as canon_hash_obj, load_canon_json, write_canon_json
from cdel.v18_0.omega_common_v1 import validate_schema as validate_schema_v18
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

_TICK_DIR_RE = re.compile(r"^tick_(\d+)$")
_DAEMON_ID = "rsi_omega_daemon_v19_0"
_DAEMON_PATH = Path("daemon") / _DAEMON_ID / "state"
_HASHED_NAME_RE = re.compile(r"^sha256_([0-9a-f]{64})\.(.+)$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_LEVELS: tuple[tuple[str, str], ...] = (
    ("L0", "M_SIGMA"),
    ("L1", "M_SIGMA"),
    ("L2", "M_PI"),
    ("L3", "M_D"),
    ("L4", "M_H"),
    ("L5", "M_A"),
    ("L6", "M_K"),
    ("L7", "M_E"),
    ("L8", "M_M"),
    ("L9", "M_C"),
    ("L10", "M_W"),
    ("L11", "M_T"),
)


def _state_root(run_dir: Path) -> Path:
    return run_dir / _DAEMON_PATH


def _tick_run_dirs(runs_root: Path) -> list[tuple[int, Path]]:
    out: list[tuple[int, Path]] = []
    for child in sorted(runs_root.iterdir(), key=lambda row: row.as_posix()):
        if not child.is_dir():
            continue
        match = _TICK_DIR_RE.fullmatch(child.name)
        if match:
            out.append((int(match.group(1)), child))
    if out:
        out.sort(key=lambda row: int(row[0]))
        return out
    return [(0, runs_root)]


def _last_matching(parent: Path, pattern: str) -> Path | None:
    if not parent.exists() or not parent.is_dir():
        return None
    rows = sorted(parent.glob(pattern), key=lambda row: row.as_posix())
    return rows[-1] if rows else None


def _to_relpath(runs_root: Path, path: Path) -> str:
    runs_root = runs_root.resolve()
    try:
        rel = path.resolve().relative_to(runs_root)
    except ValueError:
        return path.name
    return rel.as_posix()


def _contains_absolute_path(text: str) -> bool:
    if not text:
        return False
    # Drive-letter paths (C:\..., D:/...) but avoid matching URL schemes like "http://".
    if re.search(r"(?:^|[^A-Za-z0-9])[A-Za-z]:[\\/]", text):
        return True
    # UNC paths like \\server\share.
    if re.search(r"(?:^|\\s)\\\\\\\\[^\\s]+", text):
        return True
    # POSIX absolute paths anywhere in the string (common in error messages).
    if re.search(r"(?:^|\\s|[\\(\\[\\{\\\"\\'])/[^\\s]+", text):
        return True
    return False


def _filename_hash(path: Path) -> str | None:
    match = _HASHED_NAME_RE.fullmatch(path.name)
    if not match:
        return None
    return f"sha256:{match.group(1)}"


def _validate_hashed_filename(path: Path, expected_suffix: str) -> str | None:
    if not path.name.startswith("sha256_"):
        return None
    if not path.name.endswith(f".{expected_suffix}"):
        return None
    return _filename_hash(path)


def _is_relative_no_parent(value: str) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value:
        return False
    if value.startswith("/") or value.startswith("\\"):
        return False
    if re.fullmatch(r"[A-Za-z]:[\\/].*", value):
        return False
    if ".." in Path(value).parts:
        return False
    if "\\" in value:
        return False
    return True


def _append_failure(
    failures: list[dict[str, Any]],
    *,
    code: str,
    tick_u64: int | None,
    dispatch_relpath: str | None,
    detail: str | None,
) -> None:
    record: dict[str, Any] = {"code": code}
    if tick_u64 is not None:
        record["tick_u64"] = int(tick_u64)
    if dispatch_relpath:
        record["dispatch_relpath"] = dispatch_relpath
    if detail:
        record["detail"] = detail
    failures.append(record)


def _manifest_add(manifest: dict[str, str], *, runs_root: Path, path: Path, digest: str | None) -> None:
    if not digest:
        return
    relpath = _to_relpath(runs_root, path)
    if not relpath:
        return
    manifest[relpath] = str(digest)


def _validate_schema(
    payload: dict[str, Any],
    *,
    schema_name: str,
    version: str,
    failures: list[dict[str, Any]],
    tick_u64: int | None,
    dispatch_relpath: str | None,
    code_override: str | None = None,
) -> bool:
    try:
        if version == "v18":
            validate_schema_v18(payload, schema_name)
        else:
            validate_schema_v19(payload, schema_name)
    except Exception:
        _append_failure(
            failures=failures,
            code=code_override or f"SCHEMA_VALIDATION_FAIL:{schema_name}",
            tick_u64=tick_u64,
            dispatch_relpath=dispatch_relpath,
            detail=None,
        )
        return False
    return True


def _validate_declared_id(
    payload: dict[str, Any],
    *,
    id_field: str,
    failures: list[dict[str, Any]],
    tick_u64: int | None,
    dispatch_relpath: str | None,
    value_path: str | None,
    code: str | None = None,
) -> bool:
    fail_code = code or f"ID_MISMATCH:{id_field}"
    declared = str(payload.get(id_field, "")).strip()
    if not declared or _SHA256_RE.fullmatch(declared) is None:
        _append_failure(
            failures=failures,
            code=fail_code,
            tick_u64=tick_u64,
            dispatch_relpath=dispatch_relpath,
            detail=f"path={value_path}" if value_path else "missing_id_field",
        )
        return False
    no_id = dict(payload)
    no_id.pop(id_field, None)
    observed = canon_hash_obj(no_id)
    if observed != declared:
        _append_failure(
            failures=failures,
            code=fail_code,
            tick_u64=tick_u64,
            dispatch_relpath=dispatch_relpath,
            detail=f"path={value_path}" if value_path else "declared_id_mismatch",
        )
        return False
    return True


def _load_payload(
    *,
    path: Path,
    runs_root: Path,
    failures: list[dict[str, Any]],
    tick_u64: int | None,
    dispatch_relpath: str | None,
    expect_hashed_suffix: str | None = None,
    schema_version: str | None = None,
    schema_name: str | None = None,
    id_field: str | None = None,
    schema_fail_code: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = load_canon_json(path)
    except Exception:
        _append_failure(
            failures=failures,
            code="NON_CANONICAL_JSON",
            tick_u64=tick_u64,
            dispatch_relpath=dispatch_relpath,
            detail=f"relpath={_to_relpath(runs_root, path)}",
        )
        return None, None

    if not isinstance(payload, dict):
        if schema_name:
            _append_failure(
                failures=failures,
                code=schema_fail_code or f"SCHEMA_VALIDATION_FAIL:{schema_name}",
                tick_u64=tick_u64,
                dispatch_relpath=dispatch_relpath,
                detail=f"relpath={_to_relpath(runs_root, path)}",
            )
        return None, None

    digest = canon_hash_obj(payload)
    relpath = _to_relpath(runs_root, path)

    if expect_hashed_suffix is not None:
        filename_digest = _validate_hashed_filename(path, expect_hashed_suffix)
        if filename_digest is None:
            _append_failure(
                failures=failures,
                code="HASH_MISMATCH_FILENAME",
                tick_u64=tick_u64,
                dispatch_relpath=dispatch_relpath,
                detail=f"relpath={relpath}",
            )
            return None, digest
        if filename_digest != digest:
            _append_failure(
                failures=failures,
                code="HASH_MISMATCH_FILENAME",
                tick_u64=tick_u64,
                dispatch_relpath=dispatch_relpath,
                detail=f"relpath={relpath}",
            )
            return None, digest

    if schema_name:
        if not _validate_schema(
            payload,
            schema_name=schema_name,
            version=str(schema_version or "v19"),
            failures=failures,
            tick_u64=tick_u64,
            dispatch_relpath=dispatch_relpath,
            code_override=schema_fail_code,
        ):
            return None, digest

    if id_field:
        if not _validate_declared_id(payload=payload, id_field=id_field, failures=failures, tick_u64=tick_u64, dispatch_relpath=dispatch_relpath, value_path=relpath):
            return None, digest

    return payload, digest


def _count_morphism_payloads(
    *,
    bundle_root: Path,
    axis_bundle_payload: dict[str, Any],
    tick_u64: int | None,
    dispatch_relpath: str,
    runs_root: Path,
    failures: list[dict[str, Any]],
) -> tuple[set[str], dict[str, int], dict[str, int], list[tuple[Path, str]], bool]:
    """Extract morphisms from a single axis bundle.

    Returns `(morphism_types, histogram_delta, first_tick_delta, evidence_entries, ok)`.
    If `ok` is false, the caller MUST treat the dispatch as non-counted to avoid
    soft-skipping morphism evidence.
    """
    morphism_types: set[str] = set()
    histogram_delta: dict[str, int] = {}
    first_tick_delta: dict[str, int] = {}
    evidence_entries: list[tuple[Path, str]] = []
    ok = True
    morphisms = axis_bundle_payload.get("morphisms")
    if not isinstance(morphisms, list):
        _append_failure(
            failures=failures,
            code="PROMOTED_AXIS_BUNDLE_SCHEMA_FAIL",
            tick_u64=tick_u64,
            dispatch_relpath=dispatch_relpath,
            detail="axis_bundle.morphisms",
        )
        return morphism_types, histogram_delta, first_tick_delta, evidence_entries, False

    if not morphisms:
        _append_failure(
            failures=failures,
            code="PROMOTED_AXIS_BUNDLE_SCHEMA_FAIL",
            tick_u64=tick_u64,
            dispatch_relpath=dispatch_relpath,
            detail="axis_bundle.morphisms.empty",
        )
        return morphism_types, histogram_delta, first_tick_delta, evidence_entries, False

    bundle_root_resolved = bundle_root.resolve()

    for row in morphisms:
        if not isinstance(row, dict):
            ok = False
            _append_failure(
                failures=failures,
                code="PROMOTED_AXIS_BUNDLE_SCHEMA_FAIL",
                tick_u64=tick_u64,
                dispatch_relpath=dispatch_relpath,
                detail="axis_bundle.morphisms[]",
            )
            continue
        morphism_ref = row.get("morphism_ref")
        if not isinstance(morphism_ref, dict):
            ok = False
            _append_failure(
                failures=failures,
                code="PROMOTED_AXIS_BUNDLE_SCHEMA_FAIL",
                tick_u64=tick_u64,
                dispatch_relpath=dispatch_relpath,
                detail="morphism_ref",
            )
            continue
        artifact_relpath = str(morphism_ref.get("artifact_relpath", "")).strip()
        if not _is_relative_no_parent(artifact_relpath):
            _append_failure(
                failures=failures,
                code="PROMOTED_AXIS_BUNDLE_SCHEMA_FAIL",
                tick_u64=tick_u64,
                dispatch_relpath=dispatch_relpath,
                detail="morphism_ref.artifact_relpath",
            )
            ok = False
            continue
        morphism_path = (bundle_root_resolved / artifact_relpath).resolve()
        try:
            morphism_path.relative_to(bundle_root_resolved)
        except ValueError:
            _append_failure(
                failures=failures,
                code="PROMOTED_AXIS_BUNDLE_SCHEMA_FAIL",
                tick_u64=tick_u64,
                dispatch_relpath=dispatch_relpath,
                detail=f"artifact_relpath={artifact_relpath}",
            )
            ok = False
            continue
        if not morphism_path.exists() or not morphism_path.is_file():
            _append_failure(
                failures=failures,
                code="PROMOTED_AXIS_BUNDLE_SCHEMA_FAIL",
                tick_u64=tick_u64,
                dispatch_relpath=dispatch_relpath,
                detail=f"artifact_relpath={artifact_relpath}",
            )
            ok = False
            continue
        morphism_payload, morphism_digest = _load_payload(
            path=morphism_path,
            runs_root=runs_root,
            failures=failures,
            tick_u64=tick_u64,
            dispatch_relpath=dispatch_relpath,
        )
        if morphism_payload is None:
            _append_failure(
                failures=failures,
                code="PROMOTED_AXIS_BUNDLE_SCHEMA_FAIL",
                tick_u64=tick_u64,
                dispatch_relpath=dispatch_relpath,
                detail=f"artifact_relpath={artifact_relpath}",
            )
            ok = False
            continue
        if not morphism_digest:
            ok = False
            continue
        morphism_type = str(morphism_payload.get("morphism_type", "")).strip()
        if not morphism_type:
            _append_failure(
                failures=failures,
                code="PROMOTED_AXIS_BUNDLE_SCHEMA_FAIL",
                tick_u64=tick_u64,
                dispatch_relpath=dispatch_relpath,
                detail="morphism_type",
            )
            ok = False
            continue
        evidence_entries.append((morphism_path, morphism_digest))
        morphism_types.add(morphism_type)
        histogram_delta[morphism_type] = int(histogram_delta.get(morphism_type, 0)) + 1
        if tick_u64 is not None and (
            morphism_type not in first_tick_delta or int(first_tick_delta[morphism_type]) > tick_u64
        ):
            first_tick_delta[morphism_type] = int(tick_u64)

    if not morphism_types:
        ok = False

    return morphism_types, histogram_delta, first_tick_delta, evidence_entries, ok


def _compute_levels(success_events: list[tuple[int, set[str], str]]) -> tuple[list[str], str | None, dict[str, int], int | None]:
    achieved: list[str] = []
    level_first: dict[str, int] = {}
    seen: set[str] = set()
    for tick_u64, morphism_types, _ in sorted(success_events, key=lambda row: (int(row[0]), str(row[2]))):
        seen.update(morphism_types)
        for idx, (level, morphism_type) in enumerate(_LEVELS):
            if level in level_first:
                continue
            required = {m for _, m in _LEVELS[: idx + 1]}
            if required.issubset(seen):
                level_first[level] = int(tick_u64)
    for idx, (level, _morphism_type) in enumerate(_LEVELS):
        if level in level_first:
            achieved.append(level)
    max_level = achieved[-1] if achieved else None
    max_level_tick = level_first[max_level] if max_level else None
    return achieved, max_level, level_first, max_level_tick


def _sorted_failures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("dispatch_relpath", "")),
            int(row.get("tick_u64", -1)),
            str(row.get("code", "")),
            str(row.get("detail", "")),
        ),
    )


def _build_report(*, runs_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    runs_root = runs_root.resolve()

    promotion_totals = {
        "promotion_receipts_total_u64": 0,
        "promotion_receipts_by_status_u64": {"PROMOTED": 0, "REJECTED": 0, "SKIPPED": 0},
        "promotion_receipts_by_reason_code_u64": {},
    }
    axis_gate_failures = {"SAFE_HALT": 0, "SAFE_SPLIT": 0, "OTHER": 0}
    morphism_histogram: dict[str, int] = {}
    morphism_first_tick: dict[str, int] = {}
    fatal_failures: list[dict[str, Any]] = []
    nonfatal_failures: list[dict[str, Any]] = []
    manifest: dict[str, str] = {}
    success_events: list[tuple[int, set[str], str]] = []

    for tick_u64, run_dir in _tick_run_dirs(runs_root):
        state_root = _state_root(run_dir)
        if not state_root.exists() or not state_root.is_dir():
            run_dir_rel = _to_relpath(runs_root, run_dir)
            _append_failure(
                failures=nonfatal_failures,
                code="MISSING_STATE_ROOT",
                tick_u64=int(tick_u64),
                dispatch_relpath=None,
                detail=f"run_dir={run_dir_rel}",
            )
            continue

        dispatch_root = state_root / "dispatch"
        if not dispatch_root.exists() or not dispatch_root.is_dir():
            continue

        for dispatch_dir in sorted(dispatch_root.iterdir(), key=lambda row: row.as_posix()):
            if not dispatch_dir.is_dir():
                continue
            dispatch_relpath = _to_relpath(runs_root, dispatch_dir)
            promotion_root = dispatch_dir / "promotion"
            promotion_path = _last_matching(promotion_root, "sha256_*.omega_promotion_receipt_v1.json")
            promotion_payload = None
            promotion_digest = None
            promotion_status = None
            event_tick = int(tick_u64)
            if promotion_path is not None:
                promotion_payload, promotion_digest = _load_payload(
                    path=promotion_path,
                    runs_root=runs_root,
                    failures=nonfatal_failures,
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    expect_hashed_suffix="omega_promotion_receipt_v1.json",
                    schema_version="v18",
                    schema_name="omega_promotion_receipt_v1",
                    id_field="receipt_id",
                )
                if isinstance(promotion_payload, dict):
                    try:
                        event_tick = int(promotion_payload.get("tick_u64", event_tick))
                    except Exception:
                        event_tick = int(tick_u64)
                    result_obj = promotion_payload.get("result")
                    if isinstance(result_obj, dict):
                        promotion_status = str(result_obj.get("status", "")).strip()
                    if promotion_status in {"PROMOTED", "REJECTED", "SKIPPED"}:
                        promotion_totals["promotion_receipts_total_u64"] += 1
                        promotion_totals["promotion_receipts_by_status_u64"][promotion_status] = int(
                            promotion_totals["promotion_receipts_by_status_u64"].get(promotion_status, 0)
                        ) + 1
                        if promotion_status != "PROMOTED":
                            reason = result_obj.get("reason_code") if isinstance(result_obj, dict) else None
                            if reason:
                                reason_str = str(reason).strip()
                                if reason_str:
                                    promotion_totals["promotion_receipts_by_reason_code_u64"][reason_str] = int(
                                        promotion_totals["promotion_receipts_by_reason_code_u64"].get(reason_str, 0) + 1
                                    )
                        _manifest_add(manifest, runs_root=runs_root, path=promotion_path, digest=promotion_digest)
            promotion_is_promoted = promotion_status == "PROMOTED"

            dispatch_receipt = _last_matching(dispatch_dir, "sha256_*.omega_dispatch_receipt_v1.json")
            if dispatch_receipt is None:
                _append_failure(
                    failures=fatal_failures if promotion_is_promoted else nonfatal_failures,
                    code="MISSING_DISPATCH_RECEIPT",
                    tick_u64=int(event_tick),
                    dispatch_relpath=dispatch_relpath,
                    detail="missing_dispatch_receipt",
                )
                continue

            dispatch_payload, dispatch_digest = _load_payload(
                path=dispatch_receipt,
                runs_root=runs_root,
                failures=fatal_failures if promotion_is_promoted else nonfatal_failures,
                tick_u64=int(event_tick),
                dispatch_relpath=dispatch_relpath,
                expect_hashed_suffix="omega_dispatch_receipt_v1.json",
                schema_version="v18",
                schema_name="omega_dispatch_receipt_v1",
                id_field="receipt_id",
            )
            if dispatch_payload is None:
                continue

            dispatch_tick = dispatch_payload.get("tick_u64")
            try:
                event_tick = int(dispatch_tick)
            except Exception:
                event_tick = int(event_tick)

            subverifier_dir = dispatch_dir / "verifier"
            subverifier_path = _last_matching(subverifier_dir, "sha256_*.omega_subverifier_receipt_v1.json")
            if subverifier_path is not None:
                _load_payload(
                    path=subverifier_path,
                    runs_root=runs_root,
                    failures=nonfatal_failures,
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    expect_hashed_suffix="omega_subverifier_receipt_v1.json",
                    schema_version="v18",
                    schema_name="omega_subverifier_receipt_v1",
                    id_field="receipt_id",
                )

            subrun_obj = dispatch_payload.get("subrun")
            if not isinstance(subrun_obj, dict):
                _append_failure(
                    failures=fatal_failures if promotion_is_promoted else nonfatal_failures,
                    code="SCHEMA_VALIDATION_FAIL:omega_dispatch_receipt_v1",
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    detail="dispatch.subrun",
                )
                continue

            subrun_root_rel = str(subrun_obj.get("subrun_root_rel", "")).strip()
            state_dir_rel = str(subrun_obj.get("state_dir_rel", "")).strip()
            if not _is_relative_no_parent(subrun_root_rel) or not _is_relative_no_parent(state_dir_rel):
                _append_failure(
                    failures=fatal_failures if promotion_is_promoted else nonfatal_failures,
                    code="SCHEMA_VALIDATION_FAIL:omega_dispatch_receipt_v1",
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    detail="dispatch.subrun",
                )
                continue

            subrun_state_dir = state_root / subrun_root_rel / state_dir_rel
            if not subrun_state_dir.exists() or not subrun_state_dir.is_dir():
                _append_failure(
                    failures=fatal_failures if promotion_is_promoted else nonfatal_failures,
                    code="SCHEMA_VALIDATION_FAIL:omega_dispatch_receipt_v1",
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    detail="subrun.pointers",
                )
                continue

            subrun_promotion_dir = subrun_state_dir / "promotion"

            # Gate failures may be written in the subrun promotion dir, and some tooling
            # also mirrors them under the dispatch promotion dir. Prefer the subrun path.
            axis_gate_failure_present = False
            axis_gate_path: Path | None = None
            for candidate in (
                subrun_promotion_dir / "axis_gate_failure_v1.json",
                promotion_root / "axis_gate_failure_v1.json",
            ):
                if candidate.exists() and candidate.is_file():
                    axis_gate_failure_present = True
                    axis_gate_path = candidate
                    break

            if axis_gate_path is not None:
                gate_payload, gate_digest = _load_payload(
                    path=axis_gate_path,
                    runs_root=runs_root,
                    failures=nonfatal_failures,
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    schema_version="v19",
                    schema_name="axis_gate_failure_v1",
                    schema_fail_code="AXIS_GATE_FAILURE_SCHEMA_FAIL",
                )
                if gate_payload is not None:
                    detail = str(gate_payload.get("detail", "")).strip()
                    outcome = str(gate_payload.get("outcome", "")).strip()
                    if not detail or _contains_absolute_path(detail):
                        _append_failure(
                            failures=nonfatal_failures,
                            code="AXIS_GATE_FAILURE_SCHEMA_FAIL",
                            tick_u64=event_tick,
                            dispatch_relpath=dispatch_relpath,
                            detail="axis_gate_failure_v1.detail",
                        )
                    elif outcome == "SAFE_HALT":
                        axis_gate_failures["SAFE_HALT"] += 1
                        _manifest_add(manifest, runs_root=runs_root, path=axis_gate_path, digest=gate_digest)
                    elif outcome == "SAFE_SPLIT":
                        axis_gate_failures["SAFE_SPLIT"] += 1
                        _manifest_add(manifest, runs_root=runs_root, path=axis_gate_path, digest=gate_digest)
                    else:
                        _append_failure(
                            failures=nonfatal_failures,
                            code="AXIS_GATE_FAILURE_SCHEMA_FAIL",
                            tick_u64=event_tick,
                            dispatch_relpath=dispatch_relpath,
                            detail="axis_gate_failure_v1.outcome",
                        )

            if not promotion_is_promoted:
                continue

            counted = True
            counted_evidence: list[tuple[Path, str]] = []
            if axis_gate_failure_present:
                _append_failure(
                    failures=fatal_failures,
                    code="PROMOTED_AXIS_GATE_FAILURE_PRESENT",
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    detail="axis_gate_failure_v1.json",
                )
                counted = False

            verify_candidates = sorted(
                promotion_root.glob("sha256_*.meta_core_promo_verify_receipt_v1.json"),
                key=lambda row: row.as_posix(),
            )
            verify_payload_path = verify_candidates[-1] if verify_candidates else None
            if verify_payload_path is None:
                plain_verify = promotion_root / "meta_core_promo_verify_receipt_v1.json"
                if plain_verify.exists() and plain_verify.is_file():
                    verify_payload_path = plain_verify
            if verify_payload_path is None:
                _append_failure(
                    failures=fatal_failures,
                    code="PROMOTED_MISSING_META_CORE_VERIFY",
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    detail="meta_core_promo_verify_receipt_v1",
                )
                counted = False
            else:
                verify_expect = "meta_core_promo_verify_receipt_v1.json" if verify_payload_path.name.startswith("sha256_") else None
                verify_payload, verify_digest = _load_payload(
                    path=verify_payload_path,
                    runs_root=runs_root,
                    failures=fatal_failures,
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    expect_hashed_suffix=verify_expect,
                    schema_version="v18",
                    schema_name="meta_core_promo_verify_receipt_v1",
                )
                if verify_payload is None or not bool(verify_payload.get("pass", False)):
                    counted = False
                    _append_failure(
                        failures=fatal_failures,
                        code="PROMOTED_META_CORE_VERIFY_FAIL",
                        tick_u64=event_tick,
                        dispatch_relpath=dispatch_relpath,
                        detail="meta_core_promo_verify_receipt_v1.pass",
                    )
                elif verify_digest:
                    counted_evidence.append((verify_payload_path, verify_digest))

            binding_path = promotion_root / "omega_activation_binding_v1.json"
            if not binding_path.exists() or not binding_path.is_file():
                _append_failure(
                    failures=fatal_failures,
                    code="PROMOTED_MISSING_BINDING",
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    detail="omega_activation_binding_v1.json",
                )
                counted = False
            else:
                binding_payload, binding_digest = _load_payload(
                    path=binding_path,
                    runs_root=runs_root,
                    failures=fatal_failures,
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    schema_version="v18",
                    schema_name="omega_activation_binding_v1",
                    id_field="binding_id",
                )
                if binding_payload is None:
                    counted = False
                elif binding_digest:
                    counted_evidence.append((binding_path, binding_digest))

            activation_root = dispatch_dir / "activation"
            activation_path = _last_matching(activation_root, "sha256_*.omega_activation_receipt_v1.json")
            if activation_path is None:
                _append_failure(
                    failures=fatal_failures,
                    code="PROMOTED_MISSING_ACTIVATION_RECEIPT",
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    detail="activation/sha256_*.omega_activation_receipt_v1.json",
                )
                counted = False
            else:
                activation_payload, activation_digest = _load_payload(
                    path=activation_path,
                    runs_root=runs_root,
                    failures=fatal_failures,
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    expect_hashed_suffix="omega_activation_receipt_v1.json",
                    schema_version="v18",
                    schema_name="omega_activation_receipt_v1",
                    id_field="receipt_id",
                )
                if activation_payload is None:
                    counted = False
                elif not bool(activation_payload.get("activation_success", False)):
                    _append_failure(
                        failures=fatal_failures,
                        code="PROMOTED_ACTIVATION_NOT_SUCCESS",
                        tick_u64=event_tick,
                        dispatch_relpath=dispatch_relpath,
                        detail="omega_activation_receipt_v1.activation_success",
                    )
                    counted = False
                elif activation_digest:
                    counted_evidence.append((activation_path, activation_digest))

            if not (subrun_promotion_dir / "objective_J_old_v1.json").exists():
                _append_failure(
                    failures=fatal_failures,
                    code="PROMOTED_MISSING_OBJECTIVE_J_OLD",
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    detail="objective_J_old_v1.json",
                )
                counted = False
            else:
                objective_old_payload, objective_old_digest = _load_payload(
                    path=subrun_promotion_dir / "objective_J_old_v1.json",
                    runs_root=runs_root,
                    failures=fatal_failures,
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                )
                if objective_old_payload is None:
                    counted = False
                elif objective_old_digest:
                    counted_evidence.append((subrun_promotion_dir / "objective_J_old_v1.json", objective_old_digest))

            if not (subrun_promotion_dir / "objective_J_new_v1.json").exists():
                _append_failure(
                    failures=fatal_failures,
                    code="PROMOTED_MISSING_OBJECTIVE_J_NEW",
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    detail="objective_J_new_v1.json",
                )
                counted = False
            else:
                objective_new_payload, objective_new_digest = _load_payload(
                    path=subrun_promotion_dir / "objective_J_new_v1.json",
                    runs_root=runs_root,
                    failures=fatal_failures,
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                )
                if objective_new_payload is None:
                    counted = False
                elif objective_new_digest:
                    counted_evidence.append((subrun_promotion_dir / "objective_J_new_v1.json", objective_new_digest))

            axis_bundle_path = promotion_root / "meta_core_promotion_bundle_v1" / "omega" / "axis_upgrade_bundle_v1.json"
            promoted_morphism_types: set[str] = set()
            if not axis_bundle_path.exists() or not axis_bundle_path.is_file():
                _append_failure(
                    failures=fatal_failures,
                    code="PROMOTED_MISSING_AXIS_BUNDLE",
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    detail="meta_core_promotion_bundle_v1/omega/axis_upgrade_bundle_v1.json",
                )
                counted = False
            else:
                axis_bundle_payload, axis_bundle_digest = _load_payload(
                    path=axis_bundle_path,
                    runs_root=runs_root,
                    failures=fatal_failures,
                    tick_u64=event_tick,
                    dispatch_relpath=dispatch_relpath,
                    schema_version="v19",
                    schema_name="axis_upgrade_bundle_v1",
                    schema_fail_code="PROMOTED_AXIS_BUNDLE_SCHEMA_FAIL",
                )
                if axis_bundle_payload is None:
                    counted = False
                else:
                    if not _validate_declared_id(
                        payload=axis_bundle_payload,
                        id_field="axis_bundle_id",
                        failures=fatal_failures,
                        tick_u64=event_tick,
                        dispatch_relpath=dispatch_relpath,
                        value_path=_to_relpath(runs_root, axis_bundle_path),
                        code="PROMOTED_AXIS_BUNDLE_ID_MISMATCH",
                    ):
                        counted = False
                    else:
                        (
                            promoted_morphism_types,
                            histogram_delta,
                            first_tick_delta,
                            morphism_evidence,
                            morphism_ok,
                        ) = _count_morphism_payloads(
                            bundle_root=axis_bundle_path.parent.parent,
                            axis_bundle_payload=axis_bundle_payload,
                            tick_u64=event_tick,
                            dispatch_relpath=dispatch_relpath,
                            runs_root=runs_root,
                            failures=fatal_failures,
                        )
                        if not morphism_ok:
                            counted = False
                        else:
                            if axis_bundle_digest:
                                counted_evidence.append((axis_bundle_path, axis_bundle_digest))
                            counted_evidence.extend(morphism_evidence)
                            for morphism_type, count in histogram_delta.items():
                                morphism_histogram[morphism_type] = int(morphism_histogram.get(morphism_type, 0)) + int(count)
                            for morphism_type, first_tick in first_tick_delta.items():
                                if morphism_type not in morphism_first_tick or int(morphism_first_tick[morphism_type]) > int(first_tick):
                                    morphism_first_tick[morphism_type] = int(first_tick)
            if counted:
                success_events.append((event_tick, set(promoted_morphism_types), dispatch_relpath))
                # Promotion receipt is counted toward totals; dispatch receipt is required to locate subrun evidence.
                if promotion_path is not None and promotion_digest:
                    counted_evidence.append((promotion_path, promotion_digest))
                if dispatch_digest:
                    counted_evidence.append((dispatch_receipt, dispatch_digest))
                for path, digest in counted_evidence:
                    _manifest_add(manifest, runs_root=runs_root, path=path, digest=digest)

            if not counted:
                continue

    if not success_events:
        _append_failure(
            failures=fatal_failures,
            code="NO_PROMOTED_EVENTS",
            tick_u64=None,
            dispatch_relpath=None,
            detail="no counted promoted events",
        )

    if not morphism_histogram:
        _append_failure(
            failures=fatal_failures,
            code="NO_PROMOTED_MORPHISMS",
            tick_u64=None,
            dispatch_relpath=None,
            detail="no promoted morphisms extracted",
        )

    achieved_levels, max_level, level_first, max_level_tick = _compute_levels(success_events)

    axis_gate_failures_u64 = (
        int(axis_gate_failures["SAFE_HALT"]) + int(axis_gate_failures["SAFE_SPLIT"]) + int(axis_gate_failures["OTHER"])
    )
    morphism_types_sorted = sorted(morphism_histogram.keys())

    inputs_manifest = [
        {"relpath": relpath, "sha256": digest}
        for relpath, digest in sorted(manifest.items(), key=lambda row: row[0])
    ]
    inputs_manifest_hash = canon_hash_obj(
        {
            "schema_name": "v19_ladder_evidence_report_inputs_manifest_v1",
            "entries": inputs_manifest,
        }
    )

    fatal_sorted = _sorted_failures(fatal_failures)
    nonfatal_sorted = _sorted_failures(nonfatal_failures)

    report = {
        "schema_name": "v19_ladder_evidence_report_v1",
        "schema_version": "v19_0",
        "inputs_manifest": inputs_manifest,
        "inputs_manifest_hash": inputs_manifest_hash,
        "promotion_totals": {
            "promotion_receipts_total_u64": int(promotion_totals["promotion_receipts_total_u64"]),
            "promotion_receipts_by_status_u64": {status: int(count) for status, count in promotion_totals["promotion_receipts_by_status_u64"].items()},
            "promotion_receipts_by_reason_code_u64": {
                key: int(value) for key, value in sorted(promotion_totals["promotion_receipts_by_reason_code_u64"].items())
            },
        },
        "axis_gate_failures": {
            "by_outcome_u64": {
                "SAFE_HALT": int(axis_gate_failures["SAFE_HALT"]),
                "SAFE_SPLIT": int(axis_gate_failures["SAFE_SPLIT"]),
                "OTHER": int(axis_gate_failures["OTHER"]),
            },
            "failures_u64": int(axis_gate_failures_u64),
        },
        "morphism_stats": {
            "morphism_histogram_promoted_u64": {key: int(value) for key, value in sorted(morphism_histogram.items())},
            "morphism_types_promoted": morphism_types_sorted,
            "morphism_first_promoted_tick_u64": {
                key: int(value) for key, value in sorted(morphism_first_tick.items(), key=lambda row: row[0])
            },
        },
        "levels": {
            "mapping": [{"level": level, "morphism_type": morphism_type} for level, morphism_type in _LEVELS],
            "achieved_levels_monotone": achieved_levels,
            "max_level_achieved": max_level,
            "level_first_achieved_tick_u64": {
                key: int(value) for key, value in sorted(level_first.items(), key=lambda row: row[0])
            },
            "max_level_achieved_tick_u64": max_level_tick,
        },
        "proof_status": "FAIL",
        "fatal_failures": fatal_sorted,
        "nonfatal_failures": nonfatal_sorted,
    }

    if not fatal_sorted and success_events and morphism_histogram:
        report["proof_status"] = "PASS"

    report["report_id"] = canon_hash_obj({k: v for k, v in report.items() if k != "report_id"})
    return report, fatal_sorted, nonfatal_sorted


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic v19 ladder evidence")
    parser.add_argument("--runs_root", default="runs/v19_full_loop", help="Root directory containing run artifacts")
    parser.add_argument("--verify", action="store_true", help="Verify existing report against recomputation")
    parser.add_argument(
        "--mode",
        default="strict",
        choices=("strict", "lenient"),
        help="strict: non-zero exit if proof_status != PASS; lenient: always exit 0 on successful parse",
    )
    args = parser.parse_args()

    runs_root = Path(str(args.runs_root)).expanduser().resolve()
    report, _fatal_failures, _nonfatal_failures = _build_report(runs_root=runs_root)

    if args.verify:
        out_path = runs_root / "V19_LADDER_EVIDENCE_REPORT_v1.json"
        if not out_path.exists() or not out_path.is_file():
            print(f"missing report: {out_path}")
            return 1
        on_disk = load_canon_json(out_path)
        if not isinstance(on_disk, dict):
            print("invalid report payload")
            return 1
        if on_disk.get("report_id") != report.get("report_id"):
            print("report_id mismatch")
            return 1
        if canon_bytes(on_disk) != canon_bytes(report):
            print("canon bytes mismatch")
            return 1
        print(
            os.linesep.join(
                [
                    f"proof_status={report.get('proof_status')}",
                    f"report_id={report.get('report_id')}",
                ]
            )
        )
        if args.mode == "strict" and report.get("proof_status") != "PASS":
            return 2
        return 0

    out_path = runs_root / "V19_LADDER_EVIDENCE_REPORT_v1.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, report)

    if args.mode == "strict" and report.get("proof_status") != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
