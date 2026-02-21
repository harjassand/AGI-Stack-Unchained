"""RE0 deterministic hostile-instruction stripping (R7 baseline)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .common_v1 import atomic_write_bytes, atomic_write_canon_json, canon_hash_obj, ensure_sha256, hash_bytes
except Exception:  # pragma: no cover
    from common_v1 import atomic_write_bytes, atomic_write_canon_json, canon_hash_obj, ensure_sha256, hash_bytes


_STRIP_TOKENS = (
    "ignore previous instructions",
    "system prompt",
    "developer instructions",
    "tool call",
    "act as ",
    "you are chatgpt",
    "<script",
    "javascript:",
)


def _strip_hostile(text: str) -> tuple[str, list[str]]:
    removed_line_hashes: list[str] = []
    kept: list[str] = []
    for raw_line in text.splitlines():
        line = str(raw_line)
        lower = line.lower()
        if any(token in lower for token in _STRIP_TOKENS):
            removed_line_hashes.append(
                canon_hash_obj(
                    {
                        "schema_version": "epistemic_instruction_removed_line_v1",
                        "line": line,
                    }
                )
            )
            continue
        kept.append(line)
    return "\n".join(kept), removed_line_hashes


def run(
    *,
    outbox_root: Path,
    input_blob_id: str,
    instruction_strip_contract_id: str | None = None,
    strip_policy_id: str | None = None,
) -> dict[str, str | int]:
    outbox_root = outbox_root.resolve()
    input_blob_id = ensure_sha256(input_blob_id)
    contract_id_raw = instruction_strip_contract_id if instruction_strip_contract_id is not None else strip_policy_id
    if contract_id_raw is None:
        raise RuntimeError("SCHEMA_FAIL")
    instruction_strip_contract_id = ensure_sha256(contract_id_raw)
    input_path = outbox_root / "blobs" / "sha256" / input_blob_id.split(":", 1)[1]
    if not input_path.exists() or not input_path.is_file():
        raise RuntimeError("MISSING_INPUT")

    input_bytes = input_path.read_bytes()
    if hash_bytes(input_bytes) != input_blob_id:
        raise RuntimeError("HASH_MISMATCH")
    text = input_bytes.decode("utf-8", errors="replace")
    stripped_text, removed_line_hashes = _strip_hostile(text)
    output_bytes = stripped_text.encode("utf-8")
    output_blob_id = hash_bytes(output_bytes)
    output_path = outbox_root / "blobs" / "sha256" / output_blob_id.split(":", 1)[1]
    if output_path.exists():
        if hash_bytes(output_path.read_bytes()) != output_blob_id:
            raise RuntimeError("HASH_MISMATCH")
    else:
        atomic_write_bytes(output_path, output_bytes)

    removed_spans_hash = canon_hash_obj(
        {
            "schema_version": "epistemic_instruction_removed_span_set_v1",
            "removed_span_hashes": removed_line_hashes,
        }
    )
    deterministic_hash = canon_hash_obj(
        {
            "schema_version": "epistemic_instruction_strip_binding_v1",
            "input_blob_id": input_blob_id,
            "output_blob_id": output_blob_id,
            "instruction_strip_contract_id": instruction_strip_contract_id,
            "removed_span_hashes": removed_line_hashes,
            "removed_spans_hash": removed_spans_hash,
        }
    )
    receipt = {
        "schema_version": "epistemic_instruction_strip_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "input_blob_id": input_blob_id,
        "output_blob_id": output_blob_id,
        "instruction_strip_contract_id": instruction_strip_contract_id,
        "removed_span_count_u64": int(len(removed_line_hashes)),
        "removed_span_hashes": removed_line_hashes,
        "removed_spans_hash": removed_spans_hash,
        "deterministic_hash": deterministic_hash,
        "outcome": "OK",
    }
    receipt["receipt_id"] = canon_hash_obj({k: v for k, v in receipt.items() if k != "receipt_id"})
    receipt_id = str(receipt["receipt_id"])
    receipt_path = outbox_root / "receipts" / "instruction_strip" / f"sha256_{receipt_id.split(':', 1)[1]}.epistemic_instruction_strip_receipt_v1.json"
    atomic_write_canon_json(receipt_path, receipt)
    return {
        "input_blob_id": input_blob_id,
        "output_blob_id": output_blob_id,
        "receipt_id": receipt_id,
        "receipt_path": str(receipt_path),
        "removed_span_count_u64": int(len(removed_line_hashes)),
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_instruction_strip_v1")
    ap.add_argument("--outbox_root", default=".omega_cache/epistemic_outbox")
    ap.add_argument("--input_blob_id", required=True)
    ap.add_argument("--instruction_strip_contract_id", default="")
    ap.add_argument("--strip_policy_id", default="")
    args = ap.parse_args()
    contract_id = str(args.instruction_strip_contract_id).strip()
    strip_policy_id = str(args.strip_policy_id).strip()
    if not contract_id and not strip_policy_id:
        raise RuntimeError("SCHEMA_FAIL")
    result = run(
        outbox_root=Path(args.outbox_root),
        input_blob_id=str(args.input_blob_id),
        instruction_strip_contract_id=(contract_id or None),
        strip_policy_id=(strip_policy_id or None),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
