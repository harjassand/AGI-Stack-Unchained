from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json

REPO_ROOT = Path(__file__).resolve().parents[4]
ORCH_ROOT = REPO_ROOT / "Extension-1" / "agi-orchestrator"
if str(ORCH_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCH_ROOT))

from orchestrator.tools.build_metasearch_corpus_v16_0 import build_corpus  # noqa: E402


def repo_root() -> Path:
    return REPO_ROOT


def campaign_pack_path() -> Path:
    return REPO_ROOT / "campaigns" / "rsi_sas_metasearch_v16_0" / "rsi_sas_metasearch_pack_v1.json"


def daemon_config_dir() -> Path:
    return REPO_ROOT / "daemon" / "rsi_sas_metasearch_v16_0" / "config"


def _sync_pack_hashes() -> None:
    campaign_root = REPO_ROOT / "campaigns" / "rsi_sas_metasearch_v16_0"
    daemon_root = REPO_ROOT / "daemon" / "rsi_sas_metasearch_v16_0" / "config"

    pack = load_canon_json(campaign_root / "rsi_sas_metasearch_pack_v1.json")
    if not isinstance(pack, dict):
        raise RuntimeError("invalid pack")

    def _h(path: Path) -> str:
        return sha256_prefixed(path.read_bytes())

    pack["policy_hash"] = _h(campaign_root / "sas_metasearch_policy_v1.json")
    pack["baseline_search_config_hash"] = _h(campaign_root / "baseline_search_config_v1.json")
    pack["candidate_search_config_hash"] = _h(campaign_root / "candidate_search_config_v1.json")
    pack["gravity_dataset_manifest_hash"] = _h(campaign_root / "datasets" / "gravity_dataset_manifest_v1.json")
    pack["gravity_dataset_hash"] = _h(campaign_root / "datasets" / "gravity_dataset.csv")
    pack["hooke_dataset_manifest_hash"] = _h(campaign_root / "datasets" / "hooke_dataset_manifest_v1.json")
    pack["hooke_dataset_hash"] = _h(campaign_root / "datasets" / "hooke_dataset.csv")
    pack["trace_corpus_hash"] = _h(campaign_root / "trace_corpus" / "science_trace_corpus_suitepack_dev_v1.json")

    write_canon_json(campaign_root / "rsi_sas_metasearch_pack_v1.json", pack)
    write_canon_json(daemon_root / "rsi_sas_metasearch_pack_v1.json", pack)


def build_and_freeze_corpus(min_cases: int = 100) -> dict[str, Any]:
    daemon_corpus = daemon_config_dir() / "trace_corpus" / "science_trace_corpus_suitepack_dev_v1.json"
    result = build_corpus(
        runs_root=REPO_ROOT / "runs",
        out_path=daemon_corpus,
        min_cases=min_cases,
    )
    campaign_corpus = REPO_ROOT / "campaigns" / "rsi_sas_metasearch_v16_0" / "trace_corpus" / "science_trace_corpus_suitepack_dev_v1.json"
    write_canon_json(campaign_corpus, load_canon_json(daemon_corpus))
    _sync_pack_hashes()
    return result


def selected_law_from_v13_run(run_root: Path) -> str:
    promo = sorted((run_root / "state" / "promotion").glob("sha256_*.sas_science_promotion_bundle_v1.json"))
    if len(promo) != 1:
        raise RuntimeError("missing promo")
    obj = load_canon_json(promo[0])
    if not isinstance(obj, dict):
        raise RuntimeError("invalid promo")
    return str(obj.get("discovery_bundle", {}).get("law_kind"))


def trace_rows(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        out.append(json.loads(raw))
    return out


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
