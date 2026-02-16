from __future__ import annotations

import json
from pathlib import Path

from genesis.core.counterexamples import CounterexampleDB
from genesis.shadow_cdel.forager import evaluate_tests, generate_tests


ROOT = Path(__file__).resolve().parents[2]


def _load_capsule() -> dict:
    return json.loads((ROOT / "genesis" / "capsules" / "seed_capsule.json").read_text(encoding="utf-8"))


def test_forager_deterministic():
    capsule = _load_capsule()
    db = CounterexampleDB()
    tests_a = generate_tests(capsule, db.entries(), seed="0", max_tests=3)
    tests_b = generate_tests(capsule, db.entries(), seed="0", max_tests=3)
    assert [t.test_id for t in tests_a] == [t.test_id for t in tests_b]
    assert [t.input_value for t in tests_a] == [t.input_value for t in tests_b]
    ok, _ = evaluate_tests(capsule, tests_a)
    assert ok
