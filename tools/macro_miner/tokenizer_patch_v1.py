#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v18_0.omega_common_v1 import write_hashed_json
from cdel.v19_0.common_v1 import canon_hash_obj, validate_schema

from tools.macro_miner.operator_bank_store_v1 import utc_now_rfc3339


_TOKEN_RE = re.compile(r"^OP_[A-Z0-9_]{3,64}$")


def _canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha_obj(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(_canon_bytes(obj)).hexdigest()


def _is_sha(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == 71 and all(ch in "0123456789abcdef" for ch in value.split(":", 1)[1])


def _load_tokens(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        rows = payload.get("tokens")
    else:
        rows = payload
    if not isinstance(rows, list):
        raise RuntimeError("SCHEMA_FAIL:tokens")
    out = sorted({str(v).strip() for v in rows if str(v).strip()})
    for tok in out:
        if _TOKEN_RE.fullmatch(tok) is None:
            raise RuntimeError(f"SCHEMA_FAIL:token:{tok}")
    return out


def patch_tokenizer(*, tokenizer_path: Path, tokens: list[str]) -> tuple[dict[str, Any], list[str], str, str]:
    payload = json.loads(tokenizer_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL:tokenizer")

    before_hash = _sha_obj(payload)
    model = payload.get("model")
    if not isinstance(model, dict):
        raise RuntimeError("SCHEMA_FAIL:model")

    vocab = model.get("vocab")
    if not isinstance(vocab, dict):
        raise RuntimeError("SCHEMA_FAIL:model.vocab")

    next_id = 0
    if vocab:
        try:
            next_id = max(int(v) for v in vocab.values()) + 1
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("SCHEMA_FAIL:model.vocab_values") from exc

    added: list[str] = []
    for tok in sorted(tokens):
        if tok in vocab:
            continue
        vocab[tok] = int(next_id)
        next_id += 1
        added.append(tok)

    added_tokens = payload.get("added_tokens")
    if added_tokens is None:
        added_tokens = []
    if not isinstance(added_tokens, list):
        raise RuntimeError("SCHEMA_FAIL:added_tokens")

    existing = {str(row.get("content", "")) for row in added_tokens if isinstance(row, dict)}
    for tok in added:
        if tok in existing:
            continue
        added_tokens.append(
            {
                "id": int(vocab[tok]),
                "content": tok,
                "single_word": False,
                "lstrip": False,
                "rstrip": False,
                "normalized": False,
                "special": False,
            }
        )
    payload["added_tokens"] = sorted(added_tokens, key=lambda r: (int(r.get("id", 0)), str(r.get("content", ""))))
    payload["model"] = model
    after_hash = _sha_obj(payload)
    return payload, added, before_hash, after_hash


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="tokenizer_patch_v1")
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--tokens_json", required=True)
    ap.add_argument("--base_model_id", required=True)
    ap.add_argument("--bank_hash", required=True)
    ap.add_argument("--training_corpus_manifest_hash", required=True)
    ap.add_argument("--trained_model_bundle_hash", required=True)
    ap.add_argument("--pointer_update_hash", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--created_at_utc", default="")
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    tokenizer_path = Path(args.tokenizer).resolve()
    out_dir = Path(args.out_dir).resolve()
    tokens = _load_tokens(Path(args.tokens_json).resolve())

    for field in (
        "bank_hash",
        "training_corpus_manifest_hash",
        "trained_model_bundle_hash",
        "pointer_update_hash",
    ):
        value = str(getattr(args, field)).strip()
        if not _is_sha(value):
            raise RuntimeError(f"SCHEMA_FAIL:{field}")

    patched, added, before_hash, after_hash = patch_tokenizer(tokenizer_path=tokenizer_path, tokens=tokens)

    out_dir.mkdir(parents=True, exist_ok=True)
    patched_path = out_dir / "tokenizer_patched_v1.json"
    patched_path.write_bytes(_canon_bytes(patched))

    receipt_payload = {
        "schema_id": "oracle_operator_mining_receipt_v1",
        "id": "sha256:" + ("0" * 64),
        "created_at_utc": str(args.created_at_utc).strip() or utc_now_rfc3339(),
        "base_model_id": str(args.base_model_id),
        "tokenizer_before_hash": before_hash,
        "tokenizer_after_hash": after_hash,
        "added_tokens": added,
        "bank_hash": str(args.bank_hash),
        "training_corpus_manifest_hash": str(args.training_corpus_manifest_hash),
        "trained_model_bundle_hash": str(args.trained_model_bundle_hash),
        "pointer_update_hash": str(args.pointer_update_hash),
    }
    validate_schema(receipt_payload, "oracle_operator_mining_receipt_v1")
    receipt_path, receipt_obj, receipt_hash = write_hashed_json(
        out_dir,
        "oracle_operator_mining_receipt_v1.json",
        receipt_payload,
        id_field="id",
    )
    validate_schema(receipt_obj, "oracle_operator_mining_receipt_v1")

    summary = {
        "schema_version": "tokenizer_patch_summary_v1",
        "patched_tokenizer_path": patched_path.as_posix(),
        "tokenizer_before_hash": before_hash,
        "tokenizer_after_hash": after_hash,
        "added_tokens_u64": len(added),
        "receipt_hash": receipt_hash,
        "receipt_path": receipt_path.as_posix(),
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
