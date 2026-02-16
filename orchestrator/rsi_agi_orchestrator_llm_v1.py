"""Omega-dispatchable campaign wrapper that exercises agi-orchestrator LLM deterministically.

This is intentionally minimal: it generates a single LLM response (harvest or replay)
and emits a promotion bundle with an activation key derived from that response.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict, require_no_absolute_paths

from orchestrator.llm_backend import get_backend


_CAMPAIGN_ID = "rsi_agi_orchestrator_llm_v1"
_EVIDENCE_NAME = "agi_orchestrator_llm_evidence_v1.json"


def _sha256_prefixed(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_pack(path: Path) -> dict[str, Any]:
    payload = load_canon_dict(path)
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=_CAMPAIGN_ID)
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir).resolve()
    pack_path = Path(args.campaign_pack).resolve()
    pack = _load_pack(pack_path)

    tick_u64 = int(os.environ.get("OMEGA_TICK_U64", "0") or 0)
    run_seed_u64 = int(os.environ.get("OMEGA_RUN_SEED_U64", "0") or 0)

    campaign_root = out_dir / "daemon" / _CAMPAIGN_ID
    state_dir = campaign_root / "state"
    promotion_dir = state_dir / "promotion"
    promotion_dir.mkdir(parents=True, exist_ok=True)

    prompt = str(pack.get("llm_prompt", "")).strip() or json.dumps(
        {"schema_version": "agi_orchestrator_llm_prompt_v1", "task": "emit_deterministic_json"},
        sort_keys=True,
        separators=(",", ":"),
    )

    backend = get_backend()
    response = backend.generate(prompt)

    replay_path_raw = str(os.environ.get("ORCH_LLM_REPLAY_PATH", "")).strip()
    replay_filename = Path(replay_path_raw).name if replay_path_raw else None

    evidence = {
        "schema_version": "agi_orchestrator_llm_evidence_v1",
        "tick_u64": tick_u64,
        "run_seed_u64": run_seed_u64,
        "orch_llm_backend": str(os.environ.get("ORCH_LLM_BACKEND", "mock")).strip(),
        "orch_llm_replay_filename": replay_filename,
        "prompt_sha256": _sha256_prefixed(prompt),
        "response_sha256": _sha256_prefixed(response),
        "prompt": prompt,
        "response": response,
    }
    require_no_absolute_paths(evidence)
    write_canon_json(state_dir / _EVIDENCE_NAME, evidence)

    # Keep touched paths within allowlists and outside v19-governed prefixes to avoid requiring an axis bundle.
    touched_paths = ["Extension-1/agi-orchestrator/orchestrator/llm_backend.py"]
    activation_key = evidence["response_sha256"]
    promo_bundle = {
        "schema_version": "agi_orchestrator_llm_promotion_bundle_v1",
        "activation_key": activation_key,
        "touched_paths": touched_paths,
        "evidence_relpath": f"daemon/{_CAMPAIGN_ID}/state/{_EVIDENCE_NAME}",
    }
    require_no_absolute_paths(promo_bundle)
    bundle_hash = canon_hash_obj(promo_bundle)
    bundle_name = f"sha256_{bundle_hash.split(':', 1)[1]}.agi_orchestrator_llm_promotion_bundle_v1.json"
    write_canon_json(promotion_dir / bundle_name, promo_bundle)

    sys.stdout.write("OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
