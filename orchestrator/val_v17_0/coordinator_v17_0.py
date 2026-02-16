"""SAS-VAL coordinator (v17.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v17_0.runtime.sas_val_run_v1 import run_sas_val as run_v17_0


def run_sas_val(*, campaign_pack: Path, out_dir: Path, campaign_tag: str = "rsi_sas_val_v17_0") -> dict[str, Any]:
    return run_v17_0(
        campaign_pack=campaign_pack,
        out_dir=out_dir,
        campaign_tag=campaign_tag,
    )


__all__ = ["run_sas_val"]
