from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

_CDEL_ROOT = Path(__file__).resolve().parents[3]
if str(_CDEL_ROOT) not in sys.path:
    sys.path.insert(0, str(_CDEL_ROOT))

from cdel.v19_0.common_v1 import load_json_dict
from cdel.v19_0.federation.check_ok_overlap_signature_v1 import check_ok_overlap_signature


def _find_repo_root_with_genesis(start: Path) -> Path | None:
    for root in [start, *start.parents]:
        if (root / "Genesis" / "schema" / "v19_0").exists():
            return root
    return None


def test_pinned_ok_overlap_signature_matches_checker_hashes() -> None:
    repo_root = _find_repo_root_with_genesis(_CDEL_ROOT)
    if repo_root is None:
        pytest.skip("Genesis schemas not available in this checkout")

    os.environ["OMEGA_REPO_ROOT"] = str(repo_root)
    pins = _CDEL_ROOT / "cdel" / "v19_0" / "federation" / "pins"
    signature = load_json_dict(pins / "ok_overlap_signature_v1.json")
    budget = {
        "schema_name": "budget_spec_v1",
        "schema_version": "v19_0",
        "max_steps": 10_000,
        "max_bytes_read": 1_000_000,
        "max_bytes_write": 1_000_000,
        "max_items": 10_000,
        "seed": 19,
        "policy": "SAFE_HALT",
    }
    receipt = check_ok_overlap_signature(signature=signature, budget_spec=budget)
    assert receipt["outcome"] == "ACCEPT"
    assert receipt["reason_code"] == "OK_SIGNATURE_VALID"
