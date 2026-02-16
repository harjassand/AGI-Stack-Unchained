from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json


def test_simd_neon_gate(v17_state_dir: Path) -> None:
    trace = load_canon_json(sorted((v17_state_dir / "candidate" / "trace").glob("sha256_*.val_decoded_trace_v1.json"))[0])
    mnemonics = [str(row["mnemonic"]).lower() for row in trace["instructions"]]
    assert "ld1" in mnemonics
    assert "st1" in mnemonics
    assert any(m in {"eor", "and", "orr", "add", "sub", "sha256h", "sha256h2", "sha256su0", "sha256su1"} for m in mnemonics)
