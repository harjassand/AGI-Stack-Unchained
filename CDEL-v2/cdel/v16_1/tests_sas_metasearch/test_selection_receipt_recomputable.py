from __future__ import annotations

import json
from pathlib import Path

import pytest

from cdel.v16_1.tests_sas_metasearch.utils import copy_run, daemon_state
from cdel.v16_1.verify_rsi_sas_metasearch_v16_1 import MetaSearchVerifyError, verify


def test_selection_receipt_recomputable(v16_1_run_root: Path, tmp_path: Path) -> None:
    run_root = copy_run(v16_1_run_root, tmp_path / "run_selection_tamper")
    state = daemon_state(run_root)
    cand_path = None
    receipt = None
    for path in sorted((state / "selection").glob("sha256_*.metasearch_selection_receipt_v1.json")):
        obj = json.loads(path.read_text(encoding="utf-8"))
        if obj.get("algo_label") == "candidate":
            cand_path = path
            receipt = obj
            break
    assert cand_path is not None
    assert isinstance(receipt, dict)
    receipt["candidates_considered"][0]["score_components"]["total_score_q32"]["q"] = str(
        int(receipt["candidates_considered"][0]["score_components"]["total_score_q32"]["q"]) + 1
    )
    cand_path.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(MetaSearchVerifyError) as exc:
        verify(state, mode="full")
    assert str(exc.value) == "INVALID:SELECTION_MISMATCH"
