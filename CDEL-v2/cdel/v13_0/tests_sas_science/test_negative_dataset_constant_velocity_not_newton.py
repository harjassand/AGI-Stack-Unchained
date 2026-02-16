from __future__ import annotations

from .utils import DEFAULT_DT, DEFAULT_STEPS, constant_velocity_positions, load_selected_ir, run_campaign


def test_negative_dataset_constant_velocity_not_newton(tmp_path) -> None:
    positions = {
        "BodyA": constant_velocity_positions(steps=DEFAULT_STEPS, dt=DEFAULT_DT, x0=1.0, y0=0.5, vx=0.08, vy=0.03),
        "BodyB": constant_velocity_positions(steps=DEFAULT_STEPS, dt=DEFAULT_DT, x0=-0.8, y0=1.2, vx=0.04, vy=-0.05),
    }
    state = run_campaign(tmp_path=tmp_path, positions=positions)
    assert state.result["law_kind"] == "NON_NEWTON_V1"
    selected_ir = load_selected_ir(state)
    assert selected_ir["force_law"]["norm_pow_p"] != 3
