from __future__ import annotations

from self_improve_code_v1.domains.flagship_code_rsi_v1.fail_signature_v1 import normalize_log, failure_signature


def test_fail_signature_stable() -> None:
    log_a = """
    2024-01-01 12:34:56 ERROR Traceback (most recent call last):
      File "/Users/harjas/AGI Stack/agi-system/foo.py", line 10, in <module>
    AssertionError: boom
    """
    log_b = """
    2026-02-02 01:02:03 ERROR Traceback (most recent call last):
      File "/tmp/other/path/foo.py", line 10, in <module>
    AssertionError: boom
    """
    norm_a = normalize_log(log_a)
    norm_b = normalize_log(log_b)
    assert norm_a == norm_b
    assert failure_signature(norm_a) == failure_signature(norm_b)
