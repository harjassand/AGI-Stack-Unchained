from __future__ import annotations

import pytest

from cdel.v6_0.daemon_ledger import validate_daemon_chain
from .utils import build_entry


def test_v6_0_ledger_hashchain_valid_and_tamper() -> None:
    prev = "GENESIS"
    entries = []
    entries.append(build_entry(1, 0, "BOOT", prev))
    prev = entries[-1]["entry_hash"]
    entries.append(build_entry(2, 1, "TICK_BEGIN", prev))
    prev = entries[-1]["entry_hash"]
    entries.append(build_entry(3, 1, "ACTIVITY_DONE", prev))

    validate_daemon_chain(entries)

    tampered = list(entries)
    tampered[1] = dict(tampered[1])
    tampered[1]["prev_entry_hash"] = "deadbeef" * 8
    with pytest.raises(Exception):
        validate_daemon_chain(tampered)
