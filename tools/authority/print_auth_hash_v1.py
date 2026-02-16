#!/usr/bin/env python3
"""Print authority AUTH_HASH for the currently checked-out repository."""

from __future__ import annotations

import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    value = str(_entry)
    if value not in sys.path:
        sys.path.insert(0, value)

from cdel.v18_0.authority.authority_hash_v1 import auth_hash, load_authority_pins


def main() -> None:
    pins = load_authority_pins(_REPO_ROOT)
    print(auth_hash(pins))


if __name__ == "__main__":
    main()
