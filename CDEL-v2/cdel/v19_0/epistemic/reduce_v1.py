"""Deterministic REDUCE_V1 for epistemic MOB -> QXWMR graph."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
import re
import unicodedata
from typing import Any

from ..common_v1 import canon_hash_obj, ensure_sha256, fail, hash_bytes, validate_schema, verify_object_id
from .instruction_strip_v1 import default_instruction_strip_contract, strip_blob

_Q32_ONE = 1 << 32
_WS_RE = re.compile(r"[ \t\r\n]+")
_EDGE_PUNCT = " \t\r\n.,;:!?()[]{}\"'`"
_SUPPORTED_MOB_SCHEMAS = {"epistemic_model_output_v1", "epistemic_model_output_v2"}
_SUPPORTED_MOB_MEDIA_TYPES = {"application/json", "application/x.epistemic.claims+json"}


def _normalize_text(text: str, *, max_len: int, unicode_mode: str, whitespace_policy: str, punctuation_policy: str) -> str:
    out = str(text)
    if unicode_mode == "NFC":
        out = unicodedata.normalize("NFC", out)
    else:
        fail("SCHEMA_FAIL")

    if whitespace_policy == "COLLAPSE_ASCII_WHITESPACE":
        out = _WS_RE.sub(" ", out).strip()
    else:
        fail("SCHEMA_FAIL")

    if punctuation_policy == "STRIP_EDGE_PUNCT_KEEP_INNER":
        out = out.strip(_EDGE_PUNCT)
    else:
        fail("SCHEMA_FAIL")

    if len(out) > int(max_len):
        out = out[: int(max_len)]
    return out


def _q32_from_confidence(value: Any) -> int:
    try:
        dec = Decimal(str(value))
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
        return 0
    if dec.is_nan() or dec.is_infinite():
        fail("SCHEMA_FAIL")
    if dec < Decimal(0):
        dec = Decimal(0)
    if dec > Decimal(1):
        dec = Decimal(1)
    q = int((dec * Decimal(_Q32_ONE)).to_integral_value(rounding=ROUND_HALF_EVEN))
    if q < 0:
        q = 0
    if q > _Q32_ONE:
        q = _Q32_ONE
    return int(q)


def _apply_identity_clamp(q: int, *, min_q: int, max_q: int) -> int:
    lo = int(min_q)
    hi = int(max_q)
    if lo < 0 or hi < 0 or lo > hi:
        fail("SCHEMA_FAIL")
    if q < lo:
        return lo
    if q > hi:
        return hi
    return q


def _claim_hash(claim_text: str, source_span: str) -> str:
    payload = {
        "schema_version": "epistemic_claim_v1",
        "claim_text": str(claim_text),
        "source_span": str(source_span),
    }
    return canon_hash_obj(payload)


def _mob_canon_hash(payload: dict[str, Any]) -> str:
    # MOB v1 allows confidence_f64, so we use a float-tolerant canonicalizer here.
    try:
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
        return "sha256:" + ("0" * 64)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mob_v2_id_hash(mob: dict[str, Any]) -> str:
    no_id = dict(mob)
    no_id.pop("mob_id", None)
    # v2 binds receipt id through cross-checks but excludes it from mob_id derivation
    # to avoid cyclic id coupling between mob and mob_receipt artifacts.
    no_id.pop("mob_receipt_id", None)
    return canon_hash_obj(no_id)


def verify_mob_v1_id(mob: dict[str, Any]) -> str:
    expected = ensure_sha256(mob.get("mob_id"), reason="SCHEMA_FAIL")
    no_id = dict(mob)
    no_id.pop("mob_id", None)
    observed = _mob_canon_hash(no_id)
    if observed != expected:
        fail("ID_MISMATCH")
    return expected


def verify_mob_v2_id(mob: dict[str, Any]) -> str:
    expected = ensure_sha256(mob.get("mob_id"), reason="SCHEMA_FAIL")
    observed = _mob_v2_id_hash(mob)
    if observed != expected:
        fail("ID_MISMATCH")
    return expected


def verify_mob_payload(mob: dict[str, Any]) -> tuple[str, str]:
    schema_version = str(mob.get("schema_version", "")).strip()
    if schema_version == "epistemic_model_output_v1":
        validate_schema(mob, "epistemic_model_output_v1")
        return schema_version, verify_mob_v1_id(mob)
    if schema_version == "epistemic_model_output_v2":
        validate_schema(mob, "epistemic_model_output_v2")
        return schema_version, verify_mob_v2_id(mob)
    fail("MOB_SCHEMA_UNSUPPORTED")
    return "", "sha256:" + ("0" * 64)


def verify_mob_id(mob: dict[str, Any]) -> str:
    _schema_version, mob_id = verify_mob_payload(mob)
    return mob_id


def _claims_from_v2_blob(blob: bytes, *, mob_media_type: str) -> list[dict[str, Any]]:
    if mob_media_type not in _SUPPORTED_MOB_MEDIA_TYPES:
        fail("MOB_FORMAT_REJECTED")
    try:
        payload = json.loads(blob.decode("utf-8"))
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
        return []
    try:
        canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
        return []
    if blob.rstrip(b"\n") != canon:
        fail("NONDETERMINISTIC")
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    claims = payload.get("claims")
    if not isinstance(claims, list):
        fail("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in claims:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        out.append(dict(row))
    return out


def _claims_from_mob(
    mob: dict[str, Any],
    *,
    mob_blob_bytes_by_id: dict[str, bytes],
    mob_receipts_by_id: dict[str, dict[str, Any]],
    instruction_strip_contract: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    schema_version = str(mob.get("schema_version", "")).strip()
    if schema_version == "epistemic_model_output_v1":
        claims = mob.get("claims")
        if not isinstance(claims, list):
            fail("SCHEMA_FAIL")
        out_rows: list[dict[str, Any]] = []
        for row in claims:
            if not isinstance(row, dict):
                fail("SCHEMA_FAIL")
            out_rows.append(dict(row))
        payload = {"claims": out_rows}
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        input_blob_id = hash_bytes(blob)
        stripped_blob, strip_receipt = strip_blob(
            input_bytes=blob,
            input_blob_id=input_blob_id,
            contract=instruction_strip_contract,
        )
        stripped_claims = _claims_from_v2_blob(
            stripped_blob,
            mob_media_type="application/x.epistemic.claims+json",
        )
        return stripped_claims, strip_receipt

    if schema_version != "epistemic_model_output_v2":
        fail("MOB_SCHEMA_UNSUPPORTED")
    if str(mob.get("content_kind", "")) != "BLOB_REF":
        fail("MOB_FORMAT_REJECTED")
    mob_blob_id = ensure_sha256(mob.get("mob_blob_id"), reason="SCHEMA_FAIL")
    blob = mob_blob_bytes_by_id.get(mob_blob_id)
    if blob is None:
        fail("MISSING_INPUT")
    if "sha256:" + hashlib.sha256(blob).hexdigest() != mob_blob_id:
        fail("HASH_MISMATCH")

    mob_receipt_id = ensure_sha256(mob.get("mob_receipt_id"), reason="SCHEMA_FAIL")
    mob_receipt = mob_receipts_by_id.get(mob_receipt_id)
    if not isinstance(mob_receipt, dict):
        fail("MISSING_INPUT")
    validate_schema(mob_receipt, "epistemic_mob_receipt_v1")
    if verify_object_id(mob_receipt, id_field="mob_receipt_id") != mob_receipt_id:
        fail("NONDETERMINISTIC")
    if ensure_sha256(mob_receipt.get("mob_id"), reason="SCHEMA_FAIL") != ensure_sha256(mob.get("mob_id"), reason="SCHEMA_FAIL"):
        fail("NONDETERMINISTIC")
    if ensure_sha256(mob_receipt.get("episode_id"), reason="SCHEMA_FAIL") != ensure_sha256(mob.get("episode_id"), reason="SCHEMA_FAIL"):
        fail("NONDETERMINISTIC")
    if ensure_sha256(mob_receipt.get("mob_blob_id"), reason="SCHEMA_FAIL") != mob_blob_id:
        fail("NONDETERMINISTIC")

    stripped_blob, strip_receipt = strip_blob(
        input_bytes=blob,
        input_blob_id=mob_blob_id,
        contract=instruction_strip_contract,
    )
    return _claims_from_v2_blob(
        stripped_blob,
        mob_media_type=str(mob.get("mob_media_type", "")).strip(),
    ), strip_receipt


def reduce_mobs_to_qxwmr_graph_with_strip(
    *,
    episode_id: str,
    mob_payloads: list[dict[str, Any]],
    reduce_contract: dict[str, Any],
    calibration: dict[str, Any],
    instruction_strip_contract: dict[str, Any] | None = None,
    accepted_mob_schema_versions: list[str] | None = None,
    mob_blob_bytes_by_id: dict[str, bytes] | None = None,
    mob_receipts_by_id: dict[str, dict[str, Any]] | None = None,
    type_registry_id: str | None = None,
) -> dict[str, Any]:
    validate_schema(reduce_contract, "epistemic_reduce_contract_v1")
    validate_schema(calibration, "epistemic_confidence_calibration_v1")
    contract_id = verify_object_id(reduce_contract, id_field="contract_id")
    calibration_id = verify_object_id(calibration, id_field="calibration_id")
    if instruction_strip_contract is None:
        strip_contract = default_instruction_strip_contract()
    else:
        strip_contract = dict(instruction_strip_contract)
    validate_schema(strip_contract, "epistemic_instruction_strip_contract_v1")
    strip_contract_id = verify_object_id(strip_contract, id_field="contract_id")

    if str(reduce_contract.get("reducer_kind", "")) != "REDUCE_V1":
        fail("SCHEMA_FAIL")
    if str(calibration.get("calibration_kind", "")) != "IDENTITY_CLAMP_V1":
        fail("SCHEMA_FAIL")
    if ensure_sha256(reduce_contract.get("confidence_calibration_id"), reason="SCHEMA_FAIL") != calibration_id:
        fail("NONDETERMINISTIC")
    if ensure_sha256(reduce_contract.get("instruction_strip_contract_id"), reason="SCHEMA_FAIL") != strip_contract_id:
        fail("NONDETERMINISTIC")

    max_claims = int(reduce_contract.get("max_claims_u64", 0))
    max_claim_text_len = int(reduce_contract.get("max_claim_text_len_u64", 0))
    unicode_mode = str(reduce_contract.get("unicode_normalization", ""))
    ws_policy = str(reduce_contract.get("whitespace_policy", ""))
    punct_policy = str(reduce_contract.get("punctuation_policy", ""))
    claim_hash_algorithm = str(reduce_contract.get("claim_hash_algorithm", ""))
    if claim_hash_algorithm != "SHA256_CANON_V1":
        fail("SCHEMA_FAIL")

    min_q = int(calibration.get("clamp_min_q32", 0))
    max_q = int(calibration.get("clamp_max_q32", _Q32_ONE))
    if accepted_mob_schema_versions is None:
        accepted_versions = {"epistemic_model_output_v1"}
    else:
        accepted_versions = {str(row).strip() for row in accepted_mob_schema_versions if str(row).strip()}
    if not accepted_versions or not accepted_versions.issubset(_SUPPORTED_MOB_SCHEMAS):
        fail("SCHEMA_FAIL")
    mob_blob_bytes_by_id = dict(mob_blob_bytes_by_id or {})
    mob_receipts_by_id = dict(mob_receipts_by_id or {})

    nodes: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()
    strip_receipts_by_id: dict[str, dict[str, Any]] = {}

    for mob in mob_payloads:
        schema_version, _mob_id = verify_mob_payload(mob)
        if schema_version not in accepted_versions:
            fail("MOB_SCHEMA_UNSUPPORTED")
        claims, strip_receipt = _claims_from_mob(
            mob,
            mob_blob_bytes_by_id=mob_blob_bytes_by_id,
            mob_receipts_by_id=mob_receipts_by_id,
            instruction_strip_contract=strip_contract,
        )
        strip_receipt_id = verify_object_id(strip_receipt, id_field="receipt_id")
        previous = strip_receipts_by_id.get(strip_receipt_id)
        if previous is not None and canon_hash_obj(previous) != canon_hash_obj(strip_receipt):
            fail("NONDETERMINISTIC")
        strip_receipts_by_id[strip_receipt_id] = dict(strip_receipt)

        for claim_row in claims:
            if not isinstance(claim_row, dict):
                fail("SCHEMA_FAIL")
            claim_text = _normalize_text(
                str(claim_row.get("claim_text", "")),
                max_len=max_claim_text_len,
                unicode_mode=unicode_mode,
                whitespace_policy=ws_policy,
                punctuation_policy=punct_policy,
            )
            if not claim_text:
                continue
            source_span = str(claim_row.get("source_span", "")).strip()
            claim_id = _claim_hash(claim_text, source_span)
            if claim_id in seen_node_ids:
                continue
            seen_node_ids.add(claim_id)
            q_conf = _q32_from_confidence(claim_row.get("confidence_f64", 0.0))
            q_conf = _apply_identity_clamp(q_conf, min_q=min_q, max_q=max_q)
            nodes.append(
                {
                    "node_id": claim_id,
                    "type_id": "CLAIM",
                    "value_kind": "STRING",
                    "text_value": claim_text,
                    "confidence_q32": int(q_conf),
                    "provenance_raw_blob_ids": [],
                    "constraints": {
                        "source_span": source_span,
                    },
                }
            )

    nodes.sort(key=lambda row: str(row.get("node_id", "")))
    if len(nodes) > max_claims:
        nodes = nodes[:max_claims]

    graph_payload = {
        "schema_version": "qxwmr_graph_v1",
        "graph_id": "sha256:" + ("0" * 64),
        "episode_id": str(episode_id),
        "reduce_contract_id": contract_id,
        "confidence_calibration_id": calibration_id,
        "nodes": nodes,
        "edges": [],
    }
    if type_registry_id is not None:
        graph_payload["type_registry_id"] = ensure_sha256(type_registry_id, reason="SCHEMA_FAIL")
    graph_payload["graph_id"] = canon_hash_obj({k: v for k, v in graph_payload.items() if k != "graph_id"})
    validate_schema(graph_payload, "qxwmr_graph_v1")
    verify_object_id(graph_payload, id_field="graph_id")
    strip_receipts = sorted(
        strip_receipts_by_id.values(),
        key=lambda row: str(row.get("receipt_id", "")),
    )
    strip_receipt_ids = [str(row.get("receipt_id", "")) for row in strip_receipts]
    strip_receipt_id = canon_hash_obj(
        {
            "schema_version": "epistemic_instruction_strip_receipt_set_v1",
            "receipt_ids": strip_receipt_ids,
        }
    )
    return {
        "graph": graph_payload,
        "strip_receipts": strip_receipts,
        "strip_receipt_id": strip_receipt_id,
    }


def reduce_mobs_to_qxwmr_graph(
    *,
    episode_id: str,
    mob_payloads: list[dict[str, Any]],
    reduce_contract: dict[str, Any],
    calibration: dict[str, Any],
    instruction_strip_contract: dict[str, Any] | None = None,
    accepted_mob_schema_versions: list[str] | None = None,
    mob_blob_bytes_by_id: dict[str, bytes] | None = None,
    mob_receipts_by_id: dict[str, dict[str, Any]] | None = None,
    type_registry_id: str | None = None,
) -> dict[str, Any]:
    reduced = reduce_mobs_to_qxwmr_graph_with_strip(
        episode_id=episode_id,
        mob_payloads=mob_payloads,
        reduce_contract=reduce_contract,
        calibration=calibration,
        instruction_strip_contract=instruction_strip_contract,
        accepted_mob_schema_versions=accepted_mob_schema_versions,
        mob_blob_bytes_by_id=mob_blob_bytes_by_id,
        mob_receipts_by_id=mob_receipts_by_id,
        type_registry_id=type_registry_id,
    )
    graph = reduced.get("graph")
    if not isinstance(graph, dict):
        fail("NONDETERMINISTIC")
    return dict(graph)


__all__ = [
    "reduce_mobs_to_qxwmr_graph",
    "reduce_mobs_to_qxwmr_graph_with_strip",
    "verify_mob_id",
    "verify_mob_payload",
    "verify_mob_v1_id",
    "verify_mob_v2_id",
]
