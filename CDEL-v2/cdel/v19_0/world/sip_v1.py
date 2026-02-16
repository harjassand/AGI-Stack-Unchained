"""Sealed ingestion protocol (SIP) verifier for v19.0 world snapshots."""

from __future__ import annotations

import hashlib
import math
from typing import Any

from ..common_v1 import (
    BudgetExhausted,
    BudgetMeter,
    budget_outcome,
    canon_hash_obj,
    ensure_sha256,
    fail,
    require_budget_spec,
    validate_schema,
    verify_object_id,
)
from ...v1_7r.canon import canon_bytes, loads
from .check_world_task_binding_v1 import check_world_task_binding
from .merkle_v1 import ordered_entries, compute_world_root


def _ensure_bytes_by_content_id(raw_map: Any) -> dict[str, bytes]:
    if not isinstance(raw_map, dict):
        fail("SCHEMA_FAIL")
    out: dict[str, bytes] = {}
    for key, value in raw_map.items():
        content_id = ensure_sha256(key, reason="SCHEMA_FAIL")
        if isinstance(value, bytes):
            out[content_id] = value
        elif isinstance(value, bytearray):
            out[content_id] = bytes(value)
        else:
            fail("SCHEMA_FAIL")
    return out


def _entropy_q16(data: bytes) -> int:
    if not data:
        return 0
    counts = [0] * 256
    for byte in data:
        counts[byte] += 1
    total = len(data)
    entropy = 0.0
    for count in counts:
        if count == 0:
            continue
        p = count / total
        entropy -= p * math.log2(p)
    return int(round(entropy * (1 << 16)))


def _scan_leakage(
    *,
    entries: list[dict[str, Any]],
    artifact_bytes_by_content_id: dict[str, bytes],
    forbidden_patterns: list[str],
    max_entropy_q16: int | None,
    meter: BudgetMeter,
) -> tuple[list[str], list[str]]:
    scanned: list[str] = []
    flags: list[str] = []
    pattern_bytes = [pattern.encode("utf-8") for pattern in forbidden_patterns]

    for row in entries:
        content_id = ensure_sha256(row.get("content_id"), reason="SCHEMA_FAIL")
        blob = artifact_bytes_by_content_id.get(content_id)
        if blob is None:
            fail("MISSING_INPUT")
        meter.consume(steps=1, bytes_read=len(blob), items=1)
        scanned.append(content_id)

        idx = 0
        while idx < len(pattern_bytes):
            pat = pattern_bytes[idx]
            if pat and pat in blob:
                flags.append(f"{content_id}:FORBIDDEN_PATTERN:{forbidden_patterns[idx]}")
            idx += 1

        if max_entropy_q16 is not None:
            ent_q16 = _entropy_q16(blob)
            if ent_q16 > max_entropy_q16:
                flags.append(f"{content_id}:ENTROPY_Q16:{ent_q16}")

    return scanned, flags


def _validate_manifest_content(
    *,
    manifest: dict[str, Any],
    artifact_bytes_by_content_id: dict[str, bytes],
    meter: BudgetMeter,
) -> list[dict[str, Any]]:
    validate_schema(manifest, "world_snapshot_manifest_v1")
    verify_object_id(manifest, id_field="manifest_id")
    rows = ordered_entries(manifest.get("entries"), enforce_sorted=True)

    for row in rows:
        content_id = ensure_sha256(row.get("content_id"), reason="SCHEMA_FAIL")
        blob = artifact_bytes_by_content_id.get(content_id)
        if blob is None:
            fail("MISSING_INPUT")
        meter.consume(steps=1, bytes_read=len(blob), items=1)

        expected_len = int(row.get("content_length_bytes", -1))
        if expected_len != len(blob):
            fail("HASH_MISMATCH")
        observed = "sha256:" + hashlib.sha256(blob).hexdigest()
        if observed != content_id:
            fail("HASH_MISMATCH")

        content_kind = str(row.get("content_kind", "")).strip()
        if content_kind == "CANON_JSON":
            parsed = loads(blob)
            if canon_bytes(parsed) != blob:
                fail("HASH_MISMATCH")
            canon_version = row.get("canon_version")
            if not isinstance(canon_version, str) or not canon_version.strip():
                fail("SCHEMA_FAIL")

    return rows


def _build_receipt(
    *,
    sip_profile_id: str,
    manifest_id: str,
    canonicalization_profile_ids: list[str],
    input_artifact_ids: list[str],
    computed_world_root: str,
    leakage_gate: dict[str, Any],
    non_interference_gate: dict[str, Any],
    budget_spec: dict[str, Any],
    outcome: str,
    reason_code: str,
) -> dict[str, Any]:
    payload = {
        "schema_name": "sealed_ingestion_receipt_v1",
        "schema_version": "v19_0",
        "sip_profile_id": sip_profile_id,
        "input_artifact_ids": input_artifact_ids,
        "canonicalization_profile_ids": canonicalization_profile_ids,
        "world_manifest_ref": manifest_id,
        "computed_world_root": computed_world_root,
        "gate_results": {
            "leakage_gate": leakage_gate,
            "non_interference_gate": non_interference_gate,
        },
        "budgets": dict(budget_spec),
        "outcome": outcome,
        "reason_code": reason_code,
    }
    receipt = dict(payload)
    receipt["receipt_id"] = canon_hash_obj(payload)
    validate_schema(receipt, "sealed_ingestion_receipt_v1")
    verify_object_id(receipt, id_field="receipt_id")
    return receipt


def run_sip(
    *,
    manifest: dict[str, Any],
    artifact_bytes_by_content_id: dict[str, bytes] | dict[str, bytearray],
    sip_profile: dict[str, Any],
    world_task_bindings: list[dict[str, Any]],
    world_snapshot_id: str,
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    budget = require_budget_spec(budget_spec)
    meter = BudgetMeter(budget)

    manifest_id = verify_object_id(manifest, id_field="manifest_id")
    world_snapshot_id = ensure_sha256(world_snapshot_id, reason="SCHEMA_FAIL")
    artifacts = _ensure_bytes_by_content_id(artifact_bytes_by_content_id)

    if not isinstance(sip_profile, dict):
        fail("SCHEMA_FAIL")
    sip_profile_id = ensure_sha256(sip_profile.get("sip_profile_id"), reason="SCHEMA_FAIL")

    canon_profiles_raw = sip_profile.get("canonicalization_profile_ids", [])
    if not isinstance(canon_profiles_raw, list) or not canon_profiles_raw:
        fail("SCHEMA_FAIL")
    canonicalization_profile_ids = [ensure_sha256(value, reason="SCHEMA_FAIL") for value in canon_profiles_raw]

    leakage_policy = sip_profile.get("leakage_policy")
    if leakage_policy is None:
        leakage_policy = {}
    if not isinstance(leakage_policy, dict):
        fail("SCHEMA_FAIL")

    forbidden_patterns_raw = leakage_policy.get("forbidden_patterns", [])
    if not isinstance(forbidden_patterns_raw, list):
        fail("SCHEMA_FAIL")
    forbidden_patterns: list[str] = []
    for pattern in forbidden_patterns_raw:
        if not isinstance(pattern, str):
            fail("SCHEMA_FAIL")
        forbidden_patterns.append(pattern)

    max_entropy_q16_raw = leakage_policy.get("max_entropy_q16")
    max_entropy_q16: int | None = None
    if max_entropy_q16_raw is not None:
        max_entropy_q16 = int(max_entropy_q16_raw)
        if max_entropy_q16 < 0:
            fail("SCHEMA_FAIL")

    leakage_on_detect = str(leakage_policy.get("on_detect", "SAFE_HALT")).strip()
    if leakage_on_detect not in {"REJECT", "SAFE_HALT"}:
        fail("SCHEMA_FAIL")

    try:
        entries = _validate_manifest_content(
            manifest=manifest,
            artifact_bytes_by_content_id=artifacts,
            meter=meter,
        )
        computed_world_root = compute_world_root(manifest, enforce_sorted=True)

        scanned_entry_ids, leakage_flags = _scan_leakage(
            entries=entries,
            artifact_bytes_by_content_id=artifacts,
            forbidden_patterns=forbidden_patterns,
            max_entropy_q16=max_entropy_q16,
            meter=meter,
        )

        leakage_outcome = "ACCEPT"
        if leakage_flags:
            leakage_outcome = leakage_on_detect

        non_interference_flags: list[str] = []
        non_interference_outcome = "ACCEPT"
        binding_ids: list[str] = []
        if not isinstance(world_task_bindings, list):
            fail("SCHEMA_FAIL")
        for binding in world_task_bindings:
            meter.consume(steps=1, items=1)
            if not isinstance(binding, dict):
                fail("SCHEMA_FAIL")
            if ensure_sha256(binding.get("world_snapshot_id"), reason="SCHEMA_FAIL") != world_snapshot_id:
                non_interference_outcome = "SAFE_HALT"
                non_interference_flags.append("WORLD_SNAPSHOT_MISMATCH")
                continue
            receipt = check_world_task_binding(
                binding=binding,
                manifest=manifest,
                world_snapshot=None,
                budget_spec=budget,
            )
            binding_id = ensure_sha256(binding.get("binding_id"), reason="SCHEMA_FAIL")
            binding_ids.append(binding_id)
            if receipt.get("outcome") != "ACCEPT":
                non_interference_outcome = "SAFE_HALT"
                non_interference_flags.append(
                    f"{binding_id}:{str(receipt.get('reason_code', 'NON_INTERFERENCE_FAIL'))}"
                )

        leakage_gate = {
            "scanned_entry_ids": scanned_entry_ids,
            "flags": leakage_flags,
            "outcome": leakage_outcome,
        }
        non_interference_gate = {
            "scanned_entry_ids": binding_ids,
            "flags": non_interference_flags,
            "outcome": non_interference_outcome,
        }

        input_artifact_ids = sorted(
            {manifest_id, sip_profile_id, *binding_ids, *[ensure_sha256(r.get("content_id"), reason="SCHEMA_FAIL") for r in entries]}
        )

        if leakage_outcome == "REJECT":
            return _build_receipt(
                sip_profile_id=sip_profile_id,
                manifest_id=manifest_id,
                canonicalization_profile_ids=canonicalization_profile_ids,
                input_artifact_ids=input_artifact_ids,
                computed_world_root=computed_world_root,
                leakage_gate=leakage_gate,
                non_interference_gate=non_interference_gate,
                budget_spec=budget,
                outcome="REJECT",
                reason_code="LEAKAGE_DETECTED",
            )

        if leakage_outcome != "ACCEPT":
            return _build_receipt(
                sip_profile_id=sip_profile_id,
                manifest_id=manifest_id,
                canonicalization_profile_ids=canonicalization_profile_ids,
                input_artifact_ids=input_artifact_ids,
                computed_world_root=computed_world_root,
                leakage_gate=leakage_gate,
                non_interference_gate=non_interference_gate,
                budget_spec=budget,
                outcome="SAFE_HALT",
                reason_code="LEAKAGE_DETECTED",
            )

        if non_interference_outcome != "ACCEPT":
            return _build_receipt(
                sip_profile_id=sip_profile_id,
                manifest_id=manifest_id,
                canonicalization_profile_ids=canonicalization_profile_ids,
                input_artifact_ids=input_artifact_ids,
                computed_world_root=computed_world_root,
                leakage_gate=leakage_gate,
                non_interference_gate=non_interference_gate,
                budget_spec=budget,
                outcome="SAFE_HALT",
                reason_code="NON_INTERFERENCE_FAIL",
            )

        return _build_receipt(
            sip_profile_id=sip_profile_id,
            manifest_id=manifest_id,
            canonicalization_profile_ids=canonicalization_profile_ids,
            input_artifact_ids=input_artifact_ids,
            computed_world_root=computed_world_root,
            leakage_gate=leakage_gate,
            non_interference_gate=non_interference_gate,
            budget_spec=budget,
            outcome="ACCEPT",
            reason_code="GATES_PASS",
        )
    except BudgetExhausted:
        return _build_receipt(
            sip_profile_id=sip_profile_id,
            manifest_id=manifest_id,
            canonicalization_profile_ids=canonicalization_profile_ids,
            input_artifact_ids=sorted({manifest_id, sip_profile_id}),
            computed_world_root="sha256:" + ("0" * 64),
            leakage_gate={"scanned_entry_ids": [], "flags": [], "outcome": "SAFE_HALT"},
            non_interference_gate={"scanned_entry_ids": [], "flags": [], "outcome": "SAFE_HALT"},
            budget_spec=budget,
            outcome=budget_outcome(budget["policy"], allow_safe_split=False),
            reason_code="BUDGET_EXHAUSTED",
        )


__all__ = ["run_sip"]
