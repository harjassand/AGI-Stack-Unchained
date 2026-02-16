from __future__ import annotations

import json

from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.sealed.suites import compute_suite_hash_bytes
from cdel.sealed.worker import issue_stat_cert

from tests.conftest import init_repo


def _tooluse_defaults(cfg, pub_key: str, key_id: str, suite_hash: str) -> None:
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
        "eval_harness_id": "tooluse-harness-v1",
        "eval_harness_hash": "tooluse-harness-v1-hash",
        "eval_suite_hash": suite_hash,
    }


def _action_def(name: str, action: int) -> dict:
    return {
        "name": name,
        "params": [
            {"name": "step", "type": {"tag": "int"}},
            {"name": "last_ok", "type": {"tag": "int"}},
            {"name": "last_len", "type": {"tag": "int"}},
        ],
        "ret_type": {"tag": "int"},
        "body": {"tag": "int", "value": action},
        "termination": {"kind": "structural", "decreases_param": None},
    }


def _commit_defs(cfg) -> None:
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["tool_base", "tool_candidate", "tool_oracle"],
            "definitions": [
                _action_def("tool_base", -1),
                _action_def("tool_candidate", 0),
                _action_def("tool_oracle", 0),
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
        "concept": "tooluse",
        "metric": "task_success",
        "null": "no_improvement",
        "baseline_symbol": baseline,
        "candidate_symbol": candidate,
        "eval": {
            "episodes": 1,
            "max_steps": 10,
            "paired_seeds": True,
            "oracle_symbol": oracle,
        },
    }


def _write_suite(cfg) -> str:
    row = {
        "episode": 0,
        "task_id": "write_hello_v1",
        "max_steps": 2,
        "allowed_tools": ["write_file"],
        "initial_fs": [],
        "tool_calls": [{"tool": "write_file", "args": ["out.txt", "hello"]}],
        "success": {"type": "file_equals", "path": "out.txt", "contents": "hello"},
    }
    content = json.dumps(row, sort_keys=True) + "\n"
    suite_hash = compute_suite_hash_bytes(content.encode("utf-8"))
    suite_dir = cfg.root / "sealed_suites"
    suite_dir.mkdir(parents=True, exist_ok=True)
    (suite_dir / f"{suite_hash}.jsonl").write_text(content, encoding="utf-8")
    return suite_hash


def test_sealed_tooluse_harness_determinism(tmp_path):
    cfg = init_repo(tmp_path)
    suite_hash = _write_suite(cfg)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _tooluse_defaults(cfg, pub_key, key_id, suite_hash)
    _commit_defs(cfg)

    first = issue_stat_cert(cfg, _seed_request("tool_candidate", "tool_base", "tool_oracle"), priv_key, b"seed")
    second = issue_stat_cert(cfg, _seed_request("tool_candidate", "tool_base", "tool_oracle"), priv_key, b"seed")

    first_cert = first["certificate"]
    second_cert = second["certificate"]
    assert first_cert["transcript_hash"] == second_cert["transcript_hash"]
    assert first_cert["evalue"]["mantissa"] == second_cert["evalue"]["mantissa"]
    assert first_cert["evalue"]["exponent10"] == second_cert["evalue"]["exponent10"]
    assert first_cert["signature"] == second_cert["signature"]
