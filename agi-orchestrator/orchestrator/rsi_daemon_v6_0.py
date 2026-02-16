"""CLI entrypoint for RSI daemon v6.0."""

from __future__ import annotations

from orchestrator.daemon_v6_0.daemon_main_v1 import main


if __name__ == "__main__":
    raise SystemExit(main())
