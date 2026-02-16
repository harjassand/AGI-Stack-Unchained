from __future__ import annotations

import json

import pytest

from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.sealed.suites import compute_suite_hash_bytes
from cdel.sealed.worker import issue_stat_cert

from tests.conftest import init_repo
from tests.test_sealed_tooluse_harness_determinism import _commit_defs, _seed_request, _tooluse_defaults


def test_sealed_tooluse_harness_hash_mismatch_rejected(tmp_path):
    cfg = init_repo(tmp_path)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)

    expected_row = {
        "episode": 0,
        "task_id": "write_hello_v1",
        "max_steps": 2,
        "allowed_tools": ["write_file"],
        "initial_fs": [],
        "tool_calls": [{"tool": "write_file", "args": ["out.txt", "hello"]}],
        "success": {"type": "file_equals", "path": "out.txt", "contents": "hello"},
    }
    expected_bytes = (json.dumps(expected_row, sort_keys=True) + "\n").encode("utf-8")
    expected_hash = compute_suite_hash_bytes(expected_bytes)

    suite_dir = tmp_path / "sealed_suites"
    suite_dir.mkdir()
    suite_path = suite_dir / f"{expected_hash}.jsonl"
    actual_row = dict(expected_row)
    actual_row["success"] = {"type": "file_equals", "path": "out.txt", "contents": "bye"}
    suite_path.write_bytes((json.dumps(actual_row, sort_keys=True) + "\n").encode("utf-8"))

    _tooluse_defaults(cfg, pub_key, key_id, expected_hash)
    _commit_defs(cfg)

    with pytest.raises(ValueError, match="suite hash mismatch"):
        issue_stat_cert(cfg, _seed_request("tool_candidate", "tool_base", "tool_oracle"), priv_key, b"seed")
