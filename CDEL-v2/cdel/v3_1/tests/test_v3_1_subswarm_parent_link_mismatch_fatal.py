from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError, load_canon_json, write_canon_json
from cdel.v3_1.verify_rsi_swarm_v2 import verify
from cdel.v3_1.tests.utils import build_valid_swarm_run


def test_v3_1_subswarm_parent_link_mismatch_fatal(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    child_pack_path = run["child_dir"] / "subswarm_pack_v2.json"
    child_pack = load_canon_json(child_pack_path)
    child_pack["parent_link"]["parent_task_id"] = "sha256:" + "f" * 64
    write_canon_json(child_pack_path, child_pack)
    with pytest.raises(CanonError):
        verify(run["run_root"])
