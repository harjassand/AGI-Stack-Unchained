from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError, load_canon_json
from cdel.v3_1.constants import require_constants
from cdel.v3_1.immutable_core import load_lock, validate_lock
from cdel.v3_1.verify_rsi_swarm_v2 import VerifyContext, _verify_node, compute_swarm_run_id
from cdel.v3_1.tests.utils import build_valid_swarm_run


def test_v3_1_subswarm_cycle_detected_fatal(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    pack = load_canon_json(run["run_root"] / "pack.json")
    run_id = compute_swarm_run_id(pack)

    constants = require_constants()
    lock_path = repo_root / constants["IMMUTABLE_CORE_LOCK_REL"]
    lock = load_lock(lock_path)
    validate_lock(lock)

    ctx = VerifyContext(lock=lock, constants=constants, root_dir=run["run_root"], visited={run_id}, nodes=[])
    with pytest.raises(CanonError):
        _verify_node(run["run_root"], ctx)
