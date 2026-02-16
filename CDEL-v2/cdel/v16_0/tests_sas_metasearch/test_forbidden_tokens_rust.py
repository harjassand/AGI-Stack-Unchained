from __future__ import annotations

import re
from pathlib import Path

import pytest

from cdel.v16_0.verify_rsi_sas_metasearch_v1 import MetaSearchVerifyError, verify


@pytest.mark.parametrize("token", ["Newton", "gravity", "inverse-square", "1/r^2", "Gm"])
def test_forbidden_tokens_rust(v16_run_root: Path, token: str) -> None:
    src = Path("CDEL-v2/cdel/v16_0/rust/sas_metasearch_rs_v1/src/main.rs")
    original = src.read_text(encoding="utf-8")
    try:
        src.write_text(original + f"\n// {token}\n", encoding="utf-8")
        with pytest.raises(MetaSearchVerifyError, match=rf"INVALID:FORBIDDEN_TOKEN:{re.escape(token)}"):
            verify(v16_run_root, mode="full")
    finally:
        src.write_text(original, encoding="utf-8")
