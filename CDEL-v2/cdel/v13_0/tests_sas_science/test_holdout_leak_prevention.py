from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import load_canon_json
from cdel.v13_0.verify_rsi_sas_science_v1 import SASScienceError, verify

from .utils import DEFAULT_DT, DEFAULT_STEPS, run_campaign, simulate_powerlaw


def test_holdout_leak_prevention(tmp_path) -> None:
    positions = {
        "BodyA": simulate_powerlaw(
            p=3,
            mu=1.0,
            dt=DEFAULT_DT,
            steps=DEFAULT_STEPS,
            x0=1.0,
            y0=0.0,
            vx0=0.0,
            vy0=0.8,
        ),
        "BodyB": simulate_powerlaw(
            p=3,
            mu=1.0,
            dt=DEFAULT_DT,
            steps=DEFAULT_STEPS,
            x0=1.4,
            y0=0.0,
            vx0=0.0,
            vy0=0.65,
        ),
    }
    state = run_campaign(tmp_path=tmp_path, positions=positions)

    sealed_dir = state.state_dir / "eval" / "sealed"
    removed = False
    for path in sealed_dir.glob("sha256_*.sealed_science_eval_receipt_v1.json"):
        sealed = load_canon_json(path)
        if sealed.get("eval_kind") == "HELDOUT":
            path.unlink()
            removed = True
            break
    assert removed is True

    with pytest.raises(SASScienceError, match=r"INVALID:EVAL_OUTSIDE_SEALED"):
        verify(Path(state.run_root))
