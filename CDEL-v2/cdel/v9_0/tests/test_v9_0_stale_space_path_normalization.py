from __future__ import annotations

from pathlib import Path

from cdel.v9_0 import verify_rsi_boundless_science_v1 as verify_v9


def test_stale_space_prefixed_daemon_path_normalizes_to_current_repo_root() -> None:
    repo_root = Path(verify_v9.__file__).resolve().parents[3]
    raw = "/Users/harjas/AGI-Stack-Clean /daemon/rsi_daemon_v9_0_science/state/science/attempts"
    normalized = verify_v9._normalize_path_for_known_repo_space_bug(raw)  # noqa: SLF001
    assert normalized == str(repo_root / "daemon" / "rsi_daemon_v9_0_science" / "state" / "science" / "attempts")
