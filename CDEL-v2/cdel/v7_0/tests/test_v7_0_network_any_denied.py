from __future__ import annotations

from cdel.v1_7r.canon import load_canon_json
from cdel.v7_0.superego_policy import evaluate_policy
from .utils import build_request, repo_root


def test_v7_0_network_any_denied() -> None:
    policy = load_canon_json(
        repo_root() / "meta-core" / "meta_constitution" / "v7_0" / "superego_policy_v1.json"
    )
    request = build_request(
        {
            "daemon_id": "sha256:" + "1" * 64,
            "tick": 1,
            "objective_class": "VALIDATION",
            "objective_text": "net test",
            "capabilities": ["NETWORK_ANY"],
            "target_paths": ["/Users/harjas/AGI-Stack-Clean /"],
            "sealed_eval_required": False,
        }
    )
    decision, _reason = evaluate_policy(policy, request)
    assert decision == "DENY"
