from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v13_0.verify_rsi_sas_science_v1 import SASScienceError, verify

from .utils import DEFAULT_DT, DEFAULT_STEPS, run_campaign, simulate_powerlaw


def test_replay_sealed_eval_match(tmp_path) -> None:
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

    eval_dir = state.state_dir / "eval" / "reports"
    report_path = next(eval_dir.glob("sha256_*.sas_science_eval_report_v1.json"))
    report = load_canon_json(report_path)
    q_val = int(report["metrics"]["mse_accel_q32"]["q"])
    report["metrics"]["mse_accel_q32"]["q"] = str(q_val + 1)
    new_hash = sha256_prefixed(canon_bytes(report))
    new_path = eval_dir / f"sha256_{new_hash.split(':',1)[1]}.sas_science_eval_report_v1.json"
    write_canon_json(new_path, report)
    report_path.unlink()

    with pytest.raises(SASScienceError, match=r"INVALID:SEALED_EVAL_RECEIPT_MISMATCH"):
        verify(Path(state.run_root))
