#!/usr/bin/env python3
"""Local preflight checks for orchestrator dependencies."""

from __future__ import annotations

import importlib
import sys

_REQUIRED = [
    "cdel",
    "cdel.sealed.harnesses.pyut_v1",
    "cdel.sealed.harnesses.env_v1",
    "cdel.sealed.harnesses.io_v1",
]


def check_imports() -> list[str]:
    missing = []
    for name in _REQUIRED:
        try:
            importlib.import_module(name)
        except Exception:
            missing.append(name)
    return missing


def main() -> int:
    missing = check_imports()
    if missing:
        sys.stderr.write(
            "Preflight failed. Missing imports: " + ", ".join(missing) + "\n"
        )
        sys.stderr.write("Run ./scripts/dev_bootstrap.sh to install pinned deps.\n")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
