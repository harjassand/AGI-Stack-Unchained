from __future__ import annotations

import shutil

from blake3 import blake3

import pytest

from cdel.adoption.storage import read_head as read_adoption_head
from cdel.adoption.verifier import commit_adoption, verify_adoption
from cdel.ledger import index as idx
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module, verify_module
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key, sign_bytes
from cdel.sealed.evalue import alpha_for_round, encode_evalue, format_decimal, hoeffding_mixture_evalue, parse_alpha_schedule, parse_decimal
from cdel.sealed.protocol import stat_cert_signing_bytes

from tests.conftest import init_repo


def _inc_def(name: str) -> dict:
    return {
        "name": name,
        "params": [{"name": "n", "type": {"tag": "int"}}],
        "ret_type": {"tag": "int"},
        "body": {
            "tag": "prim",
            "op": "add",
            "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": 1}],
        },
        "termination": {"kind": "structural", "decreases_param": None},
    }


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


def _stat_cert_spec(
    priv_key: str,
    key_id: str,
    baseline: str,
    candidate: str,
    oracle: str,
    concept: str,
    round_idx: int = 1,
    overrides: dict | None = None,
) -> dict:
    schedule = {
        "name": "p_series",
        "exponent": 2,
        "coefficient": "0.60792710185402662866",
    }
    alpha_total = parse_decimal("1e-4")
    alpha_i = format_decimal(alpha_for_round(alpha_total, round_idx, parse_alpha_schedule(schedule)))
    n = 4
    baseline_successes = 2
    candidate_successes = 3
    diff_sum = candidate_successes - baseline_successes
    evalue = encode_evalue(hoeffding_mixture_evalue(diff_sum, n)).to_dict()
    spec = {
        "kind": "stat_cert",
        "concept": concept,
        "metric": "accuracy",
        "null": "no_improvement",
        "baseline_symbol": baseline,
        "candidate_symbol": candidate,
        "eval": {
            "episodes": n,
            "max_steps": 50,
            "paired_seeds": True,
            "oracle_symbol": oracle,
            "eval_harness_id": "toy-harness-v1",
            "eval_harness_hash": "harness-hash",
            "eval_suite_hash": "suite-hash",
        },
        "risk": {
            "alpha_i": alpha_i,
            "evalue_threshold": "1e-6",
            "alpha_schedule": schedule,
        },
        "certificate": {
            "evalue_schema_version": 2,
            "n": n,
            "baseline_successes": baseline_successes,
            "candidate_successes": candidate_successes,
            "diff_sum": diff_sum,
            "diff_min": -1,
            "diff_max": 1,
            "evalue": evalue,
            "transcript_hash": blake3(b"test").hexdigest(),
            "signature": "",
            "signature_scheme": "ed25519",
            "key_id": key_id,
        },
    }
    if overrides:
        _deep_update(spec, overrides)
    signing_bytes = stat_cert_signing_bytes(spec)
    spec["certificate"]["signature"] = sign_bytes(priv_key, signing_bytes)
    return spec


def _deep_update(target: dict, updates: dict) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _reorder(value):
    if isinstance(value, dict):
        items = list(value.items())
        items.reverse()
        return {key: _reorder(item) for key, item in items}
    if isinstance(value, list):
        return [_reorder(item) for item in value]
    return value


def _commit_base_module(cfg) -> None:
    base_module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": "GENESIS",
        "payload": {
            "new_symbols": ["inc"],
            "definitions": [_inc_def("inc")],
            "declared_deps": [],
            "specs": [],
            "concepts": [],
        },
    }
    result = commit_module(cfg, base_module)
    assert result.ok


def _commit_candidate_module(cfg, spec: dict, concept: str = "increment") -> None:
    candidate_module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["inc_v2"],
            "definitions": [_inc_def("inc_v2")],
            "declared_deps": ["inc"],
            "specs": [spec],
            "concepts": [{"concept": concept, "symbol": "inc_v2"}],
        },
    }
    result = commit_module(cfg, candidate_module)
    assert result.ok


def test_stat_cert_and_adoption_flow(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)

    _commit_base_module(cfg)

    spec = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "increment")
    _commit_candidate_module(cfg, spec)

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    symbols = idx.list_symbols_for_concept(conn, "increment", limit=10)
    assert "inc_v2" in symbols

    adoption = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": "increment",
            "chosen_symbol": "inc_v2",
            "baseline_symbol": None,
            "certificate": spec,
            "constraints": {},
        },
    }
    adoption_result = commit_adoption(cfg, adoption)
    assert adoption_result.ok

    latest = idx.latest_adoption_for_concept(conn, "increment")
    assert latest is not None
    assert latest["chosen_symbol"] == "inc_v2"


def test_stat_cert_accepts_reordered_payload(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)

    spec = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "increment")
    reordered = _reorder(spec)
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["inc_v2"],
            "definitions": [_inc_def("inc_v2")],
            "declared_deps": ["inc"],
            "specs": [reordered],
            "concepts": [{"concept": "increment", "symbol": "inc_v2"}],
        },
    }
    result = verify_module(cfg, module)
    assert result.ok


def test_stat_cert_rejects_tampered_field(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "increment")
    spec["certificate"]["transcript_hash"] = "tampered"
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
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code.value == "SPEC_FAIL"


def test_stat_cert_rejects_bad_signature(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "increment")
    spec["certificate"]["signature"] = "bogus"
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
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code.value == "SPEC_FAIL"


def test_stat_cert_rejects_unknown_key_id(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(priv_key, "unknown", "inc", "inc_v2", "inc", "increment")
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
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code.value == "SPEC_FAIL"


def test_stat_cert_rejects_wrong_alpha_i(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(
        priv_key,
        key_id,
        "inc",
        "inc_v2",
        "inc",
        "increment",
        overrides={"risk": {"alpha_i": "9e-9"}},
    )
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
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code.value == "SPEC_FAIL"


def test_stat_cert_rejects_evalue_mismatch(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(
        priv_key,
        key_id,
        "inc",
        "inc_v2",
        "inc",
        "increment",
        overrides={"certificate": {"evalue": encode_evalue(parse_decimal("9.99")).to_dict()}},
    )
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
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code.value == "SPEC_FAIL"


def test_stat_cert_rejects_legacy_evalue_format(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(
        priv_key,
        key_id,
        "inc",
        "inc_v2",
        "inc",
        "increment",
        overrides={"certificate": {"evalue": "1.23"}},
    )
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
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code.value == "SPEC_FAIL"
    assert "legacy evalue format detected" in (result.rejection.details or "")


def test_stat_cert_rejects_missing_evalue_schema_version(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(
        priv_key,
        key_id,
        "inc",
        "inc_v2",
        "inc",
        "increment",
    )
    spec["certificate"].pop("evalue_schema_version", None)
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
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code.value == "SPEC_FAIL"


def test_stat_cert_rejects_unknown_evalue_schema_version(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(
        priv_key,
        key_id,
        "inc",
        "inc_v2",
        "inc",
        "increment",
        overrides={"certificate": {"evalue_schema_version": 1}},
    )
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
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code.value == "SPEC_FAIL"


def test_stat_cert_rejects_evalue_above_1_but_below_1_over_alpha(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)

    n = 4
    baseline_successes = 0
    candidate_successes = 4
    diff_sum = candidate_successes - baseline_successes
    evalue = encode_evalue(hoeffding_mixture_evalue(diff_sum, n)).to_dict()

    spec = _stat_cert_spec(
        priv_key,
        key_id,
        "inc",
        "inc_v2",
        "inc",
        "increment",
        overrides={
            "risk": {"evalue_threshold": "1"},
            "certificate": {
                "baseline_successes": baseline_successes,
                "candidate_successes": candidate_successes,
                "diff_sum": diff_sum,
                "evalue": evalue,
            },
        },
    )
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
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code.value == "SPEC_FAIL"


def test_stat_cert_rejects_harness_hash_mismatch(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(
        priv_key,
        key_id,
        "inc",
        "inc_v2",
        "inc",
        "increment",
        overrides={"eval": {"eval_harness_hash": "wrong-hash"}},
    )
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
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code.value == "SPEC_FAIL"


def test_stat_cert_rejects_suite_hash_mismatch(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(
        priv_key,
        key_id,
        "inc",
        "inc_v2",
        "inc",
        "increment",
        overrides={"eval": {"eval_suite_hash": "wrong-suite"}},
    )
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
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code.value == "SPEC_FAIL"


def test_stat_cert_rejects_missing_crypto(tmp_path, monkeypatch):
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
    from cdel.sealed import crypto

    monkeypatch.setattr(crypto, "_CRYPTO_AVAILABLE", False)
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code.value == "SPEC_FAIL"


def test_alpha_state_not_double_spent(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "increment")
    _commit_candidate_module(cfg, spec)

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    state = idx.get_stat_cert_state(conn)
    assert state is not None
    round_before = state[0]

    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": "GENESIS",
        "payload": {
            "new_symbols": ["inc_v2"],
            "definitions": [_inc_def("inc_v2")],
            "declared_deps": ["inc"],
            "specs": [spec],
            "concepts": [{"concept": "increment", "symbol": "inc_v2"}],
        },
    }
    result = verify_module(cfg, module)
    assert not result.ok
    state_after = idx.get_stat_cert_state(conn)
    assert state_after[0] == round_before


def test_commit_does_not_double_spend_alpha_on_replay(tmp_path):
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
    first = commit_module(cfg, module)
    assert first.ok

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    state_before = idx.get_stat_cert_state(conn)

    replay = commit_module(cfg, module)
    assert not replay.ok
    state_after = idx.get_stat_cert_state(conn)
    assert state_after == state_before


def test_commit_rolls_back_alpha_on_failure(tmp_path, monkeypatch):
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

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(idx, "set_stat_cert_state", boom)
    result = commit_module(cfg, module)
    assert result.ok

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    assert idx.get_stat_cert_state(conn) is None
    assert not idx.symbol_exists(conn, "inc_v2")


def test_commit_retry_after_db_failure_does_not_spend_alpha(tmp_path, monkeypatch):
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

    original_insert = idx.insert_module

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(idx, "insert_module", boom)
    first = commit_module(cfg, module)
    assert first.ok

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    assert idx.get_stat_cert_state(conn) is None

    monkeypatch.setattr(idx, "insert_module", original_insert)
    second = commit_module(cfg, module)
    assert not second.ok
    assert idx.get_stat_cert_state(conn) is None


def test_verify_does_not_advance_alpha(tmp_path):
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
    result = verify_module(cfg, module)
    assert result.ok
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    assert idx.get_stat_cert_state(conn) is None


def test_adopt_first_time_requires_genesis_policy(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "increment")
    _commit_candidate_module(cfg, spec)

    adoption = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": "increment",
            "chosen_symbol": "inc_v2",
            "baseline_symbol": "inc",
            "certificate": spec,
            "constraints": {},
        },
    }
    adoption_result = verify_adoption(cfg, adoption)
    assert not adoption_result.ok
    assert adoption_result.rejection.code == "BASELINE_MISMATCH"


def test_adopt_wrong_baseline_rejected(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "increment")
    _commit_candidate_module(cfg, spec)

    adoption = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": "increment",
            "chosen_symbol": "inc_v2",
            "baseline_symbol": None,
            "certificate": spec,
            "constraints": {},
        },
    }
    first = commit_adoption(cfg, adoption)
    assert first.ok

    bad_adoption = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": "increment",
            "chosen_symbol": "inc_v2",
            "baseline_symbol": "inc",
            "certificate": spec,
            "constraints": {},
        },
    }
    second = verify_adoption(cfg, bad_adoption)
    assert not second.ok
    assert second.rejection.code == "BASELINE_MISMATCH"


def test_adopt_cert_baseline_mismatch(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "increment")
    _commit_candidate_module(cfg, spec)

    first = commit_adoption(
        cfg,
        {
            "schema_version": 1,
            "parent": read_adoption_head(cfg),
            "payload": {
                "concept": "increment",
                "chosen_symbol": "inc_v2",
                "baseline_symbol": None,
                "certificate": spec,
                "constraints": {},
            },
        },
    )
    assert first.ok

    bad_cert = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "increment")
    adoption = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": "increment",
            "chosen_symbol": "inc_v2",
            "baseline_symbol": "inc_v2",
            "certificate": bad_cert,
            "constraints": {},
        },
    }
    adoption_result = verify_adoption(cfg, adoption)
    assert not adoption_result.ok
    assert adoption_result.rejection.code == "SCHEMA_INVALID"


def test_adopt_missing_concept_tag(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)

    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["inc_v2"],
            "definitions": [_inc_def("inc_v2")],
            "declared_deps": [],
            "specs": [],
            "concepts": [],
        },
    }
    result = commit_module(cfg, module)
    assert result.ok

    spec = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "increment")
    adoption = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": "increment",
            "chosen_symbol": "inc_v2",
            "baseline_symbol": None,
            "certificate": spec,
            "constraints": {},
        },
    }
    adoption_result = verify_adoption(cfg, adoption)
    assert not adoption_result.ok
    assert adoption_result.rejection.code == "CONCEPT_UNKNOWN"


def test_adopt_rejects_missing_symbol_in_cdel(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    spec = _stat_cert_spec(priv_key, key_id, "inc", "missing", "inc", "increment")
    adoption = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": "increment",
            "chosen_symbol": "missing",
            "baseline_symbol": None,
            "certificate": spec,
            "constraints": {},
        },
    }
    adoption_result = verify_adoption(cfg, adoption)
    assert not adoption_result.ok
    assert adoption_result.rejection.code == "SYMBOL_UNKNOWN"


def test_adopt_mismatched_cert(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "increment")
    _commit_candidate_module(cfg, spec)

    bad_cert = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "wrong")
    adoption = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": "increment",
            "chosen_symbol": "inc_v2",
            "baseline_symbol": None,
            "certificate": bad_cert,
            "constraints": {},
        },
    }
    adoption_result = verify_adoption(cfg, adoption)
    assert not adoption_result.ok
    assert adoption_result.rejection.code == "SCHEMA_INVALID"


def test_adopt_rejects_cert_symbol_mismatch(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _sealed_defaults(cfg, pub_key, key_id)
    _commit_base_module(cfg)
    spec = _stat_cert_spec(priv_key, key_id, "inc", "inc_v2", "inc", "increment")
    _commit_candidate_module(cfg, spec)

    bad_cert = _stat_cert_spec(priv_key, key_id, "inc", "inc_v3", "inc", "increment")
    adoption = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": "increment",
            "chosen_symbol": "inc_v2",
            "baseline_symbol": None,
            "certificate": bad_cert,
            "constraints": {},
        },
    }
    adoption_result = verify_adoption(cfg, adoption)
    assert not adoption_result.ok
    assert adoption_result.rejection.code == "SCHEMA_INVALID"


def test_adopt_requires_init(tmp_path):
    cfg = init_repo(tmp_path)
    shutil.rmtree(cfg.adoption_dir)
    adoption = {
        "schema_version": 1,
        "parent": "GENESIS",
        "payload": {
            "concept": "increment",
            "chosen_symbol": "inc",
            "baseline_symbol": None,
            "certificate": {"kind": "stat_cert"},
            "constraints": {},
        },
    }
    result = verify_adoption(cfg, adoption)
    assert not result.ok
    assert result.rejection.code == "ADOPTION_NOT_INITIALIZED"
