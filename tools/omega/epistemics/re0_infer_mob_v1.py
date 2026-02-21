"""RE0 model-output builder for epistemic MOB payloads (slice 1 CANON_JSON only)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .common_v1 import atomic_write_canon_json, canon_hash_obj, ensure_sha256, load_canon_dict
except Exception:  # pragma: no cover
    from common_v1 import atomic_write_canon_json, canon_hash_obj, ensure_sha256, load_canon_dict


def _claims_from_segments(segments: list[str], *, max_claims: int, max_claim_len: int) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for segment in segments[:max_claims]:
        text = str(segment).strip()
        if not text:
            continue
        if len(text) > max_claim_len:
            text = text[:max_claim_len]
        out.append({"claim_text": text, "confidence_f64": 0.5})
    if not out:
        out.append({"claim_text": "NO_CONTENT", "confidence_f64": 0.0})
    return out


def run(
    *,
    segment_path: Path,
    out_path: Path,
    episode_id: str,
    model_id: str,
    prompt_template_id: str,
    max_claims: int,
    max_claim_len: int,
) -> dict[str, object]:
    seg = load_canon_dict(segment_path)
    segments = seg.get("segments")
    if not isinstance(segments, list):
        raise RuntimeError("SCHEMA_FAIL")
    claims = _claims_from_segments([str(row) for row in segments], max_claims=max_claims, max_claim_len=max_claim_len)
    content_obj = {"claims": claims}
    content_id = canon_hash_obj(content_obj)
    payload = {
        "schema_version": "epistemic_model_output_v1",
        "mob_id": "sha256:" + ("0" * 64),
        "episode_id": ensure_sha256(episode_id),
        "model_id": str(model_id),
        "prompt_template_id": str(prompt_template_id),
        "content_kind": "CANON_JSON",
        "content_id": content_id,
        "claims": claims,
        "metadata": {
            "segment_output_id": str(seg.get("segment_output_id", "")),
            "segmenter_id": str(seg.get("segmenter_id", "")),
        },
    }
    payload["mob_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "mob_id"})
    atomic_write_canon_json(out_path, payload)
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(prog="re0_infer_mob_v1")
    ap.add_argument("--segment_path", required=True)
    ap.add_argument("--out_path", required=True)
    ap.add_argument("--episode_id", required=True)
    ap.add_argument("--model_id", default="RE0_MOB_EXTRACTOR_V1")
    ap.add_argument("--prompt_template_id", default="PROMPT_WEB_HTML_CLAIMS_V1")
    ap.add_argument("--max_claims", type=int, default=64)
    ap.add_argument("--max_claim_len", type=int, default=1024)
    args = ap.parse_args()
    payload = run(
        segment_path=Path(args.segment_path).resolve(),
        out_path=Path(args.out_path).resolve(),
        episode_id=str(args.episode_id),
        model_id=str(args.model_id),
        prompt_template_id=str(args.prompt_template_id),
        max_claims=max(1, int(args.max_claims)),
        max_claim_len=max(1, int(args.max_claim_len)),
    )
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
