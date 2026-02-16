from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v17_0.runtime.sas_val_run_v1 import run_sas_val


@pytest.fixture(scope="session")
def v17_run_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out_root = tmp_path_factory.mktemp("v17_run") / "rsi_sas_val_v17_0_tick_0001"
    run_sas_val(
        campaign_pack=Path("campaigns/rsi_sas_val_v17_0/rsi_sas_val_pack_v17_0.json"),
        out_dir=out_root,
        campaign_tag="rsi_sas_val_v17_0",
    )
    return out_root


@pytest.fixture(scope="session")
def v17_state_dir(v17_run_root: Path) -> Path:
    return v17_run_root / "daemon" / "rsi_sas_val_v17_0" / "state"
