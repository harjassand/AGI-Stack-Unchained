from __future__ import annotations

from pathlib import Path

from cdel.bench.solve_suite import SolveSuiteConfig, run_solve_suite
from cdel.ledger import index as idx
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.solve import _ensure_base_symbols, _task_from_id

from tests.conftest import init_repo


def _sealed_defaults(cfg, pub_key: str, key_id: str, alpha_total: str = "1e-4") -> None:
    cfg.data["sealed"] = {
        "public_key": pub_key,
        "key_id": key_id,
        "public_keys": [],
        "prev_public_keys": [],
        "alpha_total": alpha_total,
        "alpha_schedule": {
            "name": "p_series",
            "exponent": 2,
            "coefficient": "0.60792710185402662866",
        },
        "eval_harness_id": "toy-harness-v1",
        "eval_harness_hash": "harness-hash",
        "eval_suite_hash": "suite-hash",
    }


def test_solve_suite_stops_on_capacity_exhaustion(tmp_path: Path) -> None:
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    _sealed_defaults(cfg, pub_key, key_id_from_public_key(pub_key), alpha_total="1000")

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    for task_id in ("arith.add_k.0", "arith.add_k.1"):
        task = _task_from_id(conn, task_id)
        _ensure_base_symbols(cfg, conn, task)

    out_dir = tmp_path / "out"
    suite_cfg = SolveSuiteConfig(
        suite="trackA",
        limit=2,
        max_candidates=1,
        episodes=4,
        seed_key="test-seed",
        budget_per_task=1,
        max_context_symbols=10,
        strategy="template_guided",
    )
    result = run_solve_suite(out_dir, cfg, suite_cfg, private_key=priv_key)

    assert result.get("stop_reason") == "capacity_exhausted"
    tasks = result.get("tasks") or []
    assert tasks
    assert any(row.get("capacity_exhausted") for row in tasks)
    for row in tasks:
        for attempt in row.get("attempts") or []:
            if attempt.get("rejection") == "CAPACITY_EXCEEDED":
                assert attempt.get("adoption_hash") is None


def test_alpha_not_advanced_on_capacity_reject(tmp_path: Path) -> None:
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    _sealed_defaults(cfg, pub_key, key_id_from_public_key(pub_key), alpha_total="1000")

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    task = _task_from_id(conn, "arith.add_k.0")
    _ensure_base_symbols(cfg, conn, task)
    before = idx.get_stat_cert_state(conn)

    out_dir = tmp_path / "out"
    suite_cfg = SolveSuiteConfig(
        suite="trackA",
        limit=1,
        max_candidates=1,
        episodes=4,
        seed_key="test-seed",
        budget_per_task=1,
        max_context_symbols=10,
        strategy="template_guided",
    )
    run_solve_suite(out_dir, cfg, suite_cfg, private_key=priv_key)

    after = idx.get_stat_cert_state(conn)
    assert before == after
