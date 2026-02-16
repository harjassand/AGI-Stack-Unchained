"""Deterministic family generalizer v1 for RSI-4 campaigns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..canon import hash_json, load_canon_json, write_canon_json
from ..family_semantics import build_family_semantics_report
from ..family_dsl.runtime import compute_family_id, compute_signature
from ..sr_cegar.gates import novelty_pass
from ..sr_cegar.witness_ledger import load_ledger_lines, verify_ledger_chain, witness_hashes_from_ledger


def _load_frontier_families(state_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    frontier_path = state_dir / "current" / "frontier_v1.json"
    frontier = load_canon_json(frontier_path)
    family_objs: list[dict[str, Any]] = []
    sig_list: list[dict[str, Any]] = []
    for entry in frontier.get("families", []) if isinstance(frontier, dict) else []:
        fam_hash = entry.get("family_hash")
        if not isinstance(fam_hash, str):
            continue
        fam_path = state_dir / "current" / "families" / f"{fam_hash.split(':', 1)[1]}.json"
        if not fam_path.exists():
            continue
        family = load_canon_json(fam_path)
        family_objs.append(family)
        sig = family.get("signature")
        if isinstance(sig, dict):
            sig_list.append({"family_id": family.get("family_id"), "signature": sig})
    return family_objs, sig_list


def _max_frontier_id(family_objs: list[dict[str, Any]]) -> str | None:
    ids = [fam.get("family_id") for fam in family_objs if isinstance(fam.get("family_id"), str)]
    return max(ids) if ids else None


def _base_family(
    *,
    env_kind: str,
    resource_bounds_steps: int,
    suite_steps: int,
    goal_max: int,
    salt: str,
    parent_witness_hash: str,
) -> dict[str, Any]:
    goal_min = max(2, int(goal_max) - 1)
    if env_kind == "lineworld-v1":
        length_val = max(12, int(goal_max) + 4)
        instantiator = {
            "op": "LINEWORLD_BUILD_V1",
            "length": {"op": "CONST", "value": int(length_val)},
            "start": {"op": "CONST", "value": 0},
            "goal": {"op": "KEYED_RAND_INT_V1", "min": int(goal_min), "max": int(goal_max), "tag": "goal"},
            "walls_k": {"op": "KEYED_RAND_INT_V1", "min": 1, "max": 2, "tag": "walls_k"},
            "max_steps": {"op": "CONST", "value": int(suite_steps)},
            "slip_ppm": {"op": "CONST", "value": 0},
        }
    else:
        instantiator = {
            "op": "GRIDWORLD_BUILD_V1",
            "width": {"op": "CONST", "value": int(goal_max)},
            "height": {"op": "CONST", "value": 1},
            "start": {"op": "CONST", "value": {"x": 0, "y": 0}},
            "goal": {"op": "CONST", "value": {"x": int(goal_max), "y": 0}},
            "walls_k": {"op": "KEYED_RAND_INT_V1", "min": 1, "max": 2, "tag": "walls_k"},
            "max_steps": {"op": "CONST", "value": int(suite_steps)},
        }

    family = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": int(resource_bounds_steps),
            "max_instance_bytes": 4096,
            "max_instantiation_gas": 10000,
            "max_shrink_gas": 10000,
        },
        "instantiator": instantiator,
        "x-provenance": "family_generalizer_v1",
        "x-parent_witness_hash": parent_witness_hash,
        "x-salt": salt,
    }
    family["family_id"] = ""
    family["signature"] = compute_signature(family)
    for _ in range(6):
        new_family_id = compute_family_id(family)
        if new_family_id == family.get("family_id"):
            new_signature = compute_signature(family)
            if new_signature == family.get("signature"):
                break
            family["signature"] = new_signature
            continue
        family["family_id"] = new_family_id
        family["signature"] = compute_signature(family)
    family["family_id"] = compute_family_id(family)
    return family


def _frontier_bounds_steps(family_objs: list[dict[str, Any]]) -> int:
    for family in family_objs:
        bounds = family.get("resource_bounds")
        if isinstance(bounds, dict):
            value = bounds.get("max_env_steps_per_instance")
            if isinstance(value, int) and value > 0:
                return int(value)
    return 14


def propose_next_family(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    state_dir: Path,
    out_dir: Path,
) -> dict[str, Any] | None:
    _ = manifest, manifest_path
    ledger_path = state_dir / "current" / "witness_ledger_v1.jsonl"
    ledger_lines = load_ledger_lines(ledger_path)
    if not ledger_lines:
        return None
    verify_ledger_chain(ledger_lines)
    witness_hashes = list(witness_hashes_from_ledger(ledger_lines))
    if not witness_hashes:
        return None
    parent_hash = witness_hashes[-1]

    family_objs, frontier_sigs = _load_frontier_families(state_dir)
    max_id = _max_frontier_id(family_objs)

    state_path = state_dir / "current" / "family_generalizer_state_v1.json"
    state = load_canon_json(state_path) if state_path.exists() else {}
    if not isinstance(state, dict):
        state = {}
    next_index = int(state.get("next_index", 0))
    grid_count = int(state.get("grid_count", 0))
    line_count = int(state.get("line_count", 0))

    env_kind = "gridworld-v1" if next_index % 2 == 0 else "lineworld-v1"
    bounds_steps = _frontier_bounds_steps(family_objs)
    suite_steps = max(4, int(bounds_steps))
    goal_max = max(4, int(suite_steps))

    for attempt in range(256):
        salt = f"ins-{next_index:03d}-{attempt:03d}"
        family = _base_family(
            env_kind=env_kind,
            resource_bounds_steps=bounds_steps,
            suite_steps=suite_steps,
            goal_max=goal_max,
            salt=salt,
            parent_witness_hash=parent_hash,
        )
        family_id = family.get("family_id")
        if not isinstance(family_id, str):
            continue
        hex_id = family_id.split(":", 1)[1] if ":" in family_id else family_id
        if not hex_id or hex_id[0] not in "0123456789ab":
            continue
        semantics_report = build_family_semantics_report(
            epoch_id="campaign",
            family=family,
            prev_frontier_families=family_objs,
        )
        checks = semantics_report.get("checks", {})
        key_ok = bool(checks.get("key_sensitive", {}).get("ok"))
        fp_ok = bool(checks.get("fingerprint_unique_vs_prev_frontier", {}).get("ok"))
        sig_ok = bool(checks.get("signature_matches_recomputed", {}).get("ok"))
        nov_ok, _dist = novelty_pass(family, frontier_sigs)
        if not (key_ok and fp_ok and sig_ok and nov_ok):
            continue
        if isinstance(max_id, str) and family.get("family_id") >= max_id:
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        content_hash = hash_json(family).split(":", 1)[1]
        write_canon_json(out_dir / f"{content_hash}.json", family)
        state["next_index"] = next_index + 1
        if env_kind == "gridworld-v1":
            state["grid_count"] = grid_count + 1
        else:
            state["line_count"] = line_count + 1
        write_canon_json(state_path, state)
        return family

    return None
