#!/usr/bin/env python3
"""Lightweight schema loading/validation helpers for Step 3A training artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:  # pragma: no cover - optional dependency
    from jsonschema import Draft202012Validator
except Exception:  # pragma: no cover - optional dependency
    Draft202012Validator = None

_SCHEMA_NAMES = {
    "proposer_sft_example_v1",
    "proposer_dpo_pair_v1",
    "proposer_training_corpus_manifest_v1",
    "proposer_corpus_build_receipt_v1",
}
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}
_VALIDATOR_CACHE: dict[str, Any] = {}


class SchemaValidationError(ValueError):
    """Raised when payloads do not satisfy their schema contract."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def schema_path(schema_name: str) -> Path:
    if schema_name not in _SCHEMA_NAMES:
        raise SchemaValidationError(f"unknown schema: {schema_name}")
    primary = repo_root() / "Genesis" / "schema" / "v19_0" / f"{schema_name}.jsonschema"
    if primary.exists() and primary.is_file():
        return primary
    secondary = repo_root() / "CDEL-v2" / "Genesis" / "schema" / "v19_0" / f"{schema_name}.jsonschema"
    if secondary.exists() and secondary.is_file():
        return secondary
    raise SchemaValidationError(f"missing schema file: {schema_name}")


def _load_schema(schema_name: str) -> dict[str, Any]:
    cached = _SCHEMA_CACHE.get(schema_name)
    if cached is not None:
        return cached
    path = schema_path(schema_name)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SchemaValidationError(f"schema parse failed: {schema_name}") from exc
    if not isinstance(payload, dict):
        raise SchemaValidationError(f"schema is not an object: {schema_name}")
    _SCHEMA_CACHE[schema_name] = payload
    return payload


def _validator(schema_name: str) -> Any:
    cached = _VALIDATOR_CACHE.get(schema_name)
    if cached is not None:
        return cached
    schema = _load_schema(schema_name)
    if Draft202012Validator is None:
        return None
    validator = Draft202012Validator(schema)
    _VALIDATOR_CACHE[schema_name] = validator
    return validator


def _require_dict(payload: Any, *, schema_name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SchemaValidationError(f"{schema_name}: payload must be an object")
    return payload


def _require_fields(payload: dict[str, Any], *, schema_name: str, fields: list[str]) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise SchemaValidationError(f"{schema_name}: missing required fields: {', '.join(missing)}")


def _require_sha(value: Any, *, schema_name: str, field: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise SchemaValidationError(f"{schema_name}: invalid sha256 field: {field}")


def _minimal_validate(payload: Any, *, schema_name: str) -> None:
    obj = _require_dict(payload, schema_name=schema_name)
    if schema_name == "proposer_sft_example_v1":
        _require_fields(
            obj,
            schema_name=schema_name,
            fields=[
                "schema_version",
                "example_id",
                "role",
                "inputs_descriptor_id",
                "agent_id",
                "candidate_id",
                "ek_id",
                "kernel_ledger_id",
                "prompt_text",
                "response_text",
                "label",
                "metadata",
            ],
        )
        _require_sha(obj.get("example_id"), schema_name=schema_name, field="example_id")
        _require_sha(obj.get("inputs_descriptor_id"), schema_name=schema_name, field="inputs_descriptor_id")
        _require_sha(obj.get("candidate_id"), schema_name=schema_name, field="candidate_id")
        _require_sha(obj.get("ek_id"), schema_name=schema_name, field="ek_id")
        _require_sha(obj.get("kernel_ledger_id"), schema_name=schema_name, field="kernel_ledger_id")
        if str(obj.get("schema_version")) != schema_name:
            raise SchemaValidationError(f"{schema_name}: schema_version mismatch")
        role = str(obj.get("role"))
        if role not in {"PATCH_DRAFTER_V1", "PATCH_CRITIC_V1"}:
            raise SchemaValidationError(f"{schema_name}: invalid role")
        label = _require_dict(obj.get("label"), schema_name=schema_name)
        _require_fields(
            label,
            schema_name=schema_name,
            fields=["official_outcome", "official_reason_code", "utility_class", "weight_q32"],
        )
        metadata = _require_dict(obj.get("metadata"), schema_name=schema_name)
        _require_fields(
            metadata,
            schema_name=schema_name,
            fields=["candidate_kind", "declared_touched_paths", "derived_touched_paths"],
        )
        return

    if schema_name == "proposer_dpo_pair_v1":
        _require_fields(
            obj,
            schema_name=schema_name,
            fields=[
                "schema_version",
                "pair_id",
                "role",
                "ek_id",
                "kernel_ledger_id",
                "group_key",
                "prompt_text",
                "chosen_response_text",
                "rejected_response_text",
                "pair_weight_q32",
                "chosen_example_id",
                "rejected_example_id",
            ],
        )
        for field in [
            "pair_id",
            "ek_id",
            "kernel_ledger_id",
            "group_key",
            "chosen_example_id",
            "rejected_example_id",
        ]:
            _require_sha(obj.get(field), schema_name=schema_name, field=field)
        return

    if schema_name == "proposer_training_corpus_manifest_v1":
        _require_fields(
            obj,
            schema_name=schema_name,
            fields=[
                "schema_version",
                "corpus_id",
                "build_config_id",
                "runs_root_rel",
                "included_run_ids",
                "ek_id",
                "kernel_ledger_id",
                "counts",
                "splits",
                "sft_examples_blob_id",
                "dpo_pairs_blob_id",
                "redaction_policy_id",
                "hashes",
            ],
        )
        for field in [
            "corpus_id",
            "build_config_id",
            "ek_id",
            "kernel_ledger_id",
            "sft_examples_blob_id",
            "dpo_pairs_blob_id",
            "redaction_policy_id",
        ]:
            _require_sha(obj.get(field), schema_name=schema_name, field=field)
        hashes = _require_dict(obj.get("hashes"), schema_name=schema_name)
        _require_sha(hashes.get("sft_examples_sha256"), schema_name=schema_name, field="hashes.sft_examples_sha256")
        _require_sha(hashes.get("dpo_pairs_sha256"), schema_name=schema_name, field="hashes.dpo_pairs_sha256")
        return

    if schema_name == "proposer_corpus_build_receipt_v1":
        _require_fields(
            obj,
            schema_name=schema_name,
            fields=[
                "schema_version",
                "corpus_id",
                "status",
                "reason_code",
                "dropped_rows_u64",
                "drop_reason_histogram",
                "forbidden_path_hits_u64",
            ],
        )
        _require_sha(obj.get("corpus_id"), schema_name=schema_name, field="corpus_id")
        status = str(obj.get("status"))
        if status not in {"OK", "FAIL"}:
            raise SchemaValidationError(f"{schema_name}: invalid status")
        return

    raise SchemaValidationError(f"unsupported schema: {schema_name}")


def validate_payload(payload: Any, schema_name: str) -> None:
    if schema_name not in _SCHEMA_NAMES:
        raise SchemaValidationError(f"unknown schema: {schema_name}")
    validator = _validator(schema_name)
    if validator is not None:
        try:
            validator.validate(payload)
            return
        except Exception as exc:  # noqa: BLE001
            raise SchemaValidationError(f"{schema_name}: schema validation failed") from exc
    _minimal_validate(payload, schema_name=schema_name)


__all__ = [
    "SchemaValidationError",
    "repo_root",
    "schema_path",
    "validate_payload",
]
