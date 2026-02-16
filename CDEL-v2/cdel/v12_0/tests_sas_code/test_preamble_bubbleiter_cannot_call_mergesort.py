from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import load_canon_json, sha256_prefixed, write_canon_json
from cdel.v12_0.verify_rsi_sas_code_v1 import verify

from .utils import build_state


def test_preamble_bubbleiter_cannot_call_mergesort(tmp_path: Path) -> None:
    state = build_state(tmp_path)
    repo_root = Path(__file__).resolve().parents[4]
    preamble_path = repo_root / "CDEL-v2" / "cdel" / "v12_0" / "lean" / "SASCodePreambleV12.lean"
    original = preamble_path.read_text(encoding="utf-8")
    try:
        tampered = original.replace("bubblePass xs", "mergeSort xs", 1)
        preamble_path.write_text(tampered, encoding="utf-8")
        new_hash = sha256_prefixed(preamble_path.read_bytes())
        pack_path = state.config_dir / "rsi_sas_code_pack_v1.json"
        pack = load_canon_json(pack_path)
        pack["lean_preamble_sha256"] = new_hash
        write_canon_json(pack_path, pack)
        with pytest.raises(Exception) as exc:
            verify(state.state_dir, mode="full")
        assert "INVALID:PREAMBLE_SEMANTICS_TAMPER" in str(exc.value)
    finally:
        preamble_path.write_text(original, encoding="utf-8")
