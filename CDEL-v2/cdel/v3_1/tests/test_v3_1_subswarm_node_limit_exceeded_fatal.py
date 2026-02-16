from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v3_1.verify_rsi_swarm_v2 import verify
from cdel.v3_1.tests.utils import build_valid_swarm_run


def test_v3_1_subswarm_node_limit_exceeded_fatal(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root, root_max_total_nodes=1)
    with pytest.raises(CanonError):
        verify(run["run_root"])
