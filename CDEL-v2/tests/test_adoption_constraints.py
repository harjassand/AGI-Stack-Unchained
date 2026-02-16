from __future__ import annotations

from blake3 import blake3

import pytest

from cdel.adoption.storage import read_head as read_adoption_head
from cdel.adoption.verifier import verify_adoption
from cdel.constraints import constraint_spec_hash
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module
from cdel.sealed.crypto import generate_keypair, key_id_from_public_key, sign_bytes
from cdel.sealed.evalue import (
    alpha_for_round,
    encode_evalue,
    format_decimal,
    hoeffding_mixture_evalue,
    parse_alpha_schedule,
    parse_decimal,
)
from cdel.sealed.protocol import stat_cert_signing_bytes

from tests.conftest import init_repo


def _sealed_block(pub_key: str, key_id: str, suite_hash: str, harness_id: str, harness_hash: str) -> dict:
    return {
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
        "eval_harness_id": harness_id,
        "eval_harness_hash": harness_hash,
        "eval_suite_hash": suite_hash,
    }


def _stat_cert_spec(
    priv_key: str,
    key_id: str,
    concept: str,
    baseline: str,
    candidate: str,
    oracle: str,
    harness_id: str,
    harness_hash: str,
    suite_hash: str,
) -> dict:
    schedule = {
        "name": "p_series",
        "exponent": 2,
        "coefficient": "0.60792710185402662866",
    }
    alpha_total = parse_decimal("1e-4")
    alpha_i = format_decimal(alpha_for_round(alpha_total, 1, parse_alpha_schedule(schedule)))
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
            "eval_harness_id": harness_id,
            "eval_harness_hash": harness_hash,
            "eval_suite_hash": suite_hash,
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
    signing_bytes = stat_cert_signing_bytes(spec)
    spec["certificate"]["signature"] = sign_bytes(priv_key, signing_bytes)
    return spec


def _commit_module(cfg, parent: str, symbol: str, concept: str | None) -> None:
    module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": parent,
        "payload": {
            "new_symbols": [symbol],
            "definitions": [
                {
                    "name": symbol,
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {
                        "tag": "prim",
                        "op": "add",
                        "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": 1}],
                    },
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [],
            "specs": [],
            "concepts": [] if concept is None else [{"concept": concept, "symbol": symbol}],
        },
    }
    result = commit_module(cfg, module)
    assert result.ok


def _constraint_spec(domain: str) -> dict:
    return {
        "schema_version": 1,
        "kind": "constraint_spec",
        "domain": domain,
        "constraints": {
            "banned_tools": ["network"],
            "max_steps": 10,
            "max_file_writes": 1,
            "allow_path_escape": False,
            "allow_network": False,
            "allow_subprocess": False,
        },
    }


def test_adoption_requires_constraints_for_high_impact(tmp_path) -> None:
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    cfg.data["sealed"] = _sealed_block(pub_key, key_id, "suite-hash", "tooluse-harness-v1", "tooluse-harness-v1-hash")
    cfg.data["sealed_safety"] = _sealed_block(
        pub_key, key_id, "safety-suite-hash", "tooluse-harness-v1", "tooluse-harness-v1-hash"
    )
    spec = _constraint_spec("tooluse")
    spec_hash = constraint_spec_hash(spec)
    cfg.data["constraints"] = {"required_concepts": ["tooluse."], "spec_hash": spec_hash}

    _commit_module(cfg, "GENESIS", "tool_base", None)
    _commit_module(cfg, read_head(cfg), "tool_candidate", "tooluse.test")

    cert = _stat_cert_spec(
        priv_key,
        key_id,
        "tooluse.test",
        "tool_base",
        "tool_candidate",
        "tool_base",
        "tooluse-harness-v1",
        "tooluse-harness-v1-hash",
        "suite-hash",
    )
    record = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": "tooluse.test",
            "chosen_symbol": "tool_candidate",
            "baseline_symbol": None,
            "certificate": cert,
            "constraints": {},
        },
    }
    result = verify_adoption(cfg, record)
    assert not result.ok
    assert result.rejection is not None
    assert result.rejection.code == "SCHEMA_INVALID"
    assert "constraints required" in (result.rejection.details or "")


def test_adoption_accepts_constraints_with_safety_cert(tmp_path) -> None:
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    cfg.data["sealed"] = _sealed_block(pub_key, key_id, "suite-hash", "tooluse-harness-v1", "tooluse-harness-v1-hash")
    cfg.data["sealed_safety"] = _sealed_block(
        pub_key, key_id, "safety-suite-hash", "tooluse-harness-v1", "tooluse-harness-v1-hash"
    )
    spec = _constraint_spec("tooluse")
    spec_hash = constraint_spec_hash(spec)
    cfg.data["constraints"] = {"required_concepts": ["tooluse."], "spec_hash": spec_hash}

    _commit_module(cfg, "GENESIS", "tool_base", None)
    _commit_module(cfg, read_head(cfg), "tool_candidate", "tooluse.test")

    cert = _stat_cert_spec(
        priv_key,
        key_id,
        "tooluse.test",
        "tool_base",
        "tool_candidate",
        "tool_base",
        "tooluse-harness-v1",
        "tooluse-harness-v1-hash",
        "suite-hash",
    )
    safety_cert = _stat_cert_spec(
        priv_key,
        key_id,
        "tooluse.test",
        "tool_base",
        "tool_candidate",
        "tool_base",
        "tooluse-harness-v1",
        "tooluse-harness-v1-hash",
        "safety-suite-hash",
    )
    record = {
        "schema_version": 1,
        "parent": read_adoption_head(cfg),
        "payload": {
            "concept": "tooluse.test",
            "chosen_symbol": "tool_candidate",
            "baseline_symbol": None,
            "certificate": cert,
            "constraints": {
                "spec": spec,
                "spec_hash": spec_hash,
                "safety_certificate": safety_cert,
            },
        },
    }
    result = verify_adoption(cfg, record)
    assert result.ok
