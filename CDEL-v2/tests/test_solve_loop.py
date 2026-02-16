from __future__ import annotations

from cdel.ledger import index as idx
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.solve import _ensure_base_symbols, _task_from_id, solve_task

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


def test_solve_rejects_invalid_candidate_and_does_not_adopt(tmp_path):
    cfg = init_repo(tmp_path)
    priv_good, _ = generate_keypair()
    _, pub_bad = generate_keypair()
    _sealed_defaults(cfg, pub_bad, key_id_from_public_key(pub_bad))

    result = solve_task(
        cfg,
        "pred.lt_k.7",
        max_candidates=1,
        episodes=4,
        seed_key="test-seed",
        private_key=priv_good,
        strategy="template_guided",
    )

    attempts = result.get("attempts") or []
    assert attempts
    assert not any(a.get("accepted") for a in attempts)
    assert all(a.get("adoption_hash") is None for a in attempts)

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    assert idx.latest_adoption_for_concept(conn, "pred.lt_k.7") is None
    assert idx.get_stat_cert_state(conn) is None


def test_solve_respects_capacity_budget_and_alpha_state(tmp_path):
    cfg = init_repo(tmp_path, budget=100000)
    priv, pub = generate_keypair()
    _sealed_defaults(cfg, pub, key_id_from_public_key(pub), alpha_total="2")

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    task = _task_from_id(conn, "pred.lt_k.7")
    _ensure_base_symbols(cfg, conn, task)
    idx.update_budget(conn, 1)
    conn.commit()
    before = idx.get_stat_cert_state(conn)

    result = solve_task(
        cfg,
        "pred.lt_k.7",
        max_candidates=2,
        episodes=4,
        seed_key="test-seed",
        private_key=priv,
        strategy="template_guided",
    )

    attempts = result.get("attempts") or []
    assert attempts
    assert any(a.get("rejection") == "CAPACITY_EXCEEDED" for a in attempts)
    assert not any(a.get("accepted") for a in attempts)
    assert all(a.get("adoption_hash") is None for a in attempts)

    after = idx.get_stat_cert_state(conn)
    assert before == after
