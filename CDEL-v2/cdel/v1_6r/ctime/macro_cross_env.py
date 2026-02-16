"""Macro cross-environment support reporting for RSI-5."""

from __future__ import annotations

from typing import Any

from .macro import _action_key
from .tokenization import _get_action_name, _greedy_pass_comp, _greedy_pass_leaf, _leaf_and_composed, _expand_to_primitives


def _macro_occurrences(prims: list[str], macro_defs: list[dict[str, Any]]) -> dict[str, int]:
    macro_map: dict[str, dict[str, Any]] = {}
    for m in macro_defs:
        mid = m.get("macro_id")
        if isinstance(mid, str):
            macro_map[mid] = m
    leaf, comp = _leaf_and_composed(macro_defs)
    t1 = _greedy_pass_leaf(prims, leaf, macro_map)
    t2 = _greedy_pass_comp(t1, comp)
    occ: dict[str, int] = {}
    for kind, val in t2:
        if kind == "M":
            occ[val] = occ.get(val, 0) + 1
    return occ


def _macro_body_keys(macro_def: dict[str, Any]) -> list[tuple[str, str]]:
    body = macro_def.get("body", [])
    if not isinstance(body, list):
        return []
    keys: list[tuple[str, str]] = []
    for op in body:
        if not isinstance(op, dict) or "name" not in op:
            return []
        keys.append(_action_key(op))
    return keys


def _count_occurrences(actions: list[tuple[str, str]], body: list[tuple[str, str]]) -> int:
    if not body:
        return 0
    count = 0
    idx = 0
    while idx <= len(actions) - len(body):
        if actions[idx : idx + len(body)] == body:
            count += 1
            idx += len(body)
        else:
            idx += 1
    return count


def build_macro_cross_env_support_report(
    *,
    epoch_id: str,
    trace_events: list[dict[str, Any]],
    macro_defs: list[dict[str, Any]],
    macro_active_set_hash: str,
    instance_specs: dict[str, Any],
) -> dict[str, Any]:
    env_kinds = ["gridworld-v1", "lineworld-v1", "editworld-v1"]

    # Map inst_hash -> env_kind
    inst_env: dict[str, str] = {}
    for inst in instance_specs.values() if isinstance(instance_specs, dict) else []:
        if not isinstance(inst, dict):
            continue
        inst_hash = inst.get("inst_hash")
        payload = inst.get("payload")
        suite_row = payload.get("suite_row") if isinstance(payload, dict) else None
        env_kind = suite_row.get("env") if isinstance(suite_row, dict) else None
        if isinstance(inst_hash, str) and isinstance(env_kind, str):
            inst_env[inst_hash] = env_kind

    # Build action streams per env for tokenization
    prims_by_env: dict[str, list[str]] = {env: [] for env in env_kinds}
    for ev in trace_events:
        if not isinstance(ev, dict):
            continue
        inst_hash = ev.get("inst_hash")
        env_kind = inst_env.get(inst_hash)
        if env_kind not in prims_by_env:
            continue
        name = _get_action_name(ev)
        if isinstance(name, str):
            prims_by_env[env_kind].append(name)

    occ_by_env: dict[str, dict[str, int]] = {env: _macro_occurrences(prims, macro_defs) for env, prims in prims_by_env.items()}

    # Build action sequences per env/family for support counts
    actions_by_env_family: dict[str, dict[str, list[tuple[str, str]]]] = {env: {} for env in env_kinds}
    for ev in trace_events:
        if not isinstance(ev, dict):
            continue
        inst_hash = ev.get("inst_hash")
        env_kind = inst_env.get(inst_hash)
        if env_kind not in actions_by_env_family:
            continue
        family_id = ev.get("family_id")
        if not isinstance(family_id, str):
            continue
        actions_by_env_family[env_kind].setdefault(family_id, []).append(_action_key(ev.get("action", {})))

    macros_out: list[dict[str, Any]] = []
    for macro in macro_defs:
        macro_id = macro.get("macro_id")
        if not isinstance(macro_id, str):
            continue
        body_keys = _macro_body_keys(macro)
        occurrences_by_env_kind: dict[str, int] = {env: int(occ_by_env.get(env, {}).get(macro_id, 0)) for env in env_kinds}
        support_families_by_env: dict[str, int] = {env: 0 for env in env_kinds}
        support_total_by_env: dict[str, int] = {env: 0 for env in env_kinds}
        for env in env_kinds:
            for actions in actions_by_env_family.get(env, {}).values():
                count = _count_occurrences(actions, body_keys)
                if count > 0:
                    support_families_by_env[env] += 1
                    support_total_by_env[env] += count
        support_envs_hold = sum(1 for env in env_kinds if support_total_by_env.get(env, 0) > 0)
        macros_out.append(
            {
                "macro_id": macro_id,
                "occurrences_by_env_kind": occurrences_by_env_kind,
                "support_families_hold_by_env_kind": support_families_by_env,
                "support_total_hold_by_env_kind": support_total_by_env,
                "support_envs_hold": int(support_envs_hold),
            }
        )

    return {
        "schema": "macro_cross_env_support_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "macro_active_set_hash": macro_active_set_hash,
        "macros": macros_out,
    }
