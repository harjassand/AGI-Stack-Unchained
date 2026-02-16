from __future__ import annotations

from .utils import DEFAULT_DT, DEFAULT_STEPS, hooke_positions, run_campaign


def test_newton_always_output_detection(tmp_path) -> None:
    positions = {
        "BodyA": hooke_positions(steps=DEFAULT_STEPS, dt=DEFAULT_DT, ax=1.1, ay=0.6, w=0.9),
        "BodyB": hooke_positions(steps=DEFAULT_STEPS, dt=DEFAULT_DT, ax=1.0, ay=0.5, w=0.9, phase=0.5),
    }
    state = run_campaign(tmp_path=tmp_path, positions=positions)
    assert state.result["law_kind"] == "NON_NEWTON_V1"
