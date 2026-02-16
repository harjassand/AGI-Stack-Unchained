from __future__ import annotations

import json
from pathlib import Path

from cdel.v1_7r.canon import write_canon_json
from tools.polymath.polymath_domain_bootstrap_v1 import bootstrap_domain
from tools.polymath.polymath_refinery_proposer_v1 import run as run_refinery_proposer


def _bootstrap_repo_domain(repo_root: Path, *, store_root: Path, domain_id: str = "genomics_lite") -> dict[str, str]:
    bootstrap = bootstrap_domain(
        domain_id=domain_id,
        domain_name="Genomics Lite",
        topic_ids=["topic:genomics_lite"],
        domains_root=repo_root / "domains",
        store_root=store_root,
        starter_size=18,
    )
    registry = {
        "schema_version": "polymath_domain_registry_v1",
        "domains": [
            {
                "domain_id": str(bootstrap["domain_id"]),
                "domain_name": "Genomics Lite",
                "status": "ACTIVE",
                "created_at_utc": "2026-02-09T00:00:00+00:00",
                "topic_ids": ["topic:genomics_lite"],
                "domain_pack_rel": f"domains/{bootstrap['domain_id']}/domain_pack_v1.json",
                "capability_id": f"RSI_DOMAIN_{str(bootstrap['domain_id']).upper()}",
                "dataset_artifact_sha256s": [],
                "ready_for_conquer": True,
                "ready_for_conquer_reason": "BOOTSTRAPPED",
                "conquered_b": False,
            }
        ],
    }
    registry_path = repo_root / "polymath" / "registry" / "polymath_domain_registry_v1.json"
    write_canon_json(registry_path, registry)
    return {"registry_path": registry_path.as_posix()}


def _proposal_map(store_root: Path) -> dict[tuple[str, str], str]:
    index_path = store_root / "refinery" / "indexes" / "domain_train_to_best.jsonl"
    if not index_path.exists() or not index_path.is_file():
        return {}
    out: dict[tuple[str, str], str] = {}
    for raw in index_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        row = json.loads(raw)
        if not isinstance(row, dict):
            continue
        key = (str(row.get("domain_id", "")), str(row.get("train_sha256", "")))
        out[key] = str(row.get("proposal_id", ""))
    return out


def test_refinery_proposer_is_deterministic(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    store_root = tmp_path / "store"
    info = _bootstrap_repo_domain(repo_root, store_root=store_root)
    registry_path = Path(info["registry_path"])

    result_a = run_refinery_proposer(
        registry_path=registry_path,
        store_root=store_root,
        workers=3,
        max_domains=32,
        repo_root=repo_root,
    )
    map_a = _proposal_map(store_root)
    result_b = run_refinery_proposer(
        registry_path=registry_path,
        store_root=store_root,
        workers=3,
        max_domains=32,
        repo_root=repo_root,
    )
    map_b = _proposal_map(store_root)

    summary_a = result_a["summary"]
    summary_b = result_b["summary"]
    assert isinstance(summary_a, dict)
    assert isinstance(summary_b, dict)
    assert int(summary_a.get("proposals_generated_u64", 0)) >= 1
    assert map_a == map_b
