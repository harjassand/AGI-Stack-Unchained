from __future__ import annotations

import json

from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.sealed.suites import compute_suite_hash_bytes
from cdel.sealed.worker import issue_stat_cert

from tests.conftest import init_repo
from tests.test_sealed_tooluse_harness_determinism import _commit_defs, _seed_request, _tooluse_defaults


def _write_suite(cfg) -> str:
    row = {
        "episode": 0,
        "task_id": "timeout_v1",
        "max_steps": 2,
        "allowed_tools": ["write_file"],
        "initial_fs": [{"path": "ready.txt", "contents": "ok"}],
        "tool_calls": [{"tool": "write_file", "args": ["out.txt", "hi"]}],
        "success": {"type": "file_exists", "path": "ready.txt"},
    }
    content = json.dumps(row, sort_keys=True) + "\n"
    suite_hash = compute_suite_hash_bytes(content.encode("utf-8"))
    suite_dir = cfg.root / "sealed_suites"
    suite_dir.mkdir(parents=True, exist_ok=True)
    (suite_dir / f"{suite_hash}.jsonl").write_text(content, encoding="utf-8")
    return suite_hash


def test_tooluse_harness_timeout_is_failure(tmp_path):
    cfg = init_repo(tmp_path)
    suite_hash = _write_suite(cfg)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _tooluse_defaults(cfg, pub_key, key_id, suite_hash)
    _commit_defs(cfg)

    artifact_dir = tmp_path / "artifacts"
    result = issue_stat_cert(
        cfg,
        _seed_request("tool_candidate", "tool_base", "tool_oracle"),
        priv_key,
        b"seed",
        artifact_dir=artifact_dir,
    )
    cert = result["certificate"]
    transcript_hash = cert["transcript_hash"]
    row = json.loads((artifact_dir / f"{transcript_hash}.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["baseline_success"] is True
    assert row["candidate_success"] is False
    assert row["candidate_error"] == "timeout"
    assert row["candidate_termination"] == "timeout"
