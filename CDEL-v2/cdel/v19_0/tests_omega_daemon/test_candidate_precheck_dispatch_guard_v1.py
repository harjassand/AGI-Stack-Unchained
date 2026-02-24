from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error
from cdel.v19_0 import verify_rsi_omega_daemon_v1 as verifier


def test_candidate_precheck_not_required_for_failed_ge_dispatch(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    verifier._verify_candidate_precheck_for_dispatch(
        state_root=state_root,
        dispatch_payload={
            "campaign_id": "rsi_ge_symbiotic_optimizer_sh1_v0_1",
            "return_code": 1,
            "subrun": {"subrun_root_rel": "subruns/failed_dispatch"},
        },
    )


def test_candidate_precheck_required_for_successful_ge_dispatch(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True, exist_ok=True)
    with pytest.raises(OmegaV18Error, match="MISSING_STATE_INPUT"):
        verifier._verify_candidate_precheck_for_dispatch(
            state_root=state_root,
            dispatch_payload={
                "campaign_id": "rsi_ge_symbiotic_optimizer_sh1_v0_1",
                "return_code": 0,
                "subrun": {"subrun_root_rel": "subruns/success_dispatch"},
            },
        )
