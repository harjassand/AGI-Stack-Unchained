from __future__ import annotations

from .utils import DEFAULT_DT, DEFAULT_STEPS, hooke_positions, load_selected_ir, run_campaign


def test_negative_dataset_hooke_not_newton(tmp_path) -> None:
    positions = {
        "BodyA": hooke_positions(steps=DEFAULT_STEPS, dt=DEFAULT_DT, ax=1.3, ay=0.8, w=0.7),
        "BodyB": hooke_positions(steps=DEFAULT_STEPS, dt=DEFAULT_DT, ax=1.1, ay=0.6, w=0.7, phase=0.6),
    }
    state = run_campaign(tmp_path=tmp_path, positions=positions)
    assert state.result["law_kind"] == "NON_NEWTON_V1"
    selected_ir = load_selected_ir(state)
    assert selected_ir["force_law"]["norm_pow_p"] != 3
