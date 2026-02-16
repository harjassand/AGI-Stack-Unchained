from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError, canon_bytes, sha256_prefixed, write_canon_json
from cdel.v4_0.verify_rsi_omega_v1 import verify

from .utils import build_minimal_omega_run


def test_v4_0_root_path_collision_rejected(tmp_path: Path, repo_root: Path) -> None:
    # Arrange a run directory such that verifier's derived "repo_root" (state_dir.parent.parent)
    # contains a colliding @ROOT path with different bytes.
    base_dir = tmp_path / "fake_repo" / "runs"
    ctx = build_minimal_omega_run(base_dir, repo_root, epochs=1, tasks_per_epoch=1, checkpoint_every=1, include_stop=True)
    run_root = ctx["run_root"]

    rel = Path("baselines/pi0_grand_challenge_v1/baseline_report_v1.json")
    run_path = run_root / rel
    repo_path = run_root.parent.parent / rel
    run_path.parent.mkdir(parents=True, exist_ok=True)
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_text("run", encoding="utf-8")
    repo_path.write_text("repo", encoding="utf-8")

    # Patch the omega pack to reference the colliding @ROOT path.
    pack_path = run_root / "rsi_real_omega_pack_v1.json"
    pack = (pack_path.read_text(encoding="utf-8")).strip()
    pack_obj = __import__("json").loads(pack)
    pack_obj["omega"]["baseline"]["baseline_report_path"] = f"@ROOT/{rel.as_posix()}"
    pack_obj["omega"]["baseline"]["baseline_report_hash"] = sha256_prefixed(repo_path.read_bytes())
    pack_obj["pack_hash"] = sha256_prefixed(canon_bytes({k: v for k, v in pack_obj.items() if k != "pack_hash"}))
    write_canon_json(pack_path, pack_obj)

    with pytest.raises(CanonError) as exc:
        verify(run_root)
    assert "OMEGA_ROOT_PATH_COLLISION" in str(exc.value)

