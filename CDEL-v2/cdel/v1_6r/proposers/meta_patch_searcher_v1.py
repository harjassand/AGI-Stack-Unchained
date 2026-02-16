"""Deterministic meta patch searcher v1 for RSI-4 campaigns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..canon import hash_json, load_canon_json, write_canon_json
from ..constants import meta_identities, require_constants


def propose_meta_patch(*, state_dir: Path, out_dir: Path) -> dict[str, Any] | None:
    constants = require_constants()
    meta = meta_identities()

    meta_patch_set_path = state_dir / "current" / "meta_patch_set_v1.json"
    benchmark_path = state_dir / "current" / "meta_benchmark_pack_v1.json"
    if not meta_patch_set_path.exists() or not benchmark_path.exists():
        return None

    meta_patch_set = load_canon_json(meta_patch_set_path)
    benchmark_pack = load_canon_json(benchmark_path)
    base_set_hash = hash_json(meta_patch_set)
    benchmark_hash = hash_json(benchmark_pack)

    enable = ["HASHCACHE_V1", "CANON_CACHE_V1"]
    proposal = {
        "schema": "meta_patch_proposal_v1",
        "schema_version": 1,
        "patch_id": "",
        "base_meta_patch_set_hash": base_set_hash,
        "enable": enable,
        "disable": [],
        "benchmark_pack_hash": benchmark_hash,
        "equiv_relation_id": constants.get("cmeta", {}).get("meta_equiv_id", "semantic_outputs_v1"),
        "x-provenance": "meta_patch_searcher_v1",
        "x-meta": meta,
    }
    proposal["patch_id"] = hash_json({k: v for k, v in proposal.items() if k != "patch_id"})

    out_dir.mkdir(parents=True, exist_ok=True)
    content_hash = hash_json(proposal).split(":", 1)[1]
    write_canon_json(out_dir / f"{content_hash}.json", proposal)
    return proposal
