from __future__ import annotations

from pathlib import Path

from cdel.v1_5r.canon import hash_json, load_canon_json
from cdel.v1_5r.cmeta.translation import load_benchmark_pack, translate_validate
from cdel.v1_5r.constants import require_constants


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_v1_5r_meta_patch_translation_positive() -> None:
    constants = require_constants()
    bench_path = _repo_root() / "campaigns" / "rsi_real_portfolio_v1" / "meta_benchmark_pack_v1.json"
    benchmark_pack = load_benchmark_pack(bench_path)
    benchmark_hash = hash_json(load_canon_json(bench_path))
    base_patch_set = {"schema": "meta_patch_set_v1", "schema_version": 1, "active_patch_ids": []}
    proposal = {
        "schema": "meta_patch_proposal_v1",
        "schema_version": 1,
        "patch_id": "",
        "base_meta_patch_set_hash": hash_json(base_patch_set),
        "enable": ["HASHCACHE_V1", "CANON_CACHE_V1"],
        "disable": [],
        "benchmark_pack_hash": benchmark_hash,
        "equiv_relation_id": constants.get("cmeta", {}).get("meta_equiv_id", "semantic_outputs_v1"),
        "x-provenance": "meta_patch_searcher_v1",
    }
    proposal["patch_id"] = hash_json({k: v for k, v in proposal.items() if k != "patch_id"})

    cert = translate_validate({**proposal, "epoch_id": "bench"}, benchmark_pack)
    overall = cert.get("overall", {})
    assert overall.get("equiv_ok") is True
    assert overall.get("dominance_ok") is True
    assert overall.get("strict_improve_ok") is True
