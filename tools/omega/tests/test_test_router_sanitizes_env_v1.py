from __future__ import annotations

import sys
from pathlib import Path

from tools.omega import omega_test_router_v1 as router


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_run_cmd_strips_polymath_store_env(monkeypatch) -> None:
    monkeypatch.setenv("OMEGA_POLYMATH_STORE_ROOT", "/tmp/nonexistent_polymath_store")
    result = router._run_cmd(  # noqa: SLF001
        cmd=[
            sys.executable,
            "-c",
            (
                "import os,sys;"
                "sys.exit(0 if os.environ.get('OMEGA_POLYMATH_STORE_ROOT','')=='' else 1)"
            ),
        ],
        cwd=_repo_root(),
    )
    assert int(result.get("return_code", 1)) == 0


def test_route_low_risk_ignores_polymath_store_env(monkeypatch) -> None:
    monkeypatch.setenv("OMEGA_POLYMATH_STORE_ROOT", "/tmp/nonexistent_polymath_store")
    monkeypatch.setenv("OMEGA_NET_LIVE_OK", "1")
    report = router.route_and_run(
        touched_paths=[
            "polymath/registry/polymath_scout_status_v1.json",
            "polymath/registry/polymath_void_report_v1.jsonl",
        ],
        mode="promotion",
        repo_root=_repo_root(),
    )
    assert str(report.get("result", "")) == "PASS"
