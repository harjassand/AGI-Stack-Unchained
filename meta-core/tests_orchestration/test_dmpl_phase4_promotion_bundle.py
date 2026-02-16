from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))


def _write_canon_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_dmpl_phase4_train_orchestrator_bundle_promotable(tmp_path: Path) -> None:
    # Minimal campaign pack (content is not used by the producer, but must be canonical JSON).
    pack_path = tmp_path / "pack.json"
    _write_canon_json(pack_path, {"schema_id": "rsi_eudrs_u_train_pack_v1"})

    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    from orchestrator.rsi_eudrs_u_train_v1 import main as train_main

    rc = int(train_main(["--campaign_pack", str(pack_path), "--out_dir", str(out_dir)]))
    assert rc == 0

    state_dir = out_dir / "daemon" / "rsi_eudrs_u_train_v1" / "state"
    assert (state_dir / "eudrs_u" / "evidence").is_dir()
    assert (state_dir / "eudrs_u" / "staged_registry_tree").is_dir()

    from cdel.v18_0.eudrs_u.verify_eudrs_u_promotion_v1 import verify as verify_promotion

    verdict = str(verify_promotion(state_dir, mode="full"))
    assert verdict == "VALID"

