"""Minimal deterministic policy synthesizer for RSI integrity campaigns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..canon import hash_json, load_canon_json, write_canon_json


def _policy_right_def(action_value: int = 3, *, name: str = "policy_right") -> dict[str, Any]:
    return {
        "name": name,
        "params": [
            {"name": "agent_x", "type": {"tag": "int"}},
            {"name": "agent_y", "type": {"tag": "int"}},
            {"name": "goal_x", "type": {"tag": "int"}},
            {"name": "goal_y", "type": {"tag": "int"}},
        ],
        "ret_type": {"tag": "int"},
        "body": {"tag": "int", "value": int(action_value)},
        "termination": {"kind": "structural", "decreases_param": None},
    }


def _required_policy_name(frontier_hash: str) -> str:
    hex_part = frontier_hash.split(":", 1)[1] if ":" in frontier_hash else frontier_hash
    suffix = hex_part[-1] if hex_part else "0"
    return f"policy_right_{suffix}"


def synthesize_policy_patch(
    *,
    state_dir: Path,
    diagnostics_dir: Path,
    out_dir: Path,
    action_value: int = 3,
) -> dict[str, Any] | None:
    witness_hash = None
    witness_index_path = diagnostics_dir / "failure_witness_v1.json"
    if witness_index_path.exists():
        witness_index = load_canon_json(witness_index_path)
        witness_hashes = witness_index.get("witnesses", []) if isinstance(witness_index, dict) else []
        if witness_hashes:
            witness_hash = witness_hashes[-1]

    state_head_path = state_dir / "current" / "state_ledger_head_v1.json"
    if not state_head_path.exists():
        return None
    state_head = load_canon_json(state_head_path)
    base_state_hash = state_head.get("ledger_head_hash")
    if not isinstance(base_state_hash, str):
        return None

    frontier_path = state_dir / "current" / "frontier_v1.json"
    frontier_hash = None
    if frontier_path.exists():
        frontier_payload = load_canon_json(frontier_path)
        frontier_hash = hash_json(frontier_payload)
    policy_name = _required_policy_name(frontier_hash) if isinstance(frontier_hash, str) else "policy_right"
    policy_program = _policy_right_def(action_value, name=policy_name)
    patch = {
        "schema": "mech_patch_v1",
        "schema_version": 1,
        "patch_id": "",
        "base_state_hash": base_state_hash,
        "policy_program": policy_program,
        "bounds": {
            "max_env_steps_per_instance": 512,
            "max_instance_bytes": 4096,
            "max_instantiation_gas": 1024,
            "max_shrink_gas": 1024,
        },
        "x-provenance": "policy_synthesizer_v1",
    }
    if isinstance(witness_hash, str):
        patch["x-witness_hash"] = witness_hash
    patch_id = hash_json({k: v for k, v in patch.items() if k != "patch_id"})
    patch["patch_id"] = patch_id

    out_dir.mkdir(parents=True, exist_ok=True)
    content_hash = hash_json(patch).split(":", 1)[1]
    write_canon_json(out_dir / f"{content_hash}.json", patch)
    return patch
