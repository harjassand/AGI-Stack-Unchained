from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, write_canon_json
from cdel.v18_0.omega_common_v1 import validate_schema as validate_schema_v18
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

_SHA_PREFIX = "sha256:"


class CandidateStoreError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise CandidateStoreError(str(reason).strip() or "STORE_ERROR")


def _sha256_prefixed(data: bytes) -> str:
    return f"{_SHA_PREFIX}{hashlib.sha256(data).hexdigest()}"


def _ensure_sha256(value: Any, *, field: str) -> str:
    text = str(value).strip()
    if not text.startswith(_SHA_PREFIX) or len(text) != 71:
        _fail(f"SCHEMA_FAIL:{field}")
    try:
        int(text.split(":", 1)[1], 16)
    except Exception as exc:  # noqa: BLE001
        raise CandidateStoreError(f"SCHEMA_FAIL:{field}") from exc
    return text


def _id_for(payload: dict[str, Any], *, id_field: str = "id") -> str:
    no_id = dict(payload)
    no_id.pop(id_field, None)
    return _sha256_prefixed(canon_bytes(no_id))


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = bytearray()
    for row in rows:
        buf += canon_bytes(row)
        buf += b"\n"
    path.write_bytes(bytes(buf))
    return _sha256_prefixed(bytes(buf))


def _write_text(path: Path, text: str) -> str:
    data = text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha256_prefixed(data)


class CandidateStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.config_dir = self.root / "config"
        self.ir_dir = self.root / "ir"
        self.plan_dir = self.root / "dmpl" / "plan"
        self.cac_dir = self.root / "dmpl" / "cac"
        self.eval_dir = self.root / "candidate_eval"
        self.index_dir = self.root / "indexes"
        self.logs_dir = self.root / "logs"
        self.receipt_dir = self.root / "receipt"

        for d in [
            self.config_dir,
            self.ir_dir,
            self.plan_dir,
            self.cac_dir,
            self.eval_dir,
            self.index_dir,
            self.logs_dir,
            self.receipt_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        self._candidate_eval_index_rows: list[dict[str, Any]] = []
        self._log_rows: list[dict[str, Any]] = []

    @staticmethod
    def _hashed_path(out_dir: Path, suffix: str, digest: str) -> Path:
        return out_dir / f"sha256_{digest.split(':', 1)[1]}.{suffix}"

    def append_log(self, *, event: str, payload: dict[str, Any]) -> None:
        row = {
            "schema_id": "ttc_grpo_log_row_v1",
            "event": str(event),
            "payload": dict(payload),
        }
        validate_schema_v19(row, "ttc_grpo_log_row_v1")
        self._log_rows.append(row)

    def write_config(self, payload: dict[str, Any]) -> str:
        obj = dict(payload)
        obj["schema_id"] = "ttc_grpo_run_config_v1"
        obj["id"] = _id_for(obj)
        validate_schema_v19(obj, "ttc_grpo_run_config_v1")
        digest = _ensure_sha256(obj.get("id"), field="id")
        out = self._hashed_path(self.config_dir, "ttc_grpo_run_config_v1.json", digest)
        write_canon_json(out, obj)
        return digest

    def write_ir(self, ir_obj: dict[str, Any]) -> str:
        obj = dict(ir_obj)
        obj["schema_version"] = "polymath_restricted_ir_v1"
        obj["ir_id"] = _id_for(obj, id_field="ir_id")
        validate_schema_v18(obj, "polymath_restricted_ir_v1")
        digest = _ensure_sha256(obj.get("ir_id"), field="ir_id")
        out = self._hashed_path(self.ir_dir, "polymath_restricted_ir_v1.json", digest)
        write_canon_json(out, obj)
        return digest

    def write_plan_result_stub(self, payload: dict[str, Any]) -> str:
        obj = dict(payload)
        digest = _sha256_prefixed(canon_bytes(obj))
        out = self._hashed_path(self.plan_dir, "dmpl_action_receipt_v1.json", digest)
        write_canon_json(out, obj)
        return digest

    def write_cac(self, payload: dict[str, Any]) -> str:
        obj = dict(payload)
        obj["schema_id"] = "cac_v1"
        validate_schema_v18(obj, "cac_v1")
        digest = _sha256_prefixed(canon_bytes(obj))
        out = self._hashed_path(self.cac_dir, "cac_v1.json", digest)
        write_canon_json(out, obj)
        return digest

    def write_candidate_eval(self, payload: dict[str, Any]) -> dict[str, Any]:
        obj = dict(payload)
        obj["schema_id"] = "ttc_grpo_candidate_eval_v1"
        obj["id"] = _id_for(obj)
        validate_schema_v19(obj, "ttc_grpo_candidate_eval_v1")
        digest = _ensure_sha256(obj.get("id"), field="id")
        out = self._hashed_path(self.eval_dir, "ttc_grpo_candidate_eval_v1.json", digest)
        write_canon_json(out, obj)

        index_row = {
            "schema_id": "ttc_grpo_candidate_eval_index_row_v1",
            "candidate_index_u64": int(obj.get("candidate_index_u64", 0)),
            "candidate_eval_hash": digest,
        }
        validate_schema_v19(index_row, "ttc_grpo_candidate_eval_index_row_v1")
        self._candidate_eval_index_rows.append(index_row)
        return obj

    def _flush_indexes_and_logs(self) -> tuple[str, str]:
        index_rows = sorted(
            self._candidate_eval_index_rows,
            key=lambda row: (int(row.get("candidate_index_u64", 0)), str(row.get("candidate_eval_hash", ""))),
        )
        index_hash = _write_jsonl(
            self.index_dir / "candidate_eval_index.ttc_grpo_candidate_eval_index_v1.jsonl",
            index_rows,
        )

        log_rows = list(self._log_rows)
        logs_hash = _write_jsonl(self.logs_dir / "ttc_grpo_run.log.jsonl", log_rows)
        return index_hash, logs_hash

    def write_run_receipt(self, payload: dict[str, Any]) -> dict[str, Any]:
        index_hash, logs_hash = self._flush_indexes_and_logs()

        obj = dict(payload)
        obj["schema_id"] = "ttc_grpo_run_receipt_v1"
        artifacts = dict(obj.get("artifacts") or {})
        artifacts["candidate_eval_index_jsonl_hash"] = index_hash
        artifacts["logs_hash"] = logs_hash
        obj["artifacts"] = artifacts
        obj["id"] = _id_for(obj)

        validate_schema_v19(obj, "ttc_grpo_run_receipt_v1")
        digest = _ensure_sha256(obj.get("id"), field="id")
        out = self._hashed_path(self.receipt_dir, "ttc_grpo_run_receipt_v1.json", digest)
        write_canon_json(out, obj)
        return obj


__all__ = ["CandidateStore", "CandidateStoreError"]
