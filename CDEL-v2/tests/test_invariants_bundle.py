from __future__ import annotations

from pathlib import Path

from cdel.adoption.storage import read_head as read_adoption_head
from cdel.consolidate import consolidate_concept
from cdel.ledger import index as idx
from cdel.ledger.closure import compute_closure_with_stats
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.solve import solve_task

from tests.conftest import init_repo
from tests.test_stat_cert_and_adoption import _commit_base_module, _sealed_defaults, _stat_cert_spec, _inc_def


def _module(
    parent: str,
    symbol: str,
    body: dict,
    *,
    concept: str | None = None,
    declared_deps: list[str] | None = None,
) -> dict:
    payload = {
        "new_symbols": [symbol],
        "definitions": [
            {
                "name": symbol,
                "params": [{"name": "n", "type": {"tag": "int"}}],
                "ret_type": {"tag": "int"},
                "body": body,
                "termination": {"kind": "structural", "decreases_param": None},
            }
        ],
        "declared_deps": declared_deps or [],
        "specs": [],
        "concepts": [],
    }
    if concept:
        payload["concepts"] = [{"concept": concept, "symbol": symbol}]
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": parent,
        "payload": payload,
    }


def _app_sym(name: str, arg: dict) -> dict:
    return {"tag": "app", "fn": {"tag": "sym", "name": name}, "args": [arg]}


def test_invariants_non_interference_bundle(tmp_path: Path) -> None:
    cfg = init_repo(tmp_path)

    base = _module("GENESIS", "inc_a", {"tag": "int", "value": 1})
    assert commit_module(cfg, base).ok

    mid = _module(read_head(cfg), "inc_b", {"tag": "int", "value": 2})
    assert commit_module(cfg, mid).ok

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    hashes_before = {
        "inc_a": idx.get_def_hash(conn, "inc_a"),
        "inc_b": idx.get_def_hash(conn, "inc_b"),
    }

    tail = _module(read_head(cfg), "inc_c", {"tag": "int", "value": 3})
    assert commit_module(cfg, tail).ok

    hashes_after = {
        "inc_a": idx.get_def_hash(conn, "inc_a"),
        "inc_b": idx.get_def_hash(conn, "inc_b"),
    }
    assert hashes_before == hashes_after


def test_invariants_adoption_safety_and_alpha(tmp_path: Path) -> None:
    cfg = init_repo(tmp_path, budget=1)
    priv_key, pub_key = generate_keypair()
    _sealed_defaults(cfg, pub_key, key_id_from_public_key(pub_key))

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    idx.set_budget(conn, 1)
    conn.commit()
    adoption_before = read_adoption_head(cfg)
    alpha_before = idx.get_stat_cert_state(conn)

    report = solve_task(
        cfg,
        "arith.add_k.0",
        max_candidates=1,
        episodes=2,
        seed_key="inv-seed",
        private_key=priv_key,
        strategy="template_guided",
        max_context_symbols=5,
    )
    attempts = report.get("attempts") or []
    assert attempts
    assert not any(a.get("accepted") for a in attempts)
    assert all(a.get("adoption_hash") is None for a in attempts)
    assert read_adoption_head(cfg) == adoption_before
    assert idx.get_stat_cert_state(conn) == alpha_before


def test_invariants_alpha_monotonicity(tmp_path: Path) -> None:
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)

    _commit_base_module(cfg)
    spec = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "increment")
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["inc_v2"],
            "definitions": [_inc_def("inc_v2")],
            "declared_deps": ["inc"],
            "specs": [spec],
            "concepts": [{"concept": "increment", "symbol": "inc_v2"}],
        },
    }
    assert commit_module(cfg, module).ok

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    state = idx.get_stat_cert_state(conn)
    assert state is not None
    assert state[0] == 2

    bad_spec = _stat_cert_spec(
        priv_key,
        key_id,
        "inc",
        "inc_v3",
        "inc",
        "increment",
        round_idx=state[0],
        overrides={"risk": {"alpha_i": "1"}},
    )
    bad_module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["inc_v3"],
            "definitions": [_inc_def("inc_v3")],
            "declared_deps": ["inc"],
            "specs": [bad_spec],
            "concepts": [{"concept": "increment", "symbol": "inc_v3"}],
        },
    }
    result = commit_module(cfg, bad_module)
    assert not result.ok
    assert idx.get_stat_cert_state(conn) == state


def test_invariants_closure_determinism(tmp_path: Path) -> None:
    cfg = init_repo(tmp_path)

    base = _module("GENESIS", "inc_a", {"tag": "int", "value": 1})
    assert commit_module(cfg, base).ok
    body = _app_sym("inc_a", {"tag": "var", "name": "n"})
    dep = _module(read_head(cfg), "inc_b", body, declared_deps=["inc_a"])
    assert commit_module(cfg, dep).ok

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    closure_a, _ = compute_closure_with_stats(conn, ["inc_b"])
    closure_b, _ = compute_closure_with_stats(conn, ["inc_b"])
    assert closure_a == closure_b


def test_invariants_consolidate_readonly(tmp_path: Path) -> None:
    cfg = init_repo(tmp_path)
    module = _module("GENESIS", "inc", {"tag": "int", "value": 1}, concept="increment")
    assert commit_module(cfg, module).ok

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    head_before = read_head(cfg)
    adopt_before = read_adoption_head(cfg)
    modules_before = conn.execute("SELECT COUNT(1) FROM modules").fetchone()[0]
    adoptions_before = conn.execute("SELECT COUNT(1) FROM adoptions").fetchone()[0]

    out_dir = tmp_path / "consolidate"
    report = consolidate_concept(cfg, "increment", out_dir=out_dir)
    assert report.get("schema_version") == 1

    head_after = read_head(cfg)
    adopt_after = read_adoption_head(cfg)
    modules_after = conn.execute("SELECT COUNT(1) FROM modules").fetchone()[0]
    adoptions_after = conn.execute("SELECT COUNT(1) FROM adoptions").fetchone()[0]

    assert head_before == head_after
    assert adopt_before == adopt_after
    assert modules_before == modules_after
    assert adoptions_before == adoptions_after
