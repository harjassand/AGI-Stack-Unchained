"""Canonical AGI_ROOT/SAS_ROOT path handling (v11.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class PathCanonError(RuntimeError):
    pass


def canon_root_v1(agi_root_raw: str | None) -> dict[str, Any]:
    if agi_root_raw is None:
        raise PathCanonError("AGI_ROOT_MISSING")
    agi_root_stripped = agi_root_raw.strip()
    if agi_root_stripped == "":
        raise PathCanonError("AGI_ROOT_MISSING")
    agi_root_canon = str(Path(agi_root_stripped).expanduser().resolve(strict=True)).rstrip("/")
    sas_root_canon = f"{agi_root_canon}/daemon/rsi_arch_synthesis_v11_0"
    return {
        "agi_root_raw": agi_root_raw,
        "agi_root_stripped": agi_root_stripped,
        "agi_root_canon": agi_root_canon,
        "was_trimmed": agi_root_raw != agi_root_stripped,
        "sas_root_canon": sas_root_canon,
        "canon_method": "CANON_ROOT_V1",
    }


def canon_root_v1_for(agi_root_raw: str | None, sas_leaf: str) -> dict[str, Any]:
    canon = canon_root_v1(agi_root_raw)
    canon = dict(canon)
    canon["sas_root_canon"] = f"{canon['agi_root_canon']}/daemon/{sas_leaf}"
    return canon


__all__ = ["canon_root_v1", "canon_root_v1_for", "PathCanonError"]
