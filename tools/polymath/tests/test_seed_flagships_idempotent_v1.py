from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _seed_script() -> Path:
    return _repo_root() / "tools" / "polymath" / "polymath_seed_flagships_v1.py"


def test_seed_flagships_idempotent(monkeypatch, tmp_path: Path) -> None:
    store_root = tmp_path / "store"
    summary_a = tmp_path / "seed_summary_a.json"
    summary_b = tmp_path / "seed_summary_b.json"

    monkeypatch.setenv("OMEGA_POLYMATH_STORE_ROOT", store_root.as_posix())
    env = dict(os.environ)

    first = subprocess.run(
        [
            sys.executable,
            str(_seed_script()),
            "--summary_path",
            str(summary_a),
        ],
        cwd=_repo_root(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert int(first.returncode) == 0, first.stderr

    payload_a = json.loads(summary_a.read_text(encoding="utf-8"))
    required = [str(row) for row in payload_a.get("required_sha256s", [])]
    assert required
    for sha256 in required:
        digest = sha256.split(":", 1)[1]
        blob = store_root / "blobs" / "sha256" / digest
        assert blob.exists() and blob.is_file()

    second = subprocess.run(
        [
            sys.executable,
            str(_seed_script()),
            "--summary_path",
            str(summary_b),
        ],
        cwd=_repo_root(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert int(second.returncode) == 0, second.stderr

    payload_b = json.loads(summary_b.read_text(encoding="utf-8"))
    assert bool(payload_b.get("builder_ran_b", True)) is False
    assert list(payload_b.get("missing_before_sha256s", [])) == []
