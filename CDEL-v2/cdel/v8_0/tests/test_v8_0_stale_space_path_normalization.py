from __future__ import annotations

from pathlib import Path

from cdel.v8_0 import verify_rsi_boundless_math_v1 as verify_v8


def test_stale_space_prefixed_daemon_path_normalizes_to_current_repo_root() -> None:
    repo_root = Path(verify_v8.__file__).resolve().parents[3]
    raw = "/Users/harjas/AGI-Stack-Clean /daemon/rsi_daemon_v8_0_math/state"
    normalized = verify_v8._normalize_path_for_known_repo_space_bug(raw)  # noqa: SLF001
    assert normalized == str(repo_root / "daemon" / "rsi_daemon_v8_0_math" / "state")
