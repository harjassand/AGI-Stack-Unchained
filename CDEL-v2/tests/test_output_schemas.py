from __future__ import annotations

from pathlib import Path

from cdel.bench.solve_suite import SolveSuiteConfig, run_solve_suite
from cdel.bench.solve_suite_ablations import AblationConfig, run_solve_suite_ablations
from cdel.consolidate import consolidate_concept
from cdel.experiments.solve_stress import SolveStressConfig, run_solve_stress
from cdel.ledger import index as idx
from cdel.ledger.verifier import commit_module
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key

from tests.conftest import init_repo


def _sealed_defaults(cfg, pub_key: str, key_id: str) -> None:
    cfg.data["sealed"] = {
        "public_key": pub_key,
        "key_id": key_id,
        "public_keys": [],
        "prev_public_keys": [],
        "alpha_total": "1e-4",
        "alpha_schedule": {
            "name": "p_series",
            "exponent": 2,
            "coefficient": "0.60792710185402662866",
        },
        "eval_harness_id": "toy-harness-v1",
        "eval_harness_hash": "harness-hash",
        "eval_suite_hash": "suite-hash",
    }


def test_schema_solve_suite(tmp_path: Path) -> None:
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    _sealed_defaults(cfg, pub_key, key_id_from_public_key(pub_key))

    out_dir = tmp_path / "suite"
    suite_cfg = SolveSuiteConfig(
        suite="trackA",
        limit=1,
        max_candidates=1,
        episodes=2,
        seed_key="schema-seed",
        budget_per_task=100000,
        max_context_symbols=10,
        strategy="template_guided",
    )
    report = run_solve_suite(out_dir, cfg, suite_cfg, private_key=priv_key)
    assert report.get("schema_version") == 1
    payload = (out_dir / "suite_scoreboard.json").read_text(encoding="utf-8")
    assert "\"schema_version\": 1" in payload


def test_schema_solve_suite_ablations(tmp_path: Path) -> None:
    out_dir = tmp_path / "ablations"
    cfg = AblationConfig(
        suite="trackA",
        limit=1,
        strategies=["baseline_enum"],
        max_candidates=1,
        episodes=2,
        seed_key="schema-seed",
        budget_per_task=100000,
        max_context_symbols=10,
        deterministic=True,
    )
    report = run_solve_suite_ablations(out_dir, cfg)
    assert report.get("schema_version") == 1
    payload = (out_dir / "ablations_results.json").read_text(encoding="utf-8")
    assert "\"schema_version\": 1" in payload


def test_schema_solve_stress(tmp_path: Path) -> None:
    out_dir = tmp_path / "stress"
    cfg = SolveStressConfig(
        tasks=1,
        max_candidates=1,
        episodes=2,
        seed_key="schema-seed",
        budget=100000,
        strategy="template_guided",
        reuse_every=0,
    )
    report = run_solve_stress(out_dir, cfg)
    assert report.get("schema_version") == 1
    payload = (out_dir / "stress_results.json").read_text(encoding="utf-8")
    assert "\"schema_version\": 1" in payload


def test_schema_consolidation_report(tmp_path: Path) -> None:
    cfg = init_repo(tmp_path)
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": "GENESIS",
        "payload": {
            "new_symbols": ["inc"],
            "definitions": [
                {
                    "name": "inc",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "int", "value": 1},
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [],
            "specs": [],
            "concepts": [{"concept": "increment", "symbol": "inc"}],
        },
    }
    assert commit_module(cfg, module).ok
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)

    out_dir = tmp_path / "consolidate"
    report = consolidate_concept(cfg, "increment", out_dir=out_dir)
    assert report.get("schema_version") == 1
    payload = (out_dir / "consolidation_report.json").read_text(encoding="utf-8")
    assert "\"schema_version\": 1" in payload
