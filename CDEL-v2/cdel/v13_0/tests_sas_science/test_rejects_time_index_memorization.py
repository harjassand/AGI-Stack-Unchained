from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import load_canon_json
from cdel.v13_0.sas_science_generator_v1 import enumerate_candidate_irs
from cdel.v13_0.sas_science_ir_v1 import SASScienceIRError, compute_complexity, compute_theory_id, validate_ir

from .utils import build_manifest


def test_rejects_time_index_memorization() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    ir_policy = load_canon_json(repo_root / "campaigns" / "rsi_sas_science_v13_0" / "sas_science_ir_policy_v1.json")
    manifest = build_manifest(bodies=["Body"])
    ir = enumerate_candidate_irs(manifest)[0]
    ir["parameters"] = {
        "mu_sources_q32": [
            {
                "schema_version": "q32_v1",
                "shift": 32,
                "q": "0",
                "time_index": "42",
            }
        ]
    }
    ir["complexity"] = compute_complexity(ir)
    ir["theory_id"] = compute_theory_id(ir)
    with pytest.raises(SASScienceIRError, match=r"INVALID:IR_FORBIDDEN_TIME_DEPENDENCE"):
        validate_ir(ir, manifest=manifest, ir_policy=ir_policy)
