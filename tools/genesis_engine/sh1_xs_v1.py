#!/usr/bin/env python3
"""SH-1 deterministic receipt ingest and experience-store snapshot builder."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json
from cdel.v18_0.omega_common_v1 import rat_q32, validate_schema

from .sh1_behavior_sig_v1 import build_behavior_signature, sentinel_class_value
from .sh1_pd_v1 import build_pd_from_patch_bytes, touched_paths_hash_prefix_hex


_Q32_ONE = 1 << 32
_ZERO_SHA = "sha256:" + ("0" * 64)


def _invalid(reason: str) -> RuntimeError:
    msg = reason
    if not msg.startswith("INVALID:"):
        msg = f"INVALID:{msg}"
    return RuntimeError(msg)


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _load_canon_dict(path: Path) -> dict[str, Any]:
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        raise _invalid("SCHEMA_FAIL")
    return payload


def _hash_obj(payload: dict[str, Any]) -> str:
    return _sha256_prefixed(canon_bytes(payload))


def load_ge_config(path: Path) -> dict[str, Any]:
    payload = _load_canon_dict(path)
    validate_schema(payload, "ge_config_v1")
    if str(payload.get("schema_version", "")).strip() != "ge_config_v1":
        raise _invalid("SCHEMA_FAIL")

    got_id = str(payload.get("ge_config_id", "")).strip()
    zeroed = dict(payload)
    zeroed["ge_config_id"] = _ZERO_SHA
    expected_id = _sha256_prefixed(canon_bytes(zeroed))
    if got_id != expected_id:
        raise _invalid("SCHEMA_FAIL")

    fracs = payload.get("bucket_fracs_q32")
    if not isinstance(fracs, dict):
        raise _invalid("SCHEMA_FAIL")
    total = int(fracs.get("opt_q32", 0)) + int(fracs.get("nov_q32", 0)) + int(fracs.get("grow_q32", 0))
    if total != _Q32_ONE:
        raise _invalid("SCHEMA_FAIL")

    receipt_ingest = payload.get("receipt_ingest")
    if not isinstance(receipt_ingest, dict):
        raise _invalid("SCHEMA_FAIL")
    globs = receipt_ingest.get("receipt_globs")
    if not isinstance(globs, list) or not globs:
        raise _invalid("SCHEMA_FAIL")

    return payload


def _receipt_search_roots(recent_runs_root: Path | None) -> list[Path]:
    """Return deterministic search roots for receipt ingest.

    Production run directories contain a full repo clone under `_worktree/` which
    makes naive `runs/**/*.json` globs very expensive. Receipts/refutations and
    CCAP bundles live under `daemon/` (and some test fixtures use `state/`), so
    we scope search to `*/daemon/` and `*/state/` (or the direct subdirs if the
    caller already points at a single run).
    """

    if recent_runs_root is None:
        return []
    if not recent_runs_root.exists() or not recent_runs_root.is_dir():
        return []

    direct_roots: set[Path] = set()
    for direct in ("daemon", "state"):
        candidate = recent_runs_root / direct
        if candidate.exists() and candidate.is_dir():
            direct_roots.add(candidate)
    if direct_roots:
        return sorted(direct_roots, key=lambda row: row.as_posix())

    roots: list[Path] = []
    for child in sorted(recent_runs_root.iterdir(), key=lambda row: row.as_posix()):
        if not child.is_dir():
            continue
        for rel in ("daemon", "state"):
            candidate = child / rel
            if candidate.exists() and candidate.is_dir():
                roots.append(candidate)

    # If we failed to discover any daemon roots, fall back to scanning the given root.
    if not roots:
        return [recent_runs_root]
    return sorted(set(roots), key=lambda row: row.as_posix())


def _collect_matching_paths(*, recent_runs_root: Path | None, globs: list[str]) -> list[Path]:
    roots = _receipt_search_roots(recent_runs_root)
    if not roots:
        return []
    picks: set[Path] = set()
    for root in roots:
        for pattern in globs:
            for path in root.glob(str(pattern)):
                if path.is_file():
                    picks.add(path)
    return sorted(picks, key=lambda row: row.as_posix())


def _refutation_match_rank(*, receipt_path: Path, refutation_path: Path) -> tuple[int, str]:
    if refutation_path.parent == receipt_path.parent:
        return (0, refutation_path.as_posix())
    if refutation_path.parent.parent == receipt_path.parent.parent:
        return (1, refutation_path.as_posix())
    return (2, refutation_path.as_posix())


def _match_refutation_for_receipt(
    *,
    receipt_path: Path,
    ccap_id: str,
    refutation_map: dict[str, list[tuple[Path, dict[str, Any]]]],
) -> dict[str, Any] | None:
    rows = refutation_map.get(ccap_id) or []
    if not rows:
        return None
    ranked = sorted(rows, key=lambda row: _refutation_match_rank(receipt_path=receipt_path, refutation_path=row[0]))
    return ranked[0][1]


def _path_distance(a: Path, b: Path) -> int:
    a_parts = a.resolve().parts
    b_parts = b.resolve().parts
    common = 0
    for x, y in zip(a_parts, b_parts, strict=False):
        if x != y:
            break
        common += 1
    return (len(a_parts) - common) + (len(b_parts) - common)


def _find_ccap_bundle_path(*, recent_runs_root: Path | None, receipt_path: Path, ccap_id: str) -> Path:
    if recent_runs_root is None or not recent_runs_root.exists() or not recent_runs_root.is_dir():
        raise _invalid("MISSING_STATE_INPUT")
    if not str(ccap_id).startswith("sha256:"):
        raise _invalid("SCHEMA_FAIL")
    ccap_hex = str(ccap_id).split(":", 1)[1]
    if len(ccap_hex) != 64:
        raise _invalid("SCHEMA_FAIL")

    candidates: set[Path] = set()
    for root in _receipt_search_roots(recent_runs_root):
        for candidate in root.glob(f"**/sha256_{ccap_hex}.ccap_v1.json"):
            if candidate.is_file():
                candidates.add(candidate)
    candidates = sorted(candidates, key=lambda row: row.as_posix())
    if not candidates:
        raise _invalid("MISSING_STATE_INPUT")
    ranked = sorted(candidates, key=lambda row: (_path_distance(receipt_path, row), row.as_posix()))
    return ranked[0]


def _find_patch_path_for_ccap(*, recent_runs_root: Path | None, ccap_path: Path, patch_blob_id: str) -> Path:
    if not str(patch_blob_id).startswith("sha256:"):
        raise _invalid("SCHEMA_FAIL")
    patch_hex = str(patch_blob_id).split(":", 1)[1]
    if len(patch_hex) != 64:
        raise _invalid("SCHEMA_FAIL")
    filename = f"sha256_{patch_hex}.patch"

    direct_candidates = [
        ccap_path.parent / "blobs" / filename,
        ccap_path.parent / "ccap" / "blobs" / filename,
    ]
    for candidate in direct_candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    if recent_runs_root is None or not recent_runs_root.exists() or not recent_runs_root.is_dir():
        raise _invalid("MISSING_STATE_INPUT")

    global_candidates: set[Path] = set()
    for root in _receipt_search_roots(recent_runs_root):
        for candidate in root.glob(f"**/{filename}"):
            if candidate.is_file():
                global_candidates.add(candidate)
    global_candidates = sorted(global_candidates, key=lambda row: row.as_posix())
    if not global_candidates:
        raise _invalid("MISSING_STATE_INPUT")
    ranked = sorted(global_candidates, key=lambda row: (_path_distance(ccap_path, row), row.as_posix()))
    return ranked[0]


def _event_stream_hash(events: list[dict[str, Any]]) -> str:
    rows = [
        {
            "ccap_id": str(row["ccap_id"]),
            "receipt_hash": str(row["receipt_hash"]),
            "refutation_code_or_empty": str(row["refutation_code_or_empty"]),
        }
        for row in events
    ]
    return _sha256_prefixed(canon_bytes({"events": rows}))


def build_xs_snapshot(
    *,
    recent_runs_root: Path | None,
    ge_config: dict[str, Any],
    authority_pins_hash: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    receipt_ingest = ge_config.get("receipt_ingest")
    if not isinstance(receipt_ingest, dict):
        raise _invalid("SCHEMA_FAIL")
    globs = receipt_ingest.get("receipt_globs")
    if not isinstance(globs, list) or not globs:
        raise _invalid("SCHEMA_FAIL")
    max_receipts_u64 = max(1, int(receipt_ingest.get("max_receipts_u64", 1)))

    paths = _collect_matching_paths(
        recent_runs_root=recent_runs_root,
        globs=[str(row) for row in globs],
    )

    receipt_rows: list[tuple[Path, dict[str, Any]]] = []
    refutation_rows: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for path in paths:
        payload = _load_canon_dict(path)
        schema_version = str(payload.get("schema_version", "")).strip()
        if schema_version == "ccap_receipt_v1":
            validate_schema(payload, "ccap_receipt_v1")
            receipt_rows.append((path, payload))
            continue
        if schema_version == "ccap_refutation_cert_v1":
            validate_schema(payload, "ccap_refutation_cert_v1")
            ccap_id = str(payload.get("ccap_id", "")).strip()
            refutation_rows.setdefault(ccap_id, []).append((path, payload))

    receipt_rows = receipt_rows[:max_receipts_u64]

    size_buckets = ge_config.get("proposal_space_patch", {}).get("size_buckets_bytes_u64", [])
    if not isinstance(size_buckets, list) or not size_buckets:
        raise _invalid("SCHEMA_FAIL")

    novelty_cfg = ge_config.get("novelty")
    if not isinstance(novelty_cfg, dict):
        raise _invalid("SCHEMA_FAIL")
    reservoir_size_u64 = max(1, int(novelty_cfg.get("reservoir_size_u64", 1)))

    hard_avoid_cfg = ge_config.get("hard_avoid")
    if not isinstance(hard_avoid_cfg, dict):
        raise _invalid("SCHEMA_FAIL")
    hard_avoid_enabled = bool(hard_avoid_cfg.get("enabled_b", False))
    hard_avoid_codes = {str(row).strip() for row in (hard_avoid_cfg.get("refutation_codes") or [])}
    pd_projection = hard_avoid_cfg.get("pd_projection")
    if not isinstance(pd_projection, dict):
        raise _invalid("SCHEMA_FAIL")
    prefix_hex_u8 = int(pd_projection.get("touched_paths_prefix_hex_u8", 0))

    events: list[dict[str, Any]] = []
    reservoir_beh_ids: list[str] = []
    hard_avoid_entries: set[tuple[str, str]] = set()

    pd_acc: dict[str, dict[str, int | str]] = {}

    for receipt_path, receipt_payload in receipt_rows:
        ccap_id = str(receipt_payload.get("ccap_id", "")).strip()
        refutation_payload = _match_refutation_for_receipt(
            receipt_path=receipt_path,
            ccap_id=ccap_id,
            refutation_map=refutation_rows,
        )
        refutation_code = ""
        if isinstance(refutation_payload, dict):
            refutation_code = str(refutation_payload.get("refutation_code", "")).strip()

        ccap_path = _find_ccap_bundle_path(
            recent_runs_root=recent_runs_root,
            receipt_path=receipt_path,
            ccap_id=ccap_id,
        )
        ccap_payload = _load_canon_dict(ccap_path)
        validate_schema(ccap_payload, "ccap_v1")

        payload_obj = ccap_payload.get("payload")
        if not isinstance(payload_obj, dict) or str(payload_obj.get("kind", "")) != "PATCH":
            raise _invalid("SCHEMA_FAIL")
        patch_blob_id = str(payload_obj.get("patch_blob_id", "")).strip()
        patch_path = _find_patch_path_for_ccap(
            recent_runs_root=recent_runs_root,
            ccap_path=ccap_path,
            patch_blob_id=patch_blob_id,
        )
        patch_bytes = patch_path.read_bytes()

        pd_payload, pd_features = build_pd_from_patch_bytes(
            patch_bytes=patch_bytes,
            base_tree_id=str(receipt_payload.get("base_tree_id", "")).strip(),
            ek_id=str(receipt_payload.get("ek_id", "")).strip(),
            op_pool_id=str(receipt_payload.get("op_pool_id", "")).strip(),
            size_buckets_bytes_u64=[int(row) for row in size_buckets],
        )
        validate_schema(pd_payload, "ge_pd_v1")

        behavior_sig = build_behavior_signature(
            ge_config=ge_config,
            receipt_payload=receipt_payload,
            refutation_code=refutation_code,
        )
        validate_schema(behavior_sig, "ge_behavior_sig_v1")

        novelty_bits = 256
        if reservoir_beh_ids:
            from .sh1_behavior_sig_v1 import novelty_bits as novelty_bits_fn

            novelty_bits = int(
                novelty_bits_fn(
                    beh_id=str(behavior_sig["beh_id"]),
                    reservoir_beh_ids=reservoir_beh_ids[-reservoir_size_u64:],
                )
            )
        reservoir_beh_ids.append(str(behavior_sig["beh_id"]))

        receipt_hash = _hash_obj(receipt_payload)
        event = {
            "ccap_id": ccap_id,
            "receipt_hash": receipt_hash,
            "refutation_code_or_empty": refutation_code,
            "receipt_payload": receipt_payload,
            "refutation_payload": refutation_payload,
            "refutation_code": refutation_code,
            "pd": pd_payload,
            "pd_features": pd_features,
            "behavior_sig": behavior_sig,
            "novelty_bits": int(novelty_bits),
            "receipt_path": receipt_path.as_posix(),
        }
        events.append(event)

        pd_id = str(pd_payload.get("pd_id", "")).strip()
        row = pd_acc.get(pd_id)
        if row is None:
            row = {
                "pd_id": pd_id,
                "seen_u64": 0,
                "promote_u64": 0,
                "reject_u64": 0,
                "busy_fail_u64": 0,
                "logic_fail_u64": 0,
                "safety_fail_u64": 0,
                "cost_cpu_ms_u64": 0,
                "cost_wall_ms_u64": 0,
                "mean_yield_q32": 0,
            }
            pd_acc[pd_id] = row

        row["seen_u64"] = int(row["seen_u64"]) + 1
        if str(receipt_payload.get("decision", "")).strip() == "PROMOTE":
            row["promote_u64"] = int(row["promote_u64"]) + 1
        else:
            row["reject_u64"] = int(row["reject_u64"]) + 1

        sentinel_class = sentinel_class_value(
            ge_config=ge_config,
            receipt_payload=receipt_payload,
            refutation_code=refutation_code,
        )
        if sentinel_class == 1:
            row["busy_fail_u64"] = int(row["busy_fail_u64"]) + 1
        elif sentinel_class == 2:
            row["logic_fail_u64"] = int(row["logic_fail_u64"]) + 1
        elif sentinel_class == 3:
            row["safety_fail_u64"] = int(row["safety_fail_u64"]) + 1

        cost_vector = receipt_payload.get("cost_vector")
        if not isinstance(cost_vector, dict):
            raise _invalid("SCHEMA_FAIL")
        row["cost_cpu_ms_u64"] = int(row["cost_cpu_ms_u64"]) + max(0, int(cost_vector.get("cpu_ms", 0)))
        row["cost_wall_ms_u64"] = int(row["cost_wall_ms_u64"]) + max(0, int(cost_vector.get("wall_ms", 0)))

        if hard_avoid_enabled and refutation_code in hard_avoid_codes:
            touched_paths_hash = str(pd_payload.get("touched_paths_hash", "")).strip()
            prefix = touched_paths_hash_prefix_hex(
                touched_paths_hash=touched_paths_hash,
                prefix_hex_u8=prefix_hex_u8,
            )
            hard_avoid_entries.add((refutation_code, prefix))

    pd_rows: list[dict[str, Any]] = []
    for pd_id in sorted(pd_acc.keys()):
        row = pd_acc[pd_id]
        seen_u64 = max(0, int(row["seen_u64"]))
        promote_u64 = max(0, int(row["promote_u64"]))
        row["mean_yield_q32"] = int(rat_q32(promote_u64, max(1, seen_u64)))
        pd_rows.append(
            {
                "pd_id": pd_id,
                "seen_u64": seen_u64,
                "promote_u64": promote_u64,
                "reject_u64": max(0, int(row["reject_u64"])),
                "busy_fail_u64": max(0, int(row["busy_fail_u64"])),
                "logic_fail_u64": max(0, int(row["logic_fail_u64"])),
                "safety_fail_u64": max(0, int(row["safety_fail_u64"])),
                "cost_cpu_ms_u64": max(0, int(row["cost_cpu_ms_u64"])),
                "cost_wall_ms_u64": max(0, int(row["cost_wall_ms_u64"])),
                "mean_yield_q32": max(0, int(row["mean_yield_q32"])),
            }
        )

    hard_avoid_set = [
        {
            "refutation_code": code,
            "touched_paths_hash_prefix_hex": prefix,
        }
        for code, prefix in sorted(hard_avoid_entries, key=lambda row: (row[0], row[1]))
    ]

    receipt_stream_hash = _event_stream_hash(events)

    snapshot: dict[str, Any] = {
        "schema_version": "ge_xs_snapshot_v1",
        "xs_id": _ZERO_SHA,
        "ge_config_id": str(ge_config.get("ge_config_id", _ZERO_SHA)),
        "authority_pins_hash": str(authority_pins_hash),
        "receipt_stream_hash": receipt_stream_hash,
        "pd_rows": pd_rows,
        "hard_avoid_set": hard_avoid_set,
    }
    snapshot_no_id = dict(snapshot)
    snapshot_no_id.pop("xs_id", None)
    snapshot["xs_id"] = _sha256_prefixed(canon_bytes(snapshot_no_id))
    validate_schema(snapshot, "ge_xs_snapshot_v1")

    return snapshot, events


__all__ = [
    "build_xs_snapshot",
    "load_ge_config",
]
