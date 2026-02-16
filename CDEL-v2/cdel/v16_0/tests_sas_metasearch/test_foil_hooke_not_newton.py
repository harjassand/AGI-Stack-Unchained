from __future__ import annotations

from pathlib import Path

from .utils import selected_law_from_v13_run


def test_foil_hooke_not_newton(v16_run_root: Path) -> None:
    foil = (
        v16_run_root
        / "daemon"
        / "rsi_sas_metasearch_v16_0"
        / "state"
        / "science_runs"
        / "candidate_foil_hooke"
    )
    assert selected_law_from_v13_run(foil) not in {"NEWTON_CENTRAL_V1", "NEWTON_NBODY_V1"}
