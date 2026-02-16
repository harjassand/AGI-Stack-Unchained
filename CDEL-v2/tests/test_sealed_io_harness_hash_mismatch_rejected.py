from __future__ import annotations

import json
import pytest

from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.sealed.suites import compute_suite_hash_bytes
from cdel.sealed.worker import issue_stat_cert

from tests.conftest import init_repo
from tests.test_sealed_io_harness_determinism import _commit_defs, _io_defaults, _seed_request


def test_sealed_io_harness_hash_mismatch_rejected(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)

    expected_bytes = json.dumps(
        {"episode": 0, "args": [{"tag": "int", "value": 1}], "target": {"tag": "bool", "value": False}},
        sort_keys=True,
    ).encode("utf-8")
    expected_hash = compute_suite_hash_bytes(expected_bytes)
    suite_dir = tmp_path / "sealed_suites"
    suite_dir.mkdir()
    suite_path = suite_dir / f"{expected_hash}.jsonl"
    suite_path.write_bytes(
        json.dumps(
            {"episode": 0, "args": [{"tag": "int", "value": 2}], "target": {"tag": "bool", "value": True}},
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )

    _io_defaults(cfg, pub_key, key_id, expected_hash)
    _commit_defs(cfg)

    with pytest.raises(ValueError, match="suite hash mismatch"):
        issue_stat_cert(cfg, _seed_request("is_even_good", "is_even_base", "is_even_oracle"), priv_key, b"seed")
