from __future__ import annotations

from pathlib import Path

import cdel.v13_0.verify_rsi_sas_science_v1 as verifier_module
from cdel.v13_0.verify_rsi_sas_science_v1 import verify

from .utils import DEFAULT_DT, DEFAULT_STEPS, run_campaign, simulate_powerlaw


def test_science_verifier_uses_worker_not_per_eval_subprocess(tmp_path: Path, monkeypatch) -> None:
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

    def _forbid(*_args, **_kwargs) -> None:
        raise AssertionError("unexpected subprocess.check_call in v13 verifier replay")

    monkeypatch.setattr(verifier_module.subprocess, "check_call", _forbid, raising=True)
    assert verify(Path(state.run_root), mode="full") == "VALID"
