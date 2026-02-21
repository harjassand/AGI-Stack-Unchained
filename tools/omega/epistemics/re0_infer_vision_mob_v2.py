"""RE0 vision inferencer emitting epistemic_model_output_v2 + mob receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common_v1 import atomic_write_bytes, atomic_write_canon_json, canon_bytes, canon_hash_obj, ensure_sha256, hash_bytes, load_canon_dict
except Exception:  # pragma: no cover
    from common_v1 import atomic_write_bytes, atomic_write_canon_json, canon_bytes, canon_hash_obj, ensure_sha256, hash_bytes, load_canon_dict


def _load_segment_receipt(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path.resolve())
    if str(payload.get("schema_version", "")).strip() != "epistemic_segment_receipt_v1":
        raise RuntimeError("SCHEMA_FAIL")
    receipt_id = ensure_sha256(payload.get("segment_receipt_id"))
    no_id = dict(payload)
    no_id.pop("segment_receipt_id", None)
    if canon_hash_obj(no_id) != receipt_id:
        raise RuntimeError("NONDETERMINISTIC")
    return payload


def _claims_from_segment_blobs(
    *,
    outbox_root: Path,
    output_blob_ids: list[str],
    max_claims: int,
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for idx, blob_id in enumerate(output_blob_ids[:max_claims]):
        segment_blob_id = ensure_sha256(blob_id)
        blob_path = outbox_root / "blobs" / "sha256" / segment_blob_id.split(":", 1)[1]
        if not blob_path.exists() or not blob_path.is_file():
            raise RuntimeError("MISSING_INPUT")
        blob = blob_path.read_bytes()
        if hash_bytes(blob) != segment_blob_id:
            raise RuntimeError("HASH_MISMATCH")
        try:
            segment_payload = json.loads(blob.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("SCHEMA_FAIL") from exc
        if not isinstance(segment_payload, dict):
            raise RuntimeError("SCHEMA_FAIL")
        prefix = str(segment_payload.get("preview_sha256_prefix", "")).strip()
        if not prefix:
            raise RuntimeError("SCHEMA_FAIL")
        claims.append(
            {
                "claim_text": f"VISION_FRAME_{idx}:{prefix}",
                "confidence_f64": 0.5,
                "source_span": f"segment:{idx}",
            }
        )
    if not claims:
        claims.append({"claim_text": "VISION_EMPTY", "confidence_f64": 0.0, "source_span": "segment:none"})
    return claims


def run(
    *,
    outbox_root: Path,
    segment_receipt_path: Path,
    out_dir: Path,
    episode_id: str,
    model_id: str,
    model_contract_id: str,
    prompt_template_id: str,
    seed_lineage_id: str,
    runtime_profile_id: str,
    sandbox_profile_id: str,
    sandbox_receipt_id: str,
    runtime_limits_receipt_id: str,
    max_claims: int,
) -> dict[str, Any]:
    outbox_root = outbox_root.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    episode_id = ensure_sha256(episode_id)
    model_contract_id = ensure_sha256(model_contract_id)
    seed_lineage_id = ensure_sha256(seed_lineage_id)
    runtime_profile_id = ensure_sha256(runtime_profile_id)
    sandbox_profile_id = ensure_sha256(sandbox_profile_id)
    sandbox_receipt_id = ensure_sha256(sandbox_receipt_id)
    runtime_limits_receipt_id = ensure_sha256(runtime_limits_receipt_id)

    segment_receipt = _load_segment_receipt(segment_receipt_path)
    if ensure_sha256(segment_receipt.get("episode_id")) != episode_id:
        raise RuntimeError("NONDETERMINISTIC")
    output_blob_ids = segment_receipt.get("output_blob_ids")
    if not isinstance(output_blob_ids, list):
        raise RuntimeError("SCHEMA_FAIL")
    claims = _claims_from_segment_blobs(
        outbox_root=outbox_root,
        output_blob_ids=[str(row) for row in output_blob_ids],
        max_claims=max(1, int(max_claims)),
    )
    claims_blob_payload = {
        "schema_version": "epistemic_mob_claims_blob_v1",
        "episode_id": episode_id,
        "claims": claims,
    }
    claims_blob = canon_bytes(claims_blob_payload)
    mob_blob_id = hash_bytes(claims_blob)
    blob_path = outbox_root / "blobs" / "sha256" / mob_blob_id.split(":", 1)[1]
    if blob_path.exists():
        if hash_bytes(blob_path.read_bytes()) != mob_blob_id:
            raise RuntimeError("HASH_MISMATCH")
    else:
        atomic_write_bytes(blob_path, claims_blob)

    mob_payload = {
        "schema_version": "epistemic_model_output_v2",
        "mob_id": "sha256:" + ("0" * 64),
        "mob_receipt_id": "sha256:" + ("0" * 64),
        "episode_id": episode_id,
        "model_id": str(model_id),
        "model_contract_id": model_contract_id,
        "prompt_template_id": str(prompt_template_id),
        "seed_lineage_id": seed_lineage_id,
        "runtime_profile_id": runtime_profile_id,
        "content_kind": "BLOB_REF",
        "mob_blob_id": mob_blob_id,
        "mob_media_type": "application/x.epistemic.claims+json",
        "metadata": {
            "segment_receipt_id": str(segment_receipt.get("segment_receipt_id", "")),
            "segment_count_u64": int(segment_receipt.get("segment_count_u64", 0)),
        },
    }
    mob_payload["mob_id"] = canon_hash_obj(
        {
            k: v
            for k, v in mob_payload.items()
            if k not in {"mob_id", "mob_receipt_id"}
        }
    )

    mob_receipt = {
        "schema_version": "epistemic_mob_receipt_v1",
        "mob_receipt_id": "sha256:" + ("0" * 64),
        "mob_id": str(mob_payload["mob_id"]),
        "episode_id": episode_id,
        "model_id": str(model_id),
        "model_contract_id": model_contract_id,
        "prompt_template_id": str(prompt_template_id),
        "seed_lineage_id": seed_lineage_id,
        "runtime_profile_id": runtime_profile_id,
        "mob_blob_id": mob_blob_id,
        "sandbox_profile_id": sandbox_profile_id,
        "model_invocation_inputs_hash": canon_hash_obj(
            {
                "segment_receipt_id": str(segment_receipt.get("segment_receipt_id", "")),
                "segment_output_blob_ids": [str(row) for row in output_blob_ids],
                "model_id": str(model_id),
                "prompt_template_id": str(prompt_template_id),
            }
        ),
        "runtime_limits_receipt_id": runtime_limits_receipt_id,
        "sandbox_receipt_id": sandbox_receipt_id,
    }
    mob_receipt["mob_receipt_id"] = canon_hash_obj({k: v for k, v in mob_receipt.items() if k != "mob_receipt_id"})
    mob_payload["mob_receipt_id"] = str(mob_receipt["mob_receipt_id"])

    mob_path = out_dir / f"sha256_{str(mob_payload['mob_id']).split(':', 1)[1]}.epistemic_model_output_v2.json"
    receipt_path = out_dir / f"sha256_{str(mob_receipt['mob_receipt_id']).split(':', 1)[1]}.epistemic_mob_receipt_v1.json"
    atomic_write_canon_json(mob_path, mob_payload)
    atomic_write_canon_json(receipt_path, mob_receipt)

    return {
        "episode_id": episode_id,
        "mob_id": str(mob_payload["mob_id"]),
        "mob_path": str(mob_path),
        "mob_receipt_id": str(mob_receipt["mob_receipt_id"]),
        "mob_receipt_path": str(receipt_path),
        "mob_blob_id": mob_blob_id,
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_infer_vision_mob_v2")
    ap.add_argument("--outbox_root", default=".omega_cache/epistemic_outbox")
    ap.add_argument("--segment_receipt_path", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--episode_id", required=True)
    ap.add_argument("--model_id", default="RE0_VISION_EXTRACTOR_V2")
    ap.add_argument("--model_contract_id", required=True)
    ap.add_argument("--prompt_template_id", default="VISION_PROMPT_V1")
    ap.add_argument("--seed_lineage_id", required=True)
    ap.add_argument("--runtime_profile_id", required=True)
    ap.add_argument("--sandbox_profile_id", required=True)
    ap.add_argument("--sandbox_receipt_id", required=True)
    ap.add_argument("--runtime_limits_receipt_id", required=True)
    ap.add_argument("--max_claims", type=int, default=128)
    args = ap.parse_args()
    result = run(
        outbox_root=Path(args.outbox_root),
        segment_receipt_path=Path(args.segment_receipt_path),
        out_dir=Path(args.out_dir),
        episode_id=str(args.episode_id),
        model_id=str(args.model_id),
        model_contract_id=str(args.model_contract_id),
        prompt_template_id=str(args.prompt_template_id),
        seed_lineage_id=str(args.seed_lineage_id),
        runtime_profile_id=str(args.runtime_profile_id),
        sandbox_profile_id=str(args.sandbox_profile_id),
        sandbox_receipt_id=str(args.sandbox_receipt_id),
        runtime_limits_receipt_id=str(args.runtime_limits_receipt_id),
        max_claims=max(1, int(args.max_claims)),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
