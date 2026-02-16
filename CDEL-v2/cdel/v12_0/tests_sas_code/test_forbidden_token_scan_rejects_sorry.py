from __future__ import annotations

from cdel.v12_0.sas_code_proof_task_v1 import scan_forbidden_tokens


def test_forbidden_token_scan_rejects_sorry() -> None:
    hits = scan_forbidden_tokens("theorem x := by sorry")
    assert "sorry" in hits
