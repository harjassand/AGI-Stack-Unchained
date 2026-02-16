"""RE2 verifier for Certified Capsule Proposal artifacts (CCAP v1)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..v1_7r.canon import write_canon_json
from .authority.authority_hash_v1 import auth_hash, load_authority_pins
from .ccap_runtime_v1 import (
    ccap_blob_path,
    ccap_payload_id,
    compute_repo_base_tree_id,
    discover_ccap_relpath,
    normalize_subrun_relpath,
    read_patch_blob,
)
from .gir.gir_extract_from_tree_v1 import is_gir_scope_path
from .ek.ek_runner_v1 import run_ek
from .omega_common_v1 import OmegaV18Error, canon_hash_obj, load_canon_dict, validate_schema, write_hashed_json


_ZERO_SHA = "sha256:" + ("0" * 64)


def _normalize_patch_relpath(path_value: str) -> str:
    value = str(path_value).strip().replace("\\", "/")
    if value.startswith("./"):
        value = value[2:]
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise RuntimeError("SCHEMA_FAIL")
    return value


def _prefix_match(path_rel: str, prefix: str) -> bool:
    norm_prefix = str(prefix).strip().replace("\\", "/")
    if norm_prefix.endswith("/"):
        norm_prefix = norm_prefix[:-1]
    if not norm_prefix:
        return False
    return path_rel == norm_prefix or path_rel.startswith(f"{norm_prefix}/")


def _parse_patch_touched_paths(patch_bytes: bytes) -> list[str]:
    touched: list[str] = []
    seen: set[str] = set()
    for raw in patch_bytes.decode("utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line.startswith("+++ "):
            continue
        if line == "+++ /dev/null":
            continue
        if not line.startswith("+++ b/"):
            continue
        rel = line[len("+++ b/") :]
        rel = rel.split("\t", 1)[0].strip()
        if rel.startswith('"') and rel.endswith('"') and len(rel) >= 2:
            rel = rel[1:-1]
        try:
            normalized = _normalize_patch_relpath(rel)
        except RuntimeError:
            normalized = rel
        if normalized and normalized not in seen:
            touched.append(normalized)
            seen.add(normalized)
    return touched


def _load_pinned_patch_allowlists(repo_root: Path, pins: dict[str, Any]) -> dict[str, list[str]]:
    allowlists_path = repo_root / "authority" / "ccap_patch_allowlists_v1.json"
    payload = load_canon_dict(allowlists_path)
    if payload.get("schema_version") != "ccap_patch_allowlists_v1":
        raise RuntimeError("SCHEMA_FAIL")

    expected_allowlists_id = str(pins.get("ccap_patch_allowlists_id", "")).strip()
    if not expected_allowlists_id.startswith("sha256:"):
        raise RuntimeError("SCHEMA_FAIL")
    if canon_hash_obj(payload) != expected_allowlists_id:
        raise RuntimeError("SCHEMA_FAIL")

    allow_prefixes = payload.get("allow_prefixes")
    forbid_prefixes = payload.get("forbid_prefixes")
    forbid_exact_paths = payload.get("forbid_exact_paths")
    if not isinstance(allow_prefixes, list) or not isinstance(forbid_prefixes, list) or not isinstance(forbid_exact_paths, list):
        raise RuntimeError("SCHEMA_FAIL")

    def _normalize_prefixes(rows: list[Any]) -> list[str]:
        out: list[str] = []
        for row in rows:
            value = _normalize_patch_relpath(str(row))
            out.append(value)
        return out

    return {
        "allow_prefixes": _normalize_prefixes(allow_prefixes),
        "forbid_prefixes": _normalize_prefixes(forbid_prefixes),
        "forbid_exact_paths": [_normalize_patch_relpath(str(row)) for row in forbid_exact_paths],
    }


def _path_forbidden_by_allowlists(path_rel: str, allowlists: dict[str, list[str]]) -> bool:
    normalized = _normalize_patch_relpath(path_rel)
    forbid_prefixes = allowlists.get("forbid_prefixes", [])
    forbid_exact_paths = set(allowlists.get("forbid_exact_paths", []))
    allow_prefixes = allowlists.get("allow_prefixes", [])

    if any(_prefix_match(normalized, prefix) for prefix in forbid_prefixes):
        return True
    if normalized in forbid_exact_paths:
        return True
    if not any(_prefix_match(normalized, prefix) for prefix in allow_prefixes):
        return True
    return False


def _resolve_repo_root(repo_root_arg: str | None) -> Path:
    if repo_root_arg and str(repo_root_arg).strip():
        path = Path(str(repo_root_arg)).resolve()
        if path.exists() and path.is_dir():
            return path
    return Path(__file__).resolve().parents[3]


def _resolve_subrun_root(*, cwd: Path, subrun_root_arg: str | None, state_dir_arg: str | None) -> Path:
    if subrun_root_arg and str(subrun_root_arg).strip():
        path = Path(str(subrun_root_arg))
        if not path.is_absolute():
            path = (cwd / path).resolve()
        if path.exists() and path.is_dir():
            return path
    if state_dir_arg and str(state_dir_arg).strip():
        path = Path(str(state_dir_arg))
        if not path.is_absolute():
            path = (cwd / path).resolve()
        if path.exists() and path.is_dir():
            return path
    raise RuntimeError("MISSING_STATE_INPUT")


def _resolve_ccap_path(*, subrun_root: Path, ccap_relpath: str | None) -> tuple[Path, str]:
    if ccap_relpath and str(ccap_relpath).strip():
        rel = normalize_subrun_relpath(str(ccap_relpath))
    else:
        rel = discover_ccap_relpath(subrun_root)
    path = (subrun_root / rel).resolve()
    if not path.exists() or not path.is_file():
        raise RuntimeError("MISSING_STATE_INPUT")
    return path, rel


def _write_refutation_cert(
    *,
    subrun_root: Path,
    ccap_id: str,
    code: str,
    detail: str,
    evidence_hashes: list[str] | None,
) -> tuple[dict[str, Any], str]:
    payload: dict[str, Any] = {
        "schema_version": "ccap_refutation_cert_v1",
        "ccap_id": ccap_id,
        "refutation_code": code,
        "detail": detail,
    }
    if evidence_hashes:
        payload["evidence_hashes"] = list(evidence_hashes)
    validate_schema(payload, "ccap_refutation_cert_v1")
    out_dir = subrun_root / "ccap" / "refutations"
    _, cert, digest = write_hashed_json(out_dir, "ccap_refutation_cert_v1.json", payload)
    write_canon_json(out_dir / "ccap_refutation_cert_v1.json", cert)
    return cert, digest


def _write_realized_receipt(
    *,
    subrun_root: Path,
    ccap_id: str,
    base_tree_id: str,
    applied_tree_id: str,
    realized_out_id: str,
    ek_id: str,
    op_pool_id: str,
    auth_hash_value: str,
    determinism_check: str,
    eval_status: str,
    cost_vector: dict[str, Any],
    logs_hash: str,
) -> tuple[dict[str, Any], str]:
    payload = {
        "schema_version": "realized_capsule_receipt_v1",
        "realized_receipt_id": _ZERO_SHA,
        "ccap_id": ccap_id,
        "base_tree_id": base_tree_id,
        "applied_tree_id": applied_tree_id,
        "realized_out_id": realized_out_id,
        "ek_id": ek_id,
        "op_pool_id": op_pool_id,
        "auth_hash": auth_hash_value,
        "determinism_check": determinism_check,
        "eval_status": eval_status,
        "cost_vector": cost_vector,
        "logs_hash": logs_hash,
    }
    _, realized, digest = write_hashed_json(
        subrun_root / "ccap" / "realized",
        "realized_capsule_receipt_v1.json",
        payload,
        id_field="realized_receipt_id",
    )
    validate_schema(realized, "realized_capsule_receipt_v1")
    write_canon_json(subrun_root / "ccap" / "realized" / "realized_capsule_receipt_v1.json", realized)
    return realized, digest


def _receipt_payload(
    *,
    ccap_id: str,
    base_tree_id: str,
    applied_tree_id: str,
    realized_out_id: str,
    ek_id: str,
    op_pool_id: str,
    auth_hash_value: str,
    determinism_check: str,
    eval_status: str,
    decision: str,
    cost_vector: dict[str, Any],
    logs_hash: str,
    scorecard_summary: dict[str, Any] | None = None,
    score_base_summary: dict[str, Any] | None = None,
    score_cand_summary: dict[str, Any] | None = None,
    score_delta_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "ccap_receipt_v1",
        "ccap_id": ccap_id,
        "base_tree_id": base_tree_id,
        "applied_tree_id": applied_tree_id,
        "realized_out_id": realized_out_id,
        "ek_id": ek_id,
        "op_pool_id": op_pool_id,
        "auth_hash": auth_hash_value,
        "determinism_check": determinism_check,
        "eval_status": eval_status,
        "decision": decision,
        "cost_vector": cost_vector,
        "logs_hash": logs_hash,
    }
    if isinstance(scorecard_summary, dict):
        payload["scorecard_summary"] = {
            "median_stps_non_noop_q32": int(scorecard_summary.get("median_stps_non_noop_q32", 0)),
            "non_noop_ticks_per_min_f64": float(scorecard_summary.get("non_noop_ticks_per_min_f64", 0.0)),
            "promotions_u64": int(scorecard_summary.get("promotions_u64", 0)),
            "activation_success_u64": int(scorecard_summary.get("activation_success_u64", 0)),
        }
    if isinstance(score_base_summary, dict):
        payload["score_base_summary"] = {
            "median_stps_non_noop_q32": int(score_base_summary.get("median_stps_non_noop_q32", 0)),
            "non_noop_ticks_per_min_f64": float(score_base_summary.get("non_noop_ticks_per_min_f64", 0.0)),
            "promotions_u64": int(score_base_summary.get("promotions_u64", 0)),
            "activation_success_u64": int(score_base_summary.get("activation_success_u64", 0)),
        }
    if isinstance(score_cand_summary, dict):
        payload["score_cand_summary"] = {
            "median_stps_non_noop_q32": int(score_cand_summary.get("median_stps_non_noop_q32", 0)),
            "non_noop_ticks_per_min_f64": float(score_cand_summary.get("non_noop_ticks_per_min_f64", 0.0)),
            "promotions_u64": int(score_cand_summary.get("promotions_u64", 0)),
            "activation_success_u64": int(score_cand_summary.get("activation_success_u64", 0)),
        }
    if isinstance(score_delta_summary, dict):
        payload["score_delta_summary"] = {
            "median_stps_non_noop_q32": int(score_delta_summary.get("median_stps_non_noop_q32", 0)),
            "non_noop_ticks_per_min_f64": float(score_delta_summary.get("non_noop_ticks_per_min_f64", 0.0)),
            "promotions_u64": int(score_delta_summary.get("promotions_u64", 0)),
            "activation_success_u64": int(score_delta_summary.get("activation_success_u64", 0)),
        }
    validate_schema(payload, "ccap_receipt_v1")
    return payload


def _write_ccap_receipt(out_dir: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    _, receipt, digest = write_hashed_json(out_dir, "ccap_receipt_v1.json", payload)
    validate_schema(receipt, "ccap_receipt_v1")
    write_canon_json(out_dir / "ccap_receipt_v1.json", receipt)
    return receipt, digest


def _verify_once(
    *,
    subrun_root: Path,
    repo_root: Path,
    ccap_relpath: str,
    receipt_out_dir: Path,
) -> tuple[dict[str, Any], str | None]:
    ccap_path, resolved_ccap_rel = _resolve_ccap_path(subrun_root=subrun_root, ccap_relpath=ccap_relpath)
    ccap = load_canon_dict(ccap_path)
    validate_schema(ccap, "ccap_v1")

    ccap_id = ccap_payload_id(ccap)
    expected_ccap_name = f"sha256_{ccap_id.split(':', 1)[1]}.ccap_v1.json"
    if Path(resolved_ccap_rel).name != expected_ccap_name:
        cert, _ = _write_refutation_cert(
            subrun_root=subrun_root,
            ccap_id=ccap_id,
            code="CANONICALIZATION_MISMATCH",
            detail="ccap path name does not match payload-derived ccap_id",
            evidence_hashes=None,
        )
        payload = _receipt_payload(
            ccap_id=ccap_id,
            base_tree_id=_ZERO_SHA,
            applied_tree_id=_ZERO_SHA,
            realized_out_id="",
            ek_id=_ZERO_SHA,
            op_pool_id=_ZERO_SHA,
            auth_hash_value=_ZERO_SHA,
            determinism_check="REFUTED",
            eval_status="REFUTED",
            decision="REJECT",
            cost_vector={"cpu_ms": 0, "wall_ms": 0, "mem_mb": 0, "disk_mb": 0, "fds": 0, "procs": 0, "threads": 0},
            logs_hash=canon_hash_obj(cert),
        )
        _write_ccap_receipt(receipt_out_dir, payload)
        return payload, "CANONICALIZATION_MISMATCH"
    meta = ccap.get("meta")
    if not isinstance(meta, dict):
        raise RuntimeError("SCHEMA_FAIL")

    pins = load_authority_pins(repo_root)
    expected_auth_hash = auth_hash(pins)
    try:
        patch_allowlists = _load_pinned_patch_allowlists(repo_root, pins)
    except Exception:  # noqa: BLE001
        cert, _ = _write_refutation_cert(
            subrun_root=subrun_root,
            ccap_id=ccap_id,
            code="EVAL_STAGE_FAIL",
            detail="ccap patch allowlists missing, invalid, or hash-pin mismatched",
            evidence_hashes=None,
        )
        payload = _receipt_payload(
            ccap_id=ccap_id,
            base_tree_id=str((ccap.get("meta") or {}).get("base_tree_id", _ZERO_SHA)),
            applied_tree_id=_ZERO_SHA,
            realized_out_id="",
            ek_id=str((ccap.get("meta") or {}).get("ek_id", _ZERO_SHA)),
            op_pool_id=str((ccap.get("meta") or {}).get("op_pool_id", _ZERO_SHA)),
            auth_hash_value=str((ccap.get("meta") or {}).get("auth_hash", _ZERO_SHA)),
            determinism_check="REFUTED",
            eval_status="REFUTED",
            decision="REJECT",
            cost_vector={"cpu_ms": 0, "wall_ms": 0, "mem_mb": 0, "disk_mb": 0, "fds": 0, "procs": 0, "threads": 0},
            logs_hash=canon_hash_obj(cert),
        )
        _write_ccap_receipt(receipt_out_dir, payload)
        return payload, "EVAL_STAGE_FAIL"

    ccap_auth_hash = str(meta.get("auth_hash", "")).strip()
    if ccap_auth_hash != expected_auth_hash:
        cert, _ = _write_refutation_cert(
            subrun_root=subrun_root,
            ccap_id=ccap_id,
            code="AUTH_HASH_MISMATCH",
            detail="ccap.meta.auth_hash does not match current authority pins",
            evidence_hashes=[expected_auth_hash],
        )
        payload = _receipt_payload(
            ccap_id=ccap_id,
            base_tree_id=str(meta.get("base_tree_id", _ZERO_SHA)),
            applied_tree_id=_ZERO_SHA,
            realized_out_id="",
            ek_id=str(meta.get("ek_id", _ZERO_SHA)),
            op_pool_id=str(meta.get("op_pool_id", _ZERO_SHA)),
            auth_hash_value=ccap_auth_hash or _ZERO_SHA,
            determinism_check="REFUTED",
            eval_status="REFUTED",
            decision="REJECT",
            cost_vector={"cpu_ms": 0, "wall_ms": 0, "mem_mb": 0, "disk_mb": 0, "fds": 0, "procs": 0, "threads": 0},
            logs_hash=canon_hash_obj(cert),
        )
        _write_ccap_receipt(receipt_out_dir, payload)
        return payload, "AUTH_HASH_MISMATCH"

    active_op_pool_ids = pins.get("active_op_pool_ids")
    if not isinstance(active_op_pool_ids, list) or str(meta.get("op_pool_id", "")) not in {str(v) for v in active_op_pool_ids}:
        cert, _ = _write_refutation_cert(
            subrun_root=subrun_root,
            ccap_id=ccap_id,
            code="OP_POOL_NOT_ACTIVE",
            detail="ccap.meta.op_pool_id is not in authority active_op_pool_ids",
            evidence_hashes=None,
        )
        payload = _receipt_payload(
            ccap_id=ccap_id,
            base_tree_id=str(meta.get("base_tree_id", _ZERO_SHA)),
            applied_tree_id=_ZERO_SHA,
            realized_out_id="",
            ek_id=str(meta.get("ek_id", _ZERO_SHA)),
            op_pool_id=str(meta.get("op_pool_id", _ZERO_SHA)),
            auth_hash_value=ccap_auth_hash,
            determinism_check="REFUTED",
            eval_status="REFUTED",
            decision="REJECT",
            cost_vector={"cpu_ms": 0, "wall_ms": 0, "mem_mb": 0, "disk_mb": 0, "fds": 0, "procs": 0, "threads": 0},
            logs_hash=canon_hash_obj(cert),
        )
        _write_ccap_receipt(receipt_out_dir, payload)
        return payload, "OP_POOL_NOT_ACTIVE"

    canon_version_ids = meta.get("canon_version_ids")
    if not isinstance(canon_version_ids, dict) or canon_version_ids != pins.get("canon_version_ids"):
        cert, _ = _write_refutation_cert(
            subrun_root=subrun_root,
            ccap_id=ccap_id,
            code="CANON_VERSION_MISMATCH",
            detail="ccap.meta.canon_version_ids do not match authority pins",
            evidence_hashes=None,
        )
        payload = _receipt_payload(
            ccap_id=ccap_id,
            base_tree_id=str(meta.get("base_tree_id", _ZERO_SHA)),
            applied_tree_id=_ZERO_SHA,
            realized_out_id="",
            ek_id=str(meta.get("ek_id", _ZERO_SHA)),
            op_pool_id=str(meta.get("op_pool_id", _ZERO_SHA)),
            auth_hash_value=ccap_auth_hash,
            determinism_check="REFUTED",
            eval_status="REFUTED",
            decision="REJECT",
            cost_vector={"cpu_ms": 0, "wall_ms": 0, "mem_mb": 0, "disk_mb": 0, "fds": 0, "procs": 0, "threads": 0},
            logs_hash=canon_hash_obj(cert),
        )
        _write_ccap_receipt(receipt_out_dir, payload)
        return payload, "CANON_VERSION_MISMATCH"

    base_tree_id = compute_repo_base_tree_id(repo_root)
    if str(meta.get("base_tree_id", "")) != base_tree_id:
        cert, _ = _write_refutation_cert(
            subrun_root=subrun_root,
            ccap_id=ccap_id,
            code="BASE_TREE_MISMATCH",
            detail="ccap.meta.base_tree_id does not match repository base tree",
            evidence_hashes=[base_tree_id],
        )
        payload = _receipt_payload(
            ccap_id=ccap_id,
            base_tree_id=base_tree_id,
            applied_tree_id=_ZERO_SHA,
            realized_out_id="",
            ek_id=str(meta.get("ek_id", _ZERO_SHA)),
            op_pool_id=str(meta.get("op_pool_id", _ZERO_SHA)),
            auth_hash_value=ccap_auth_hash,
            determinism_check="REFUTED",
            eval_status="REFUTED",
            decision="REJECT",
            cost_vector={"cpu_ms": 0, "wall_ms": 0, "mem_mb": 0, "disk_mb": 0, "fds": 0, "procs": 0, "threads": 0},
            logs_hash=canon_hash_obj(cert),
        )
        _write_ccap_receipt(receipt_out_dir, payload)
        return payload, "BASE_TREE_MISMATCH"

    payload_obj = ccap.get("payload")
    if not isinstance(payload_obj, dict):
        raise RuntimeError("SCHEMA_FAIL")
    payload_kind = str(payload_obj.get("kind", "")).strip()
    if payload_kind not in {"PATCH", "ACTIONSEQ", "GIR"}:
        cert, _ = _write_refutation_cert(
            subrun_root=subrun_root,
            ccap_id=ccap_id,
            code="PAYLOAD_KIND_UNSUPPORTED",
            detail=f"payload kind unsupported in v0.2: {payload_kind}",
            evidence_hashes=None,
        )
        payload = _receipt_payload(
            ccap_id=ccap_id,
            base_tree_id=base_tree_id,
            applied_tree_id=_ZERO_SHA,
            realized_out_id="",
            ek_id=str(meta.get("ek_id", _ZERO_SHA)),
            op_pool_id=str(meta.get("op_pool_id", _ZERO_SHA)),
            auth_hash_value=ccap_auth_hash,
            determinism_check="REFUTED",
            eval_status="REFUTED",
            decision="REJECT",
            cost_vector={"cpu_ms": 0, "wall_ms": 0, "mem_mb": 0, "disk_mb": 0, "fds": 0, "procs": 0, "threads": 0},
            logs_hash=canon_hash_obj(cert),
        )
        _write_ccap_receipt(receipt_out_dir, payload)
        return payload, "PAYLOAD_KIND_UNSUPPORTED"

    if payload_kind == "PATCH":
        patch_blob_id = str(payload_obj.get("patch_blob_id", "")).strip()
        try:
            patch_bytes = read_patch_blob(subrun_root=subrun_root, patch_blob_id=patch_blob_id)
        except OmegaV18Error:
            cert, _ = _write_refutation_cert(
                subrun_root=subrun_root,
                ccap_id=ccap_id,
                code="PATCH_HASH_MISMATCH",
                detail="patch blob does not exist or hash does not match ccap payload",
                evidence_hashes=[patch_blob_id] if patch_blob_id.startswith("sha256:") else None,
            )
            payload = _receipt_payload(
                ccap_id=ccap_id,
                base_tree_id=base_tree_id,
                applied_tree_id=_ZERO_SHA,
                realized_out_id="",
                ek_id=str(meta.get("ek_id", _ZERO_SHA)),
                op_pool_id=str(meta.get("op_pool_id", _ZERO_SHA)),
                auth_hash_value=ccap_auth_hash,
                determinism_check="REFUTED",
                eval_status="REFUTED",
                decision="REJECT",
                cost_vector={"cpu_ms": 0, "wall_ms": 0, "mem_mb": 0, "disk_mb": 0, "fds": 0, "procs": 0, "threads": 0},
                logs_hash=canon_hash_obj(cert),
            )
            _write_ccap_receipt(receipt_out_dir, payload)
            return payload, "PATCH_HASH_MISMATCH"
        touched_paths = _parse_patch_touched_paths(patch_bytes)
        if not touched_paths:
            cert, _ = _write_refutation_cert(
                subrun_root=subrun_root,
                ccap_id=ccap_id,
                code="FORBIDDEN_PATH",
                detail="patch does not declare any touched paths via unified diff headers",
                evidence_hashes=None,
            )
            payload = _receipt_payload(
                ccap_id=ccap_id,
                base_tree_id=base_tree_id,
                applied_tree_id=_ZERO_SHA,
                realized_out_id="",
                ek_id=str(meta.get("ek_id", _ZERO_SHA)),
                op_pool_id=str(meta.get("op_pool_id", _ZERO_SHA)),
                auth_hash_value=ccap_auth_hash,
                determinism_check="REFUTED",
                eval_status="REFUTED",
                decision="REJECT",
                cost_vector={"cpu_ms": 0, "wall_ms": 0, "mem_mb": 0, "disk_mb": 0, "fds": 0, "procs": 0, "threads": 0},
                logs_hash=canon_hash_obj(cert),
            )
            _write_ccap_receipt(receipt_out_dir, payload)
            return payload, "FORBIDDEN_PATH"
        for touched_path in touched_paths:
            try:
                forbidden = _path_forbidden_by_allowlists(touched_path, patch_allowlists)
            except RuntimeError:
                forbidden = True
            if forbidden:
                cert, _ = _write_refutation_cert(
                    subrun_root=subrun_root,
                    ccap_id=ccap_id,
                    code="FORBIDDEN_PATH",
                    detail=f"patch touches forbidden or unallowlisted path: {touched_path}",
                    evidence_hashes=None,
                )
                payload = _receipt_payload(
                    ccap_id=ccap_id,
                    base_tree_id=base_tree_id,
                    applied_tree_id=_ZERO_SHA,
                    realized_out_id="",
                    ek_id=str(meta.get("ek_id", _ZERO_SHA)),
                    op_pool_id=str(meta.get("op_pool_id", _ZERO_SHA)),
                    auth_hash_value=ccap_auth_hash,
                    determinism_check="REFUTED",
                    eval_status="REFUTED",
                    decision="REJECT",
                    cost_vector={"cpu_ms": 0, "wall_ms": 0, "mem_mb": 0, "disk_mb": 0, "fds": 0, "procs": 0, "threads": 0},
                    logs_hash=canon_hash_obj(cert),
                )
                _write_ccap_receipt(receipt_out_dir, payload)
                return payload, "FORBIDDEN_PATH"
    elif payload_kind == "GIR":
        gir_blob_id = str(payload_obj.get("gir_blob_id", "")).strip()
        try:
            path = ccap_blob_path(subrun_root=subrun_root, blob_id=gir_blob_id, suffix=".bin")
            if not path.exists() or not path.is_file():
                raise OmegaV18Error("INVALID:PATCH_HASH_MISMATCH")
        except OmegaV18Error:
            cert, _ = _write_refutation_cert(
                subrun_root=subrun_root,
                ccap_id=ccap_id,
                code="PATCH_HASH_MISMATCH",
                detail="GIR blob is missing or invalid",
                evidence_hashes=[gir_blob_id] if gir_blob_id.startswith("sha256:") else None,
            )
            payload = _receipt_payload(
                ccap_id=ccap_id,
                base_tree_id=base_tree_id,
                applied_tree_id=_ZERO_SHA,
                realized_out_id="",
                ek_id=str(meta.get("ek_id", _ZERO_SHA)),
                op_pool_id=str(meta.get("op_pool_id", _ZERO_SHA)),
                auth_hash_value=ccap_auth_hash,
                determinism_check="REFUTED",
                eval_status="REFUTED",
                decision="REJECT",
                cost_vector={"cpu_ms": 0, "wall_ms": 0, "mem_mb": 0, "disk_mb": 0, "fds": 0, "procs": 0, "threads": 0},
                logs_hash=canon_hash_obj(cert),
            )
            _write_ccap_receipt(receipt_out_dir, payload)
            return payload, "PATCH_HASH_MISMATCH"
    else:  # ACTIONSEQ
        action_seq = payload_obj.get("action_seq")
        steps = action_seq.get("steps") if isinstance(action_seq, dict) else None
        if not isinstance(steps, list):
            raise RuntimeError("SCHEMA_FAIL")
        for step in steps:
            if not isinstance(step, dict):
                raise RuntimeError("SCHEMA_FAIL")
            op_id = str(step.get("op_id", "")).strip()
            if op_id == "OP_ADD_TEST_FILE":
                continue
            site = str(step.get("site", "")).strip()
            rel = site.split("::", 1)[0].strip().replace("\\", "/")
            if not rel or not is_gir_scope_path(rel):
                cert, _ = _write_refutation_cert(
                    subrun_root=subrun_root,
                    ccap_id=ccap_id,
                    code="PAYLOAD_KIND_UNSUPPORTED",
                    detail=f"ACTIONSEQ site outside GIR scope: {rel}",
                    evidence_hashes=None,
                )
                payload = _receipt_payload(
                    ccap_id=ccap_id,
                    base_tree_id=base_tree_id,
                    applied_tree_id=_ZERO_SHA,
                    realized_out_id="",
                    ek_id=str(meta.get("ek_id", _ZERO_SHA)),
                    op_pool_id=str(meta.get("op_pool_id", _ZERO_SHA)),
                    auth_hash_value=ccap_auth_hash,
                    determinism_check="REFUTED",
                    eval_status="REFUTED",
                    decision="REJECT",
                    cost_vector={"cpu_ms": 0, "wall_ms": 0, "mem_mb": 0, "disk_mb": 0, "fds": 0, "procs": 0, "threads": 0},
                    logs_hash=canon_hash_obj(cert),
                )
                _write_ccap_receipt(receipt_out_dir, payload)
                return payload, "PAYLOAD_KIND_UNSUPPORTED"

    ek_result = run_ek(
        repo_root=repo_root,
        subrun_root=subrun_root,
        ccap_id=ccap_id,
        ccap=ccap,
        out_dir=subrun_root / "ccap" / "ek_runs" / ccap_id.split(":", 1)[1][:16],
    )

    determinism_check = str(ek_result.get("determinism_check", "REFUTED"))
    eval_status = str(ek_result.get("eval_status", "REFUTED"))
    decision = str(ek_result.get("decision", "REJECT"))
    applied_tree_id = str(ek_result.get("applied_tree_id", _ZERO_SHA))
    realized_out_id = str(ek_result.get("realized_out_id", ""))
    cost_vector = ek_result.get("cost_vector")
    if not isinstance(cost_vector, dict):
        cost_vector = {"cpu_ms": 0, "wall_ms": 0, "mem_mb": 0, "disk_mb": 0, "fds": 0, "procs": 0, "threads": 0}
    logs_hash = str(ek_result.get("logs_hash", _ZERO_SHA))
    scorecard_summary = ek_result.get("scorecard_summary")
    if not isinstance(scorecard_summary, dict):
        scorecard_summary = None
    score_base_summary = ek_result.get("score_base_summary")
    if not isinstance(score_base_summary, dict):
        score_base_summary = None
    score_cand_summary = ek_result.get("score_cand_summary")
    if not isinstance(score_cand_summary, dict):
        score_cand_summary = None
    score_delta_summary = ek_result.get("score_delta_summary")
    if not isinstance(score_delta_summary, dict):
        score_delta_summary = None

    refutation = ek_result.get("refutation")
    refutation_code: str | None = None
    if isinstance(refutation, dict):
        code = str(refutation.get("code", "EVAL_STAGE_FAIL")).strip() or "EVAL_STAGE_FAIL"
        detail = str(refutation.get("detail", "evaluation kernel stage failed")).strip() or "evaluation kernel stage failed"
        evidence = refutation.get("evidence_hashes")
        evidence_hashes = [str(row) for row in evidence] if isinstance(evidence, list) else None
        _write_refutation_cert(
            subrun_root=subrun_root,
            ccap_id=ccap_id,
            code=code,
            detail=detail,
            evidence_hashes=evidence_hashes,
        )
        refutation_code = code

    receipt_payload = _receipt_payload(
        ccap_id=ccap_id,
        base_tree_id=base_tree_id,
        applied_tree_id=applied_tree_id,
        realized_out_id=realized_out_id,
        ek_id=str(meta.get("ek_id", _ZERO_SHA)),
        op_pool_id=str(meta.get("op_pool_id", _ZERO_SHA)),
        auth_hash_value=ccap_auth_hash,
        determinism_check=determinism_check,
        eval_status=eval_status,
        decision=decision,
        cost_vector=cost_vector,
        logs_hash=logs_hash,
        scorecard_summary=scorecard_summary,
        score_base_summary=score_base_summary,
        score_cand_summary=score_cand_summary,
        score_delta_summary=score_delta_summary,
    )
    _write_ccap_receipt(receipt_out_dir, receipt_payload)

    if decision == "PROMOTE":
        _write_realized_receipt(
            subrun_root=subrun_root,
            ccap_id=ccap_id,
            base_tree_id=base_tree_id,
            applied_tree_id=applied_tree_id,
            realized_out_id=realized_out_id,
            ek_id=str(meta.get("ek_id", _ZERO_SHA)),
            op_pool_id=str(meta.get("op_pool_id", _ZERO_SHA)),
            auth_hash_value=ccap_auth_hash,
            determinism_check=determinism_check,
            eval_status=eval_status,
            cost_vector=cost_vector,
            logs_hash=logs_hash,
        )

    return receipt_payload, refutation_code


def verify(
    *,
    subrun_root: Path,
    repo_root: Path,
    ccap_relpath: str | None,
    receipt_out_dir: Path,
) -> tuple[dict[str, Any], str | None]:
    receipt, code = _verify_once(
        subrun_root=subrun_root,
        repo_root=repo_root,
        ccap_relpath=(ccap_relpath if ccap_relpath else discover_ccap_relpath(subrun_root)),
        receipt_out_dir=receipt_out_dir,
    )
    return receipt, code


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_ccap_v1")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--state_dir", required=False)
    parser.add_argument("--subrun_root", required=False)
    parser.add_argument("--repo_root", required=False)
    parser.add_argument("--ccap_relpath", required=False)
    parser.add_argument("--receipt_out_dir", required=False)
    parser.add_argument("--enable_ccap", required=False, default="0")
    args = parser.parse_args()

    if str(args.mode) != "full":
        print("INVALID:MODE_UNSUPPORTED")
        raise SystemExit(1)
    if str(args.enable_ccap).strip() != "1":
        print("INVALID:CCAP_DISABLED")
        raise SystemExit(1)

    cwd = Path.cwd().resolve()
    try:
        repo_root = _resolve_repo_root(args.repo_root)
        subrun_root = _resolve_subrun_root(cwd=cwd, subrun_root_arg=args.subrun_root, state_dir_arg=args.state_dir)
        ccap_relpath = str(args.ccap_relpath).strip() if args.ccap_relpath else None

        if args.receipt_out_dir and str(args.receipt_out_dir).strip():
            receipt_out_dir = Path(str(args.receipt_out_dir))
            if not receipt_out_dir.is_absolute():
                receipt_out_dir = (cwd / receipt_out_dir).resolve()
        else:
            receipt_out_dir = subrun_root / "verifier"
        receipt_out_dir.mkdir(parents=True, exist_ok=True)

        _receipt, _code = verify(
            subrun_root=subrun_root,
            repo_root=repo_root,
            ccap_relpath=ccap_relpath,
            receipt_out_dir=receipt_out_dir,
        )
        print("VALID")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).strip()
        if msg.startswith("INVALID:"):
            print(msg)
        else:
            print("INVALID:VERIFY_ERROR")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
