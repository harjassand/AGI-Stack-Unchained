"""SAS-Metasearch coordinator (v16.1)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cdel.v16_1.metasearch_run_v1 import run_sas_metasearch as run_v16_1


def _parse_min_corpus_cases() -> int:
    raw = str(os.environ.get("V16_MIN_CORPUS_CASES", "")).strip()
    if not raw:
        return 100
    try:
        parsed = int(raw)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("INVALID:V16_MIN_CORPUS_CASES") from exc
    if parsed < 1 or parsed > 100000:
        raise RuntimeError("INVALID:V16_MIN_CORPUS_CASES")
    return int(parsed)


def run_sas_metasearch(*, campaign_pack: Path, out_dir: Path, campaign_tag: str = "rsi_sas_metasearch_v16_1") -> dict[str, Any]:
    min_corpus_cases = _parse_min_corpus_cases()
    return run_v16_1(
        campaign_pack=campaign_pack,
        out_dir=out_dir,
        campaign_tag=campaign_tag,
        min_corpus_cases=min_corpus_cases,
    )


__all__ = ["run_sas_metasearch"]
