from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v18_0.omega_common_v1 import tree_hash
from orchestrator.omega_v19_0 import coordinator_v1


def _prepare_determinism_pack(tmp_path: Path) -> Path:
    src = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0"
    dst = tmp_path / "campaign_pack"
    shutil.copytree(src, dst)

    policy = load_canon_json(dst / "omega_policy_ir_v1.json")
    policy["rules"] = []
    write_canon_json(dst / "omega_policy_ir_v1.json", policy)

    runaway_cfg = load_canon_json(dst / "omega_runaway_config_v1.json")
    runaway_cfg["enabled"] = False
    write_canon_json(dst / "omega_runaway_config_v1.json", runaway_cfg)

    write_canon_json(
        dst / "goals" / "omega_goal_queue_v1.json",
        {"schema_version": "omega_goal_queue_v1", "goals": []},
    )
    return dst / "rsi_omega_daemon_pack_v1.json"


def _latest(path: Path, pattern: str) -> Path:
    rows = sorted(path.glob(pattern), key=lambda row: row.as_posix())
    if not rows:
        raise AssertionError(f"missing {pattern} under {path}")
    return rows[-1]


def _run_two_ticks(*, root: Path, campaign_pack: Path) -> tuple[Path, dict[str, Any]]:
    out_1 = root / "run_tick_0001"
    result_1 = coordinator_v1.run_tick(
        campaign_pack=campaign_pack,
        out_dir=out_1,
        tick_u64=1,
        prev_state_dir=None,
    )
    state_1 = out_1 / "daemon" / "rsi_omega_daemon_v19_0" / "state"

    out_2 = root / "run_tick_0002"
    result_2 = coordinator_v1.run_tick(
        campaign_pack=campaign_pack,
        out_dir=out_2,
        tick_u64=2,
        prev_state_dir=state_1,
    )
    state_2 = out_2 / "daemon" / "rsi_omega_daemon_v19_0" / "state"

    result = {
        "tick_1": result_1,
        "tick_2": result_2,
        "timings_log": (state_2 / "ledger" / "timings.log").read_text(encoding="utf-8"),
        "tick_perf_text": _latest(state_2 / "perf", "sha256_*.omega_tick_perf_v1.json").read_text(encoding="utf-8"),
    }
    return state_2, result


def test_v19_tier2_tree_hash_deterministic(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMEGA_RUN_SEED_U64", "424242")
    monkeypatch.setattr(coordinator_v1, "read_meta_core_active_manifest_hash", lambda: "sha256:" + ("0" * 64))
    monkeypatch.setattr(
        coordinator_v1,
        "synthesize_goal_queue",
        lambda **kwargs: kwargs["goal_queue_base"],
    )
    campaign_pack = _prepare_determinism_pack(tmp_path)

    state_a, artifacts_a = _run_two_ticks(root=tmp_path / "v19_e2e_a", campaign_pack=campaign_pack)
    state_b, artifacts_b = _run_two_ticks(root=tmp_path / "v19_e2e_b", campaign_pack=campaign_pack)

    assert tree_hash(state_a) == tree_hash(state_b)
    assert artifacts_a["timings_log"] == artifacts_b["timings_log"]
    assert artifacts_a["tick_perf_text"] == artifacts_b["tick_perf_text"]
