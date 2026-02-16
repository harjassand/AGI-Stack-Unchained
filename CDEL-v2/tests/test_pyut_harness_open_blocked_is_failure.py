from __future__ import annotations

import json

from cdel.sealed.crypto import generate_keypair, key_id_from_public_key
from cdel.sealed.suites import compute_suite_hash_bytes
from cdel.sealed.worker import issue_stat_cert

from tests.conftest import init_repo
from tests.test_sealed_pyut_harness_determinism import _commit_defs, _pyut_defaults, _seed_request


def _write_suite(cfg) -> str:
    row = {
        "episode": 0,
        "task_id": "abs_int_v1",
        "fn_name": "abs_int",
        "signature": "def abs_int(x: int) -> int:",
        "tests": [{"args": [2], "expected": 2}],
    }
    content = json.dumps(row, sort_keys=True) + "\n"
    suite_hash = compute_suite_hash_bytes(content.encode("utf-8"))
    suite_dir = cfg.root / "sealed_suites"
    suite_dir.mkdir(parents=True, exist_ok=True)
    (suite_dir / f"{suite_hash}.jsonl").write_text(content, encoding="utf-8")
    return suite_hash


def test_pyut_harness_open_blocked_is_failure(tmp_path):
    cfg = init_repo(tmp_path)
    suite_hash = _write_suite(cfg)
    priv_key, pub_key = generate_keypair()
    key_id = key_id_from_public_key(pub_key)
    _pyut_defaults(cfg, pub_key, key_id, suite_hash)

    baseline_src = "def abs_int(x: int) -> int:\n    return x if x >= 0 else -x\n"
    candidate_src = "def abs_int(x: int) -> int:\n    f = open('/etc/passwd', 'r')\n    return 0\n"
    _commit_defs(cfg, baseline_src, candidate_src, baseline_src)

    artifact_dir = tmp_path / "artifacts"
    result = issue_stat_cert(
        cfg,
        _seed_request("pyut_candidate", "pyut_base", "pyut_oracle"),
        priv_key,
        b"seed",
        artifact_dir=artifact_dir,
    )
    cert = result["certificate"]
    transcript_hash = cert["transcript_hash"]
    row = json.loads((artifact_dir / f"{transcript_hash}.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert row["baseline_success"] is True
    assert row["candidate_error"] == "security_violation"
    assert row["candidate_error_detail"] == "SecurityViolation"
    assert cert["candidate_successes"] == 0
