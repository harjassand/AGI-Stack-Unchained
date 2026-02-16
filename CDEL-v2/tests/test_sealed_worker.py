from __future__ import annotations

import json

from blake3 import blake3

from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.sealed.worker import issue_stat_cert

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


def _const_false_def(name: str) -> dict:
    return {
        "name": name,
        "params": [{"name": "n", "type": {"tag": "int"}}],
        "ret_type": {"tag": "bool"},
        "body": {"tag": "bool", "value": False},
        "termination": {"kind": "structural", "decreases_param": None},
    }


def _is_even_def(name: str) -> dict:
    return {
        "name": name,
        "params": [{"name": "n", "type": {"tag": "int"}}],
        "ret_type": {"tag": "bool"},
        "body": {
            "tag": "prim",
            "op": "eq_int",
            "args": [
                {
                    "tag": "prim",
                    "op": "mod",
                    "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": 2}],
                },
                {"tag": "int", "value": 0},
            ],
        },
        "termination": {"kind": "structural", "decreases_param": None},
    }


def _seed_request(candidate: str, baseline: str, oracle: str) -> dict:
    return {
        "kind": "stat_cert",
        "concept": "is_even",
        "metric": "accuracy",
        "null": "no_improvement",
        "baseline_symbol": baseline,
        "candidate_symbol": candidate,
        "eval": {
            "episodes": 8,
            "max_steps": 50,
            "paired_seeds": True,
            "oracle_symbol": oracle,
        },
    }


def _commit_defs(cfg) -> None:
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["is_even_base", "is_even_oracle", "is_even_good", "is_even_bad"],
            "definitions": [
                _const_false_def("is_even_base"),
                _is_even_def("is_even_oracle"),
                _is_even_def("is_even_good"),
                _const_false_def("is_even_bad"),
            ],
            "declared_deps": [],
            "specs": [],
            "concepts": [],
        },
    }
    result = commit_module(cfg, module)
    assert result.ok


def test_sealed_worker_constant_shape(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_defs(cfg)

    good = issue_stat_cert(cfg, _seed_request("is_even_good", "is_even_base", "is_even_oracle"), priv_key, b"seed")
    bad = issue_stat_cert(cfg, _seed_request("is_even_bad", "is_even_base", "is_even_oracle"), priv_key, b"seed")

    assert set(good.keys()) == set(bad.keys())
    assert set(good["certificate"].keys()) == set(bad["certificate"].keys())
    assert set(good["eval"].keys()) == set(bad["eval"].keys())
    assert good["certificate"].get("transcript_hash")
    assert bad["certificate"].get("transcript_hash")


def test_sealed_worker_writes_artifact(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_defs(cfg)

    artifact_dir = tmp_path / "artifacts"
    result = issue_stat_cert(
        cfg,
        _seed_request("is_even_good", "is_even_base", "is_even_oracle"),
        priv_key,
        b"seed",
        artifact_dir=artifact_dir,
    )

    transcript_hash = result["certificate"]["transcript_hash"]
    path = artifact_dir / f"{transcript_hash}.jsonl"
    assert path.exists()

    diffs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        diffs.append(int(row["diff"]))
    digest = blake3("\n".join(str(d) for d in diffs).encode("utf-8")).hexdigest()
    assert digest == transcript_hash
