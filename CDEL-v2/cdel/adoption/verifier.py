"""Verifier pipeline for adoption records."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import time

from cdel.constraints import constraint_spec_hash
from cdel.adoption import canon
from cdel.adoption.storage import append_order_log, object_path, read_head, write_head, write_meta, write_object
from cdel.config import Config
from cdel.kernel.canon import canonical_json_bytes
from cdel.ledger import index as idx
from cdel.sealed.config import load_sealed_config
from cdel.sealed.crypto import crypto_available, verify_signature
from cdel.sealed.evalue import encoded_evalue_to_decimal, format_decimal, parse_alpha_schedule, parse_decimal, parse_evalue
from cdel.sealed.protocol import stat_cert_signing_bytes


@dataclass(frozen=True)
class AdoptionRejection:
    code: str
    reason: str
    details: str | None = None


@dataclass(frozen=True)
class AdoptionResult:
    ok: bool
    payload_hash: str | None = None
    payload_bytes: bytes | None = None
    payload: dict | None = None
    rejection: AdoptionRejection | None = None


def verify_adoption(cfg: Config, record: dict) -> AdoptionResult:
    try:
        _validate_schema(record)
        if not cfg.adoption_head_file.exists():
            return _reject("ADOPTION_NOT_INITIALIZED", "adoption ledger not initialized", "run cdel init")
        payload = canon.canonicalize_payload(record.get("payload") or {})
        payload_bytes = canonical_json_bytes(payload)
        payload_hash = canon.payload_hash_hex(payload)
        parent = record.get("parent")

        head = read_head(cfg)
        if parent != head:
            return _reject("PARENT_MISMATCH", "parent does not match head", f"expected {head}")

        if object_path(cfg, payload_hash).exists():
            return _reject("HASH_EXISTS", "payload already exists", payload_hash)

        concept = payload.get("concept")
        chosen_symbol = payload.get("chosen_symbol")
        baseline_symbol = payload.get("baseline_symbol")
        cert = payload.get("certificate") or {}

        conn = idx.connect(str(cfg.sqlite_path))
        idx.init_schema(conn)
        if not idx.symbol_exists(conn, chosen_symbol):
            return _reject("SYMBOL_UNKNOWN", "chosen_symbol not found", chosen_symbol)
        if baseline_symbol and not idx.symbol_exists(conn, baseline_symbol):
            return _reject("SYMBOL_UNKNOWN", "baseline_symbol not found", baseline_symbol)
        if not idx.concept_symbol_exists(conn, concept, chosen_symbol):
            return _reject("CONCEPT_UNKNOWN", "concept symbol not indexed", concept)

        latest = idx.latest_adoption_for_concept(conn, concept)
        if latest is None:
            if baseline_symbol is not None:
                return _reject("BASELINE_MISMATCH", "baseline must be null for first adoption", concept)
        else:
            current = latest.get("chosen_symbol")
            if baseline_symbol != current:
                return _reject("BASELINE_MISMATCH", "baseline does not match current adoption", current)

        _validate_certificate(cfg, cert, concept, chosen_symbol, baseline_symbol)
        _validate_constraints(cfg, payload.get("constraints") or {}, concept, chosen_symbol, baseline_symbol)

        return AdoptionResult(
            ok=True,
            payload_hash=payload_hash,
            payload_bytes=payload_bytes,
            payload=payload,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        return _reject("SCHEMA_INVALID", "schema validation failed", str(exc))


def commit_adoption(cfg: Config, record: dict) -> AdoptionResult:
    result = verify_adoption(cfg, record)
    if not result.ok:
        return result
    assert result.payload_hash is not None
    assert result.payload_bytes is not None
    assert result.payload is not None

    write_object(cfg, result.payload_hash, result.payload_bytes)
    meta = record.get("meta")
    if isinstance(meta, dict) and meta:
        try:
            write_meta(cfg, result.payload_hash, meta)
        except Exception:
            logging.warning("adoption meta write failed; continuing without metadata")
    appended = append_order_log(cfg, result.payload_hash)
    if not appended:
        logging.warning("adoption order.log already contains hash; skipping append")
        return result
    write_head(cfg, result.payload_hash)

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    try:
        with conn:
            idx.insert_adoption(
                conn,
                result.payload_hash,
                record.get("parent"),
                result.payload_bytes,
                int(time.time()),
                result.payload.get("concept"),
                result.payload.get("chosen_symbol"),
                result.payload.get("baseline_symbol"),
            )
    except Exception:
        conn.rollback()
        logging.warning("adoption sqlite update failed; ledger remains append-only")
    return result


def _validate_schema(record: dict) -> None:
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    if record.get("schema_version") != 1:
        raise ValueError("unsupported schema_version")
    if "parent" not in record or not isinstance(record.get("parent"), str):
        raise ValueError("record missing parent")
    if "payload" not in record or not isinstance(record.get("payload"), dict):
        raise ValueError("record missing payload")


def _validate_certificate(
    cfg: Config,
    cert: dict,
    concept: str,
    chosen_symbol: str,
    baseline_symbol: str | None,
    *,
    sealed_cfg_override=None,
) -> None:
    if not isinstance(cert, dict):
        raise ValueError("certificate must be an object")
    if cert.get("kind") != "stat_cert":
        raise ValueError("certificate must be stat_cert")
    if cert.get("candidate_symbol") != chosen_symbol:
        raise ValueError("certificate candidate_symbol mismatch")
    if baseline_symbol is not None and cert.get("baseline_symbol") != baseline_symbol:
        raise ValueError("certificate baseline_symbol mismatch")
    if cert.get("concept") != concept:
        raise ValueError("certificate concept mismatch")

    sealed_cfg = sealed_cfg_override or load_sealed_config(cfg.data)
    eval_cfg = cert.get("eval") or {}
    if not isinstance(eval_cfg, dict):
        raise ValueError("certificate eval must be object")
    if eval_cfg.get("eval_harness_id") != sealed_cfg.eval_harness_id:
        raise ValueError("certificate eval_harness_id mismatch")
    if eval_cfg.get("eval_harness_hash") != sealed_cfg.eval_harness_hash:
        raise ValueError("certificate eval_harness_hash mismatch")
    if eval_cfg.get("eval_suite_hash") != sealed_cfg.eval_suite_hash:
        raise ValueError("certificate eval_suite_hash mismatch")

    risk = cert.get("risk") or {}
    if not isinstance(risk, dict):
        raise ValueError("certificate risk must be an object")
    alpha_i = parse_decimal(str(risk.get("alpha_i")))
    threshold = parse_decimal(str(risk.get("evalue_threshold")))
    schedule = parse_alpha_schedule(risk.get("alpha_schedule"))
    if schedule.name != sealed_cfg.alpha_schedule.name or schedule.exponent != sealed_cfg.alpha_schedule.exponent:
        raise ValueError("certificate alpha_schedule mismatch")
    if format_decimal(schedule.coefficient) != format_decimal(sealed_cfg.alpha_schedule.coefficient):
        raise ValueError("certificate alpha_schedule coefficient mismatch")

    cert_payload = cert.get("certificate") or {}
    if not isinstance(cert_payload, dict):
        raise ValueError("certificate payload must be an object")
    schema_version = cert_payload.get("evalue_schema_version")
    if schema_version is None:
        raise ValueError("certificate evalue_schema_version missing")
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise ValueError("certificate evalue_schema_version must be int")
    if schema_version != 2:
        raise ValueError("certificate evalue_schema_version unsupported")
    try:
        evalue = parse_evalue(cert_payload.get("evalue"), "certificate evalue")
    except ValueError as exc:
        raise ValueError("certificate evalue invalid") from exc
    signature = cert_payload.get("signature")
    signature_scheme = cert_payload.get("signature_scheme")
    key_id = cert_payload.get("key_id")
    if not isinstance(signature, str) or not isinstance(signature_scheme, str):
        raise ValueError("certificate signature missing")
    if not isinstance(key_id, str) or not key_id:
        raise ValueError("certificate key_id missing")

    if not crypto_available():
        raise ValueError("crypto backend unavailable")
    public_key = sealed_cfg.allowed_keys.get(key_id)
    if not public_key:
        raise ValueError("certificate key_id not allowed")

    if encoded_evalue_to_decimal(evalue) * alpha_i < threshold:
        raise ValueError("certificate evalue below threshold")

    signing_bytes = stat_cert_signing_bytes(cert)
    if not verify_signature(public_key, signing_bytes, signature, signature_scheme):
        raise ValueError("certificate signature invalid")


def _validate_constraints(
    cfg: Config,
    constraints: dict,
    concept: str,
    chosen_symbol: str,
    baseline_symbol: str | None,
) -> None:
    constraints_cfg = cfg.data.get("constraints") or {}
    required = constraints_cfg.get("required_concepts") or []
    if not _requires_constraints(concept, required):
        return

    if not constraints:
        raise ValueError("constraints required for concept")

    expected_hash = constraints_cfg.get("spec_hash")
    if not isinstance(expected_hash, str) or not expected_hash:
        raise ValueError("constraints.spec_hash missing")
    spec_hash = constraints.get("spec_hash")
    if spec_hash != expected_hash:
        raise ValueError("constraints spec_hash mismatch")
    spec = constraints.get("spec")
    if not isinstance(spec, dict):
        raise ValueError("constraints spec missing")
    actual_hash = constraint_spec_hash(spec)
    if actual_hash != expected_hash:
        raise ValueError("constraints spec hash mismatch")

    safety_cert = constraints.get("safety_certificate")
    if not isinstance(safety_cert, dict):
        raise ValueError("constraints safety_certificate missing")
    safety_block = cfg.data.get("sealed_safety")
    if not isinstance(safety_block, dict) or not safety_block:
        raise ValueError("sealed_safety missing")
    safety_cfg = load_sealed_config({"sealed": safety_block}, require_keys=True)
    _validate_certificate(
        cfg,
        safety_cert,
        concept,
        chosen_symbol,
        baseline_symbol,
        sealed_cfg_override=safety_cfg,
    )


def _requires_constraints(concept: str, prefixes: object) -> bool:
    if not isinstance(prefixes, list) or not prefixes:
        return False
    for item in prefixes:
        if isinstance(item, str) and concept.startswith(item):
            return True
    return False


def _reject(code: str, reason: str, details: str | None = None) -> AdoptionResult:
    return AdoptionResult(ok=False, rejection=AdoptionRejection(code=code, reason=reason, details=details))
