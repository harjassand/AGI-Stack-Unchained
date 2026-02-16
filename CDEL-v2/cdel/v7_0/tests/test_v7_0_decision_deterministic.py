from __future__ import annotations

from cdel.v7_0.superego_policy import evaluate_policy
from .utils import build_request, repo_root
from cdel.v1_7r.canon import load_canon_json


def test_v7_0_decision_deterministic() -> None:
    policy = load_canon_json(
        repo_root() / "meta-core" / "meta_constitution" / "v7_0" / "superego_policy_v1.json"
    )
    request = build_request(
        {
            "daemon_id": "sha256:" + "0" * 64,
            "tick": 1,
            "objective_class": "MAINTENANCE",
            "objective_text": "health check",
            "capabilities": ["FS_READ_WORKSPACE", "FS_WRITE_DAEMON_STATE", "NETWORK_NONE"],
            "target_paths": ["/Users/harjas/AGI-Stack-Clean /daemon/"],
            "sealed_eval_required": False,
        }
    )
    d1 = evaluate_policy(policy, request)
    d2 = evaluate_policy(policy, request)
    assert d1 == d2
    assert policy.get("schema_version") == "superego_policy_v1"
