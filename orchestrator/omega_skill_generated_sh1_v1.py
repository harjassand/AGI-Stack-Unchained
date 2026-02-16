"""Deterministic SH1-generated capability scaffold campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj, require_no_absolute_paths


_CAMPAIGN_ID_DEFAULT = "rsi_domain_skill_generated_sh1_v1"
_PROMOTION_SCHEMA = "omega_skill_generated_sh1_promotion_bundle_v1"
_SKILL_ID = "ARCH_SYNTH_V11"
_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def _slug_token(value: str) -> str:
    out = _TOKEN_RE.sub("_", str(value).strip().lower()).strip("_")
    return out or "x"


def _sha256_prefixed(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omega_skill_generated_sh1_v1")
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args(argv)

    campaign_pack = Path(args.campaign_pack).resolve()
    out_dir = Path(args.out_dir).resolve()
    pack = _load_pack(campaign_pack)

    campaign_id = str(pack.get("campaign_id", "")).strip() or _CAMPAIGN_ID_DEFAULT
    domain_slug = _slug_token(str(pack.get("domain_slug", "frontier_probe")))
    tick_u64 = max(0, int(os.environ.get("OMEGA_TICK_U64", "0") or "0"))
    run_seed_u64 = max(0, int(os.environ.get("OMEGA_RUN_SEED_U64", "0") or "0"))
    prompt = str(pack.get("skill_prompt", "")).strip() or f"synthesize capability scaffold for domain:{domain_slug}"

    state_dir = out_dir / "daemon" / campaign_id / "state"
    reports_dir = state_dir / "reports"
    promotion_dir = state_dir / "promotion"
    reports_dir.mkdir(parents=True, exist_ok=True)
    promotion_dir.mkdir(parents=True, exist_ok=True)

    inputs_payload = {
        "campaign_id": campaign_id,
        "domain_slug": domain_slug,
        "tick_u64": int(tick_u64),
        "run_seed_u64": int(run_seed_u64),
        "skill_prompt": prompt,
    }
    inputs_hash = _sha256_prefixed(json.dumps(inputs_payload, sort_keys=True, separators=(",", ":")))
    novelty_q32 = int(((len(domain_slug) % 7) + 1) * (1 << 29))
    report = {
        "schema_version": "omega_skill_report_v1",
        "skill_id": _SKILL_ID,
        "tick_u64": int(tick_u64),
        "inputs_hash": inputs_hash,
        "metrics": {
            "frontier_signal_q32": {"q": int(1 << 32)},
            "domain_novelty_q32": {"q": int(novelty_q32)},
            "dispatch_attempts_u64": int(1),
        },
        "flags": [
            "SH1_GENERATED",
            "WILD_MODE" if str(os.environ.get("OMEGA_BLACKBOX", "")).strip() else "STRICT_MODE",
        ],
        "recommendations": [
            {
                "kind": "REGISTER_CAPABILITY",
                "detail": f"maintain active probing for domain={domain_slug}",
            }
        ],
    }
    require_no_absolute_paths(report)
    report_hash = canon_hash_obj(report)
    report_hash_hex = report_hash.split(":", 1)[1]
    report_relpath = f"daemon/{campaign_id}/state/reports/sha256_{report_hash_hex}.omega_skill_report_v1.json"
    write_canon_json(reports_dir / f"sha256_{report_hash_hex}.omega_skill_report_v1.json", report)
    write_canon_json(reports_dir / "omega_skill_report_v1.json", report)

    promotion_bundle = {
        "schema_version": _PROMOTION_SCHEMA,
        "domain_id": domain_slug,
        "activation_key": report_hash,
        "touched_paths": [
            f"orchestrator/omega_skill_{domain_slug}_v1.py",
            f"campaigns/{campaign_id}/rsi_domain_skill_{domain_slug}_pack_v1.json",
        ],
        "skill_report_relpath": report_relpath,
    }
    require_no_absolute_paths(promotion_bundle)
    bundle_hash = canon_hash_obj(promotion_bundle)
    bundle_hash_hex = bundle_hash.split(":", 1)[1]
    write_canon_json(
        promotion_dir / f"sha256_{bundle_hash_hex}.{_PROMOTION_SCHEMA}.json",
        promotion_bundle,
    )

    sys.stdout.write("OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
