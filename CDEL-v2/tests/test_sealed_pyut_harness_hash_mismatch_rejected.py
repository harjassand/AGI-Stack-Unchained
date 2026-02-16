from __future__ import annotations

import json
import pytest

from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.sealed.suites import compute_suite_hash_bytes
from cdel.sealed.worker import issue_stat_cert

from tests.conftest import init_repo
from tests.test_sealed_pyut_harness_determinism import _commit_defs, _pyut_defaults, _seed_request


def test_sealed_pyut_harness_hash_mismatch_rejected(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)

    expected_bytes = json.dumps(
        {
            "episode": 0,
            "task_id": "abs_int_v1",
            "fn_name": "abs_int",
            "signature": "def abs_int(x: int) -> int:",
            "tests": [{"args": [0], "expected": 0}],
        },
        sort_keys=True,
    ).encode("utf-8")
    expected_hash = compute_suite_hash_bytes(expected_bytes)
    suite_dir = tmp_path / "sealed_suites"
    suite_dir.mkdir()
    suite_path = suite_dir / f"{expected_hash}.jsonl"
    suite_path.write_bytes(
        json.dumps(
            {
                "episode": 0,
                "task_id": "abs_int_v1",
                "fn_name": "abs_int",
                "signature": "def abs_int(x: int) -> int:",
                "tests": [{"args": [1], "expected": 1}],
            },
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )

    _pyut_defaults(cfg, pub_key, key_id, expected_hash)
    baseline_src = "def abs_int(x: int) -> int:\n    return 0\n"
    candidate_src = "def abs_int(x: int) -> int:\n    return x if x >= 0 else -x\n"
    _commit_defs(cfg, baseline_src, candidate_src, candidate_src)

    with pytest.raises(ValueError, match="suite hash mismatch"):
        issue_stat_cert(cfg, _seed_request("pyut_candidate", "pyut_base", "pyut_oracle"), priv_key, b"seed")
