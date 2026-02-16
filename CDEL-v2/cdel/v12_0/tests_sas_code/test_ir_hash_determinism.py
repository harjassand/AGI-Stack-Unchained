from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json
from cdel.v12_0.sas_code_ir_v1 import compute_algo_id, validate_ir


def test_ir_hash_determinism() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    path = repo_root / "campaigns" / "rsi_sas_code_v12_0" / "baseline_bubble_sort_v1.sas_code_ir_v1.json"
    ir = load_canon_json(path)
    validate_ir(ir)
    first = compute_algo_id(ir)
    second = compute_algo_id(ir)
    assert first == second
    assert ir["algo_id"] == first
