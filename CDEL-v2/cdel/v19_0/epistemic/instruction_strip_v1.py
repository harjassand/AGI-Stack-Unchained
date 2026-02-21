"""Deterministic instruction stripping for epistemic reducer commit path."""

from __future__ import annotations

import unicodedata
from typing import Any

from ..common_v1 import canon_hash_obj, ensure_sha256, fail, hash_bytes, validate_schema, verify_object_id


def default_instruction_strip_contract() -> dict[str, Any]:
    payload = {
        "schema_version": "epistemic_instruction_strip_contract_v1",
        "contract_id": "sha256:" + ("0" * 64),
        "unicode_normalization": "NFC",
        "whitespace_policy": "PRESERVE_LINES",
        "pattern_engine_semantics": "LOWERCASE_SUBSTRING_MATCH_V1",
        "rule_version": "RULESET_V1",
        "strip_tokens": [
            "ignore previous instructions",
            "system prompt",
            "developer instructions",
            "tool call",
            "act as ",
            "you are chatgpt",
            "<script",
            "javascript:",
        ],
        "removed_span_binding_mode": "REMOVED_LINE_HASHES_V1",
        "tie_break_policy": "INPUT_ORDER_ASC",
    }
    payload["contract_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "contract_id"})
    validate_schema(payload, "epistemic_instruction_strip_contract_v1")
    verify_object_id(payload, id_field="contract_id")
    return payload


def _apply_line_normalization(*, text: str, unicode_normalization: str) -> str:
    if unicode_normalization == "NFC":
        return unicodedata.normalize("NFC", text)
    fail("SCHEMA_FAIL")
    return text


def apply_instruction_strip(
    *,
    input_bytes: bytes,
    contract: dict[str, Any],
) -> tuple[bytes, list[str]]:
    validate_schema(contract, "epistemic_instruction_strip_contract_v1")
    verify_object_id(contract, id_field="contract_id")
    if str(contract.get("unicode_normalization", "")) != "NFC":
        fail("SCHEMA_FAIL")
    if str(contract.get("whitespace_policy", "")) != "PRESERVE_LINES":
        fail("SCHEMA_FAIL")
    if str(contract.get("pattern_engine_semantics", "")) != "LOWERCASE_SUBSTRING_MATCH_V1":
        fail("SCHEMA_FAIL")
    if str(contract.get("rule_version", "")) != "RULESET_V1":
        fail("SCHEMA_FAIL")
    if str(contract.get("removed_span_binding_mode", "")) != "REMOVED_LINE_HASHES_V1":
        fail("SCHEMA_FAIL")
    if str(contract.get("tie_break_policy", "")) != "INPUT_ORDER_ASC":
        fail("SCHEMA_FAIL")
    token_rows = contract.get("strip_tokens")
    if not isinstance(token_rows, list) or not token_rows:
        fail("SCHEMA_FAIL")
    strip_tokens: list[str] = []
    for row in token_rows:
        token = str(row).strip().lower()
        if not token:
            fail("SCHEMA_FAIL")
        strip_tokens.append(token)
    if len(strip_tokens) != len(set(strip_tokens)):
        fail("SCHEMA_FAIL")

    text = input_bytes.decode("utf-8", errors="replace")
    kept_lines: list[str] = []
    removed_span_hashes: list[str] = []
    for raw_line in text.splitlines():
        line = _apply_line_normalization(text=str(raw_line), unicode_normalization="NFC")
        line_lower = line.lower()
        if any(token in line_lower for token in strip_tokens):
            removed_span_hashes.append(
                canon_hash_obj(
                    {
                        "schema_version": "epistemic_instruction_removed_line_v1",
                        "line": line,
                    }
                )
            )
            continue
        kept_lines.append(line)
    output_bytes = "\n".join(kept_lines).encode("utf-8")
    return output_bytes, removed_span_hashes


def build_instruction_strip_receipt(
    *,
    input_blob_id: str,
    output_blob_id: str,
    instruction_strip_contract_id: str,
    removed_span_hashes: list[str],
    outcome: str = "OK",
) -> dict[str, Any]:
    input_blob_id = ensure_sha256(input_blob_id, reason="SCHEMA_FAIL")
    output_blob_id = ensure_sha256(output_blob_id, reason="SCHEMA_FAIL")
    instruction_strip_contract_id = ensure_sha256(instruction_strip_contract_id, reason="SCHEMA_FAIL")
    if str(outcome) not in {"OK", "SAFE_HALT"}:
        fail("SCHEMA_FAIL")
    ordered_removed_hashes = [ensure_sha256(v, reason="SCHEMA_FAIL") for v in list(removed_span_hashes)]
    removed_spans_hash = canon_hash_obj(
        {
            "schema_version": "epistemic_instruction_removed_span_set_v1",
            "removed_span_hashes": ordered_removed_hashes,
        }
    )
    deterministic_hash = canon_hash_obj(
        {
            "schema_version": "epistemic_instruction_strip_binding_v1",
            "input_blob_id": input_blob_id,
            "output_blob_id": output_blob_id,
            "instruction_strip_contract_id": instruction_strip_contract_id,
            "removed_span_hashes": ordered_removed_hashes,
            "removed_spans_hash": removed_spans_hash,
        }
    )
    payload = {
        "schema_version": "epistemic_instruction_strip_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "input_blob_id": input_blob_id,
        "output_blob_id": output_blob_id,
        "instruction_strip_contract_id": instruction_strip_contract_id,
        "removed_span_count_u64": int(len(ordered_removed_hashes)),
        "removed_span_hashes": ordered_removed_hashes,
        "removed_spans_hash": removed_spans_hash,
        "deterministic_hash": deterministic_hash,
        "outcome": str(outcome),
    }
    payload["receipt_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "receipt_id"})
    validate_schema(payload, "epistemic_instruction_strip_receipt_v1")
    verify_object_id(payload, id_field="receipt_id")
    return payload


def strip_blob(
    *,
    input_bytes: bytes,
    input_blob_id: str,
    contract: dict[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    input_blob_id = ensure_sha256(input_blob_id, reason="SCHEMA_FAIL")
    if hash_bytes(input_bytes) != input_blob_id:
        fail("HASH_MISMATCH")
    contract_id = verify_object_id(contract, id_field="contract_id")
    output_bytes, removed_span_hashes = apply_instruction_strip(
        input_bytes=input_bytes,
        contract=contract,
    )
    output_blob_id = hash_bytes(output_bytes)
    receipt = build_instruction_strip_receipt(
        input_blob_id=input_blob_id,
        output_blob_id=output_blob_id,
        instruction_strip_contract_id=contract_id,
        removed_span_hashes=removed_span_hashes,
    )
    return output_bytes, receipt


__all__ = [
    "apply_instruction_strip",
    "build_instruction_strip_receipt",
    "default_instruction_strip_contract",
    "strip_blob",
]
