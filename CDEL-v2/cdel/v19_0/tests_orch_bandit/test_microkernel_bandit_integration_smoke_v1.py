from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from orchestrator.omega_v19_0 import coordinator_v1 as coordinator_v19
from orchestrator.omega_v19_0.orch_bandit.bandit_v1 import select_capability_id


def _prepare_v19_noop_pack(dst_root: Path) -> tuple[Path, str]:
    src = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0_super_unified"
    dst = dst_root / "campaign_pack"
    shutil.copytree(src, dst)

    program = {
        "schema_version": "coordinator_isa_program_v1",
        "isa_version": 1,
        "program_id": "sha256:" + ("0" * 64),
        "entry_pc_u32": 0,
        "constants": {},
        "instructions": [{"op": "EMIT_PLAN", "args": {"plan_kind": "DECISION_PLAN_V1"}}],
        "declared_limits": {
            "max_steps_u64": 64,
            "max_stack_items_u32": 32,
            "max_trace_bytes_u64": 1_048_576,
        },
    }
    no_id = dict(program)
    no_id.pop("program_id", None)
    program["program_id"] = sha256_prefixed(canon_bytes(no_id))
    write_canon_json(dst / "coordinator_isa_program_v1.json", program)

    registry = load_canon_json(dst / "omega_capability_registry_v2.json")
    capabilities = [row for row in list(registry.get("capabilities") or []) if isinstance(row, dict)]
    capabilities.sort(key=lambda row: str(row.get("capability_id", "")))
    selected_capability_id = str(capabilities[0]["capability_id"])
    for row in capabilities:
        row["enabled"] = str(row.get("capability_id", "")) == selected_capability_id
    registry["capabilities"] = capabilities
    write_canon_json(dst / "omega_capability_registry_v2.json", registry)

    bandit_config = {
        "schema_version": "orch_bandit_config_v1",
        "selector_kind": "BANDIT_V1",
        "max_contexts_u32": 64,
        "max_arms_per_context_u32": 64,
        "alpha_q32": 2147483648,
        "explore_weight_q32": 2147483648,
        "cost_weight_q32": 1073741824,
        "cost_scale_ms_u64": 60000,
        "min_trials_before_exploit_u32": 2,
    }
    write_canon_json(dst / "orch_bandit_config_v1.json", bandit_config)

    opcode_table = load_canon_json(dst / "coordinator_opcode_table_v1.json")
    pack = load_canon_json(dst / "rsi_omega_daemon_pack_v1.json")
    pack["coordinator_isa_program_id"] = str(program["program_id"])
    pack["coordinator_opcode_table_id"] = str(opcode_table["opcode_table_id"])
    pack["policy_vm_mode"] = "DECISION_ONLY"
    pack["orch_bandit_config_rel"] = "orch_bandit_config_v1.json"
    write_canon_json(dst / "rsi_omega_daemon_pack_v1.json", pack)

    return dst / "rsi_omega_daemon_pack_v1.json", selected_capability_id


def _run_v19_tick(*, out_dir: Path, campaign_pack: Path, tick_u64: int) -> tuple[dict, Path]:
    prev_mode = os.environ.get("OMEGA_META_CORE_ACTIVATION_MODE")
    prev_allow = os.environ.get("OMEGA_ALLOW_SIMULATE_ACTIVATION")
    prev_seed = os.environ.get("OMEGA_RUN_SEED_U64")
    prev_det = os.environ.get("OMEGA_V19_DETERMINISTIC_TIMING")
    os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = "simulate"
    os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = "1"
    os.environ["OMEGA_RUN_SEED_U64"] = "424242"
    os.environ["OMEGA_V19_DETERMINISTIC_TIMING"] = "1"
    try:
        result = coordinator_v19.run_tick(
            campaign_pack=campaign_pack,
            out_dir=out_dir,
            tick_u64=tick_u64,
        )
    finally:
        if prev_mode is None:
            os.environ.pop("OMEGA_META_CORE_ACTIVATION_MODE", None)
        else:
            os.environ["OMEGA_META_CORE_ACTIVATION_MODE"] = prev_mode
        if prev_allow is None:
            os.environ.pop("OMEGA_ALLOW_SIMULATE_ACTIVATION", None)
        else:
            os.environ["OMEGA_ALLOW_SIMULATE_ACTIVATION"] = prev_allow
        if prev_seed is None:
            os.environ.pop("OMEGA_RUN_SEED_U64", None)
        else:
            os.environ["OMEGA_RUN_SEED_U64"] = prev_seed
        if prev_det is None:
            os.environ.pop("OMEGA_V19_DETERMINISTIC_TIMING", None)
        else:
            os.environ["OMEGA_V19_DETERMINISTIC_TIMING"] = prev_det
    state_dir = out_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    return result, state_dir


def test_microkernel_bandit_integration_smoke_v1(tmp_path: Path) -> None:
    campaign_pack, only_enabled_capability_id = _prepare_v19_noop_pack(tmp_path / "pack_src")
    _result, state_root = _run_v19_tick(
        out_dir=tmp_path / "run",
        campaign_pack=campaign_pack,
        tick_u64=1,
    )

    update_rows = sorted((state_root / "orch_bandit" / "updates").glob("sha256_*.orch_bandit_update_receipt_v1.json"))
    assert update_rows, "orch_bandit_update_receipt_v1 not written"
    update_receipt = load_canon_json(update_rows[-1])

    state_in_id = str(update_receipt.get("state_in_id", ""))
    hexd = state_in_id.split(":", 1)[1]
    state_in = load_canon_json(state_root / "orch_bandit" / "state" / f"sha256_{hexd}.orch_bandit_state_v1.json")

    bandit_config = load_canon_json(campaign_pack.parent / "orch_bandit_config_v1.json")
    expected_selected = select_capability_id(
        config=bandit_config,
        state=state_in,
        context_key=str(update_receipt.get("context_key", "")),
        eligible_capability_ids=[only_enabled_capability_id],
    )

    assert str(update_receipt.get("selected_capability_id", "")) == expected_selected
