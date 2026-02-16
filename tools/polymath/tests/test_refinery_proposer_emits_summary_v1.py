from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _seed_script() -> Path:
    return _repo_root() / "tools" / "polymath" / "polymath_seed_flagships_v1.py"


def _proposer_script() -> Path:
    return _repo_root() / "tools" / "polymath" / "polymath_refinery_proposer_v1.py"


def test_refinery_proposer_emits_summary_and_unblocks_after_seed(tmp_path: Path) -> None:
    store_root = tmp_path / "store"
    proposer_before = tmp_path / "proposer_before.json"
    seed_summary = tmp_path / "seed.json"
    proposer_after = tmp_path / "proposer_after.json"

    registry_path = _repo_root() / "polymath" / "registry" / "polymath_domain_registry_v1.json"

    before_run = subprocess.run(
        [
            sys.executable,
            str(_proposer_script()),
            "--registry_path",
            str(registry_path),
            "--store_root",
            str(store_root),
            "--workers",
            "2",
            "--max_domains",
            "32",
            "--summary_path",
            str(proposer_before),
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert int(before_run.returncode) == 0, before_run.stderr

    before_payload = json.loads(proposer_before.read_text(encoding="utf-8"))
    assert int(before_payload.get("proposals_generated_u64", 0)) == 0
    skip_reasons_before = before_payload.get("domains_skipped_by_reason")
    assert isinstance(skip_reasons_before, dict)
    assert int(skip_reasons_before.get("MISSING_STORE_BLOBS", 0)) >= 1

    seed_run = subprocess.run(
        [
            sys.executable,
            str(_seed_script()),
            "--store_root",
            str(store_root),
            "--summary_path",
            str(seed_summary),
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert int(seed_run.returncode) == 0, seed_run.stderr

    after_run = subprocess.run(
        [
            sys.executable,
            str(_proposer_script()),
            "--registry_path",
            str(registry_path),
            "--store_root",
            str(store_root),
            "--workers",
            "2",
            "--max_domains",
            "32",
            "--summary_path",
            str(proposer_after),
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert int(after_run.returncode) == 0, after_run.stderr

    after_payload = json.loads(proposer_after.read_text(encoding="utf-8"))
    assert int(after_payload.get("domains_eligible_u64", 0)) >= 1
    assert int(after_payload.get("proposals_generated_u64", 0)) >= 1
