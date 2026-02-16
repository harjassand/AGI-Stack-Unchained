from __future__ import annotations

from .utils import DEFAULT_DT, DEFAULT_STEPS, load_selected_ir, run_campaign, simulate_powerlaw


def test_negative_dataset_inverse_cube_not_newton(tmp_path) -> None:
    positions = {
        "BodyA": simulate_powerlaw(
            p=4,
            mu=1.0,
            dt=DEFAULT_DT,
            steps=DEFAULT_STEPS,
            x0=1.0,
            y0=0.0,
            vx0=0.05,
            vy0=1.0,
        ),
        "BodyB": simulate_powerlaw(
            p=4,
            mu=1.0,
            dt=DEFAULT_DT,
            steps=DEFAULT_STEPS,
            x0=1.4,
            y0=0.0,
            vx0=0.02,
            vy0=0.85,
        ),
    }
    state = run_campaign(tmp_path=tmp_path, positions=positions)
    assert state.result["law_kind"] == "NON_NEWTON_V1"
    selected_ir = load_selected_ir(state)
    assert selected_ir["force_law"]["norm_pow_p"] == 4
