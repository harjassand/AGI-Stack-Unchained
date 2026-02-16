from __future__ import annotations

import json

from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.sealed.suites import compute_suite_hash_bytes
from cdel.sealed.worker import issue_stat_cert

from tests.conftest import init_repo


def _pyut_defaults(cfg, pub_key: str, key_id: str, suite_hash: str) -> None:
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
        "eval_harness_id": "pyut-harness-v1",
        "eval_harness_hash": "pyut-harness-v1-hash-2",
        "eval_suite_hash": suite_hash,
    }


def _list_literal(values: list[int]) -> dict:
    term: dict = {"tag": "nil"}
    for value in reversed(values):
        term = {
            "tag": "cons",
            "head": {"tag": "int", "value": value},
            "tail": term,
        }
    return term


def _code_def(name: str, source: str) -> dict:
    data = source.encode("ascii")
    return {
        "name": name,
        "params": [],
        "ret_type": {"tag": "list", "of": {"tag": "int"}},
        "body": _list_literal(list(data)),
        "termination": {"kind": "structural", "decreases_param": None},
    }


def _commit_defs(cfg, baseline_src: str, candidate_src: str, oracle_src: str) -> None:
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["pyut_base", "pyut_candidate", "pyut_oracle"],
            "definitions": [
                _code_def("pyut_base", baseline_src),
                _code_def("pyut_candidate", candidate_src),
                _code_def("pyut_oracle", oracle_src),
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
        "concept": "pyut.abs_int",
        "metric": "accuracy",
        "null": "no_improvement",
        "baseline_symbol": baseline,
        "candidate_symbol": candidate,
        "eval": {
            "episodes": 1,
            "max_steps": 2000,
            "paired_seeds": True,
            "oracle_symbol": oracle,
        },
    }


def _write_suite(cfg) -> str:
    rows = [
        {
            "episode": 0,
            "task_id": "abs_int_v1",
            "fn_name": "abs_int",
            "signature": "def abs_int(x: int) -> int:",
            "tests": [
                {"args": [0], "expected": 0},
                {"args": [-3], "expected": 3},
                {"args": [5], "expected": 5},
            ],
        }
    ]
    content = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
    suite_hash = compute_suite_hash_bytes(content.encode("utf-8"))
    suite_dir = cfg.root / "sealed_suites"
    suite_dir.mkdir(parents=True, exist_ok=True)
    (suite_dir / f"{suite_hash}.jsonl").write_text(content, encoding="utf-8")
    return suite_hash


def test_sealed_pyut_harness_determinism(tmp_path):
    cfg = init_repo(tmp_path)
    suite_hash = _write_suite(cfg)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _pyut_defaults(cfg, pub_key, key_id, suite_hash)

    baseline_src = "def abs_int(x: int) -> int:\n    return 0\n"
    candidate_src = "def abs_int(x: int) -> int:\n    return x if x >= 0 else -x\n"
    _commit_defs(cfg, baseline_src, candidate_src, candidate_src)

    first = issue_stat_cert(cfg, _seed_request("pyut_candidate", "pyut_base", "pyut_oracle"), priv_key, b"seed")
    second = issue_stat_cert(cfg, _seed_request("pyut_candidate", "pyut_base", "pyut_oracle"), priv_key, b"seed")

    first_cert = first["certificate"]
    second_cert = second["certificate"]
    assert first_cert["transcript_hash"] == second_cert["transcript_hash"]
    assert first_cert["evalue"]["mantissa"] == second_cert["evalue"]["mantissa"]
    assert first_cert["evalue"]["exponent10"] == second_cert["evalue"]["exponent10"]
    assert first_cert["signature"] == second_cert["signature"]
