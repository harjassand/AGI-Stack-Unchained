from __future__ import annotations

import json

from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.sealed.suites import compute_suite_hash_bytes
from cdel.sealed.worker import issue_stat_cert

from tests.conftest import init_repo
from tests.test_sealed_worker import _is_even_def


def _io_defaults(cfg, pub_key: str, key_id: str, suite_hash: str) -> None:
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
        "eval_harness_id": "io-harness-v1",
        "eval_harness_hash": "io-harness-v1-hash",
        "eval_suite_hash": suite_hash,
    }


def _error_def(name: str) -> dict:
    return {
        "name": name,
        "params": [{"name": "n", "type": {"tag": "int"}}],
        "ret_type": {"tag": "bool"},
        "body": {
            "tag": "prim",
            "op": "mod",
            "args": [{"tag": "int", "value": 1}, {"tag": "int", "value": 0}],
        },
        "termination": {"kind": "structural", "decreases_param": None},
    }


def _commit_defs(cfg) -> None:
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["is_even_base", "is_even_error", "is_even_oracle"],
            "definitions": [
                _is_even_def("is_even_base"),
                _error_def("is_even_error"),
                _is_even_def("is_even_oracle"),
            ],
            "declared_deps": [],
            "specs": [],
            "concepts": [],
        },
    }
    result = commit_module(cfg, module)
    assert result.ok


def _seed_request(candidate: str, baseline: str, oracle: str) -> dict:
    return {
        "kind": "stat_cert",
        "concept": "is_even",
        "metric": "accuracy",
        "null": "no_improvement",
        "baseline_symbol": baseline,
        "candidate_symbol": candidate,
        "eval": {
            "episodes": 2,
            "max_steps": 50,
            "paired_seeds": True,
            "oracle_symbol": oracle,
        },
    }


def _write_suite(cfg) -> str:
    rows = [
        {"episode": 0, "args": [{"tag": "int", "value": 2}], "target": {"tag": "bool", "value": True}},
        {"episode": 1, "args": [{"tag": "int", "value": 3}], "target": {"tag": "bool", "value": False}},
    ]
    content = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
    suite_hash = compute_suite_hash_bytes(content.encode("utf-8"))
    suite_dir = cfg.root / "sealed_suites"
    suite_dir.mkdir(parents=True, exist_ok=True)
    (suite_dir / f"{suite_hash}.jsonl").write_text(content, encoding="utf-8")
    return suite_hash


def test_io_harness_error_is_failure(tmp_path):
    cfg = init_repo(tmp_path)
    suite_hash = _write_suite(cfg)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _io_defaults(cfg, pub_key, key_id, suite_hash)
    _commit_defs(cfg)

    result = issue_stat_cert(cfg, _seed_request("is_even_error", "is_even_base", "is_even_oracle"), priv_key, b"seed")
    cert = result["certificate"]
    assert cert["baseline_successes"] > cert["candidate_successes"]
