from __future__ import annotations

from .utils import (
    DEFAULT_DT,
    DEFAULT_STEPS,
    add_noise,
    load_promotion_bundle,
    run_campaign,
    simulate_powerlaw,
)


def test_noisy_planetary_still_newton(tmp_path) -> None:
    base_a = simulate_powerlaw(
        p=3,
        mu=1.0,
        dt=DEFAULT_DT,
        steps=DEFAULT_STEPS,
        x0=1.0,
        y0=0.0,
        vx0=0.0,
        vy0=0.8,
    )
    base_b = simulate_powerlaw(
        p=3,
        mu=1.0,
        dt=DEFAULT_DT,
        steps=DEFAULT_STEPS,
        x0=1.4,
        y0=0.0,
        vx0=0.0,
        vy0=0.65,
    )
    positions = {
        "BodyA": add_noise(base_a, sigma=1e-6, seed=7),
        "BodyB": add_noise(base_b, sigma=1e-6, seed=13),
    }
    state = run_campaign(tmp_path=tmp_path, positions=positions)
    promo = load_promotion_bundle(state)
    assert promo["discovery_bundle"]["law_kind"] in ("NEWTON_CENTRAL_V1", "NEWTON_NBODY_V1")
    assert promo["acceptance_decision"]["pass"] is True
