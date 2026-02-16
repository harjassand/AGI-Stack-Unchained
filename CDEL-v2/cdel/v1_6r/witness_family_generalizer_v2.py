"""Witness-conditioned family generalizer v2 for RSI-5."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .canon import canon_bytes, hash_json, load_canon_json, write_canon_json
from .constants import require_constants
from .family_dsl.runtime import (
    _probe_keys,
    _semantic_signature_fields,
    compute_family_id,
    compute_signature,
    instantiate_family,
)
from .witness_constants import WITNESS_REPLAY_KEY_DOMAIN_V1
from .sr_cegar.gates import novelty_pass


def _parse_prefixed_hash(value: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError("hash value missing")
    hex_part = value.split(":", 1)[1] if ":" in value else value
    return bytes.fromhex(hex_part)


def _frontier_threshold(out_dir: Path) -> str | None:
    try:
        state_dir = out_dir.resolve().parents[2]
    except Exception:
        return None
    frontier_path = state_dir / "current" / "frontier_v1.json"
    if not frontier_path.exists():
        return None
    frontier = load_canon_json(frontier_path)
    families = frontier.get("families", []) if isinstance(frontier, dict) else []
    ids: list[str] = []
    if isinstance(families, list):
        for entry in families:
            if isinstance(entry, dict):
                fam_id = entry.get("family_id")
                if isinstance(fam_id, str):
                    ids.append(fam_id)
    if not ids:
        return None
    ids.sort()
    m_frontier = int(require_constants().get("sr", {}).get("m_frontier", len(ids)))
    idx = min(max(m_frontier - 1, 0), len(ids) - 1)
    return ids[idx]


def _frontier_signatures(out_dir: Path) -> list[dict[str, Any]]:
    try:
        state_dir = out_dir.resolve().parents[2]
    except Exception:
        return []
    frontier_path = state_dir / "current" / "frontier_v1.json"
    if not frontier_path.exists():
        return []
    frontier = load_canon_json(frontier_path)
    families = frontier.get("families", []) if isinstance(frontier, dict) else []
    sigs: list[dict[str, Any]] = []
    if isinstance(families, list):
        for entry in families:
            if not isinstance(entry, dict):
                continue
            fam_hash = entry.get("family_hash")
            if not isinstance(fam_hash, str):
                continue
            fam_path = state_dir / "current" / "families" / f"{fam_hash.split(':', 1)[1]}.json"
            if not fam_path.exists():
                continue
            fam = load_canon_json(fam_path)
            sig = fam.get("signature")
            if isinstance(sig, dict):
                sigs.append({"signature": sig})
    return sigs


def _frontier_env_fields(out_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    try:
        state_dir = out_dir.resolve().parents[2]
    except Exception:
        return []
    frontier_path = state_dir / "current" / "frontier_v1.json"
    if not frontier_path.exists():
        return []
    frontier = load_canon_json(frontier_path)
    families = frontier.get("families", []) if isinstance(frontier, dict) else []
    if not isinstance(families, list):
        return []
    key_a, _key_b, key_a_bytes, _key_b_bytes = _probe_keys()
    out: list[tuple[str, dict[str, Any]]] = []
    for entry in families:
        if not isinstance(entry, dict):
            continue
        fam_hash = entry.get("family_hash")
        if not isinstance(fam_hash, str):
            continue
        fam_path = state_dir / "current" / "families" / f"{fam_hash.split(':', 1)[1]}.json"
        if not fam_path.exists():
            continue
        fam = load_canon_json(fam_path)
        try:
            inst = instantiate_family(fam, {}, {"commitment": key_a}, epoch_key=key_a_bytes)
            payload = inst.get("payload") if isinstance(inst, dict) else None
            suite_row = payload.get("suite_row") if isinstance(payload, dict) else None
        except Exception:
            suite_row = None
        if not isinstance(suite_row, dict):
            continue
        env_kind = suite_row.get("env")
        fields = fam.get("signature", {}).get("fields") if isinstance(fam, dict) else None
        if not isinstance(env_kind, str) or not isinstance(fields, dict):
            continue
        out.append((env_kind, fields))
    return out


def _theta0_from_params(params_schema: list[dict[str, Any]]) -> dict[str, Any]:
    theta0: dict[str, Any] = {}
    for param in params_schema:
        name = param.get("name")
        if not isinstance(name, str):
            raise ValueError("missing param name")
        ptype = param.get("type")
        min_val = param.get("min")
        if ptype == "int":
            if not isinstance(min_val, int):
                raise ValueError("missing int min")
            theta0[name] = int(min_val)
        elif ptype == "fixed":
            if not isinstance(min_val, str):
                raise ValueError("missing fixed min")
            theta0[name] = min_val
        else:
            raise ValueError("unknown param type")
    return theta0


def _suite_row_hash_for_key(family: dict[str, Any], key_bytes: bytes) -> str | None:
    try:
        theta0 = _theta0_from_params(family.get("params_schema", []))
        commitment = "sha256:" + key_bytes.hex()
        inst = instantiate_family(family, theta0, {"commitment": commitment}, epoch_key=key_bytes)
        payload = inst.get("payload") if isinstance(inst, dict) else None
        suite_row = payload.get("suite_row") if isinstance(payload, dict) else None
        if not isinstance(suite_row, dict):
            return None
        return hash_json(suite_row)
    except Exception:
        return None


def _suite_row_for_key(family: dict[str, Any], key_bytes: bytes) -> dict[str, Any] | None:
    try:
        theta0 = _theta0_from_params(family.get("params_schema", []))
        commitment = "sha256:" + key_bytes.hex()
        inst = instantiate_family(family, theta0, {"commitment": commitment}, epoch_key=key_bytes)
        payload = inst.get("payload") if isinstance(inst, dict) else None
        suite_row = payload.get("suite_row") if isinstance(payload, dict) else None
        if not isinstance(suite_row, dict):
            return None
        return suite_row
    except Exception:
        return None


def _load_parent_witness(
    witness_index_path: Path, preferred_envs: list[str] | None = None
) -> tuple[str, dict[str, Any]] | None:
    index_payload = load_canon_json(witness_index_path)
    by_env = index_payload.get("witnesses_by_env_kind", {})
    if not isinstance(by_env, dict):
        return None

    def _hashes_for_env(env_kind: str) -> list[str]:
        env_bucket = by_env.get(env_kind)
        if not isinstance(env_bucket, dict):
            return []
        hashes: list[str] = []
        for kind in ("anchor", "pressure", "gate"):
            kind_list = env_bucket.get(kind)
            if isinstance(kind_list, list):
                hashes.extend([h for h in kind_list if isinstance(h, str)])
        return sorted(set(hashes))

    search_envs = preferred_envs or []
    for env_kind in search_envs:
        hashes = _hashes_for_env(env_kind)
        if hashes:
            parent_hash = hashes[0]
            witness_path = witness_index_path.parent / "instance_witnesses_v1" / f"{parent_hash.split(':', 1)[1]}.json"
            if witness_path.exists():
                witness = load_canon_json(witness_path)
                return parent_hash, witness

    # Fallback: smallest hash across all envs
    all_hashes: list[str] = []
    for env_kind in by_env.keys():
        all_hashes.extend(_hashes_for_env(env_kind))
    if not all_hashes:
        return None
    parent_hash = sorted(set(all_hashes))[0]
    witness_path = witness_index_path.parent / "instance_witnesses_v1" / f"{parent_hash.split(':', 1)[1]}.json"
    if not witness_path.exists():
        return None
    witness = load_canon_json(witness_path)
    return parent_hash, witness


def _mutation_seed(epoch_key: bytes, suite_row: dict[str, Any]) -> int:
    material = epoch_key + canon_bytes(suite_row)
    return int.from_bytes(hashlib.sha256(material).digest()[:4], "little")


def _mutate_gridworld(
    suite_row: dict[str, Any],
    seed_val: int,
    *,
    forbidden_nuisance: set[int] | None = None,
    forbidden_delay: set[int] | None = None,
) -> dict[str, Any]:
    _ = forbidden_delay
    forbid_nuisance = set(forbidden_nuisance or [])
    delta = 1 + (seed_val % 3)
    new_goal = {"x": int(delta), "y": 0}
    candidate_steps = [7, 8, 9]
    max_steps = candidate_steps[seed_val % len(candidate_steps)]
    if max_steps % 16 in forbid_nuisance:
        for step in candidate_steps:
            if step % 16 not in forbid_nuisance:
                max_steps = step
                break
    # Place a wall off the direct path to keep the task solvable.
    wall_x = 1 + (seed_val % 2)
    wall_y = 1
    mutated = dict(suite_row)
    mutated["start"] = {"x": 0, "y": 0}
    mutated["goal"] = new_goal
    mutated["walls"] = [{"x": int(wall_x), "y": int(wall_y)}]
    mutated["max_steps"] = int(max_steps)
    return mutated


def _mutate_lineworld(
    suite_row: dict[str, Any],
    seed_val: int,
    *,
    forbidden_nuisance: set[int] | None = None,
    forbidden_delay: set[int] | None = None,
) -> dict[str, Any]:
    _ = forbidden_delay
    forbid_nuisance = set(forbidden_nuisance or [])
    goal = 1 + (seed_val % 3)
    length = max(6, goal + 4)
    # Pick a small step budget that avoids existing nuisance buckets when possible.
    candidate_steps = [7, 8, 9]
    max_steps = candidate_steps[seed_val % len(candidate_steps)]
    if max_steps % 16 in forbid_nuisance:
        for step in candidate_steps:
            if step % 16 not in forbid_nuisance:
                max_steps = step
                break
    wall_pos = int(length)
    if wall_pos == goal:
        wall_pos = max(0, wall_pos - 1)
    mutated = dict(suite_row)
    mutated["length"] = int(length)
    mutated["start"] = 0
    mutated["goal"] = int(goal)
    mutated["walls"] = [int(wall_pos)]
    mutated["slip_p"] = 0
    mutated["max_steps"] = int(max_steps)
    return mutated


def _mutate_editworld(
    suite_row: dict[str, Any],
    vocab: list[str],
    max_goal_len: int,
    seed_val: int,
    *,
    forbidden_nuisance: set[int] | None = None,
    forbidden_delay: set[int] | None = None,
) -> dict[str, Any]:
    if not vocab:
        return dict(suite_row)
    forbid_nuisance = set(forbidden_nuisance or [])
    forbid_delay = set(forbidden_delay or [])
    vocab_len = len(vocab)
    # Deterministic search for a small, novel editworld variant.
    for offset in range(16):
        seed = seed_val + offset
        tok = vocab[seed % vocab_len]
        goal_len = 1 + (seed % 2)
        start_len = (seed // 2) % 2
        goal_text = (tok * (goal_len + 1))[:goal_len]
        start_text = (tok * (start_len + 1))[:start_len]
        if len(goal_text) > max_goal_len:
            goal_text = goal_text[:max_goal_len]
        # Keep steps small but avoid existing nuisance buckets when possible.
        candidate_steps = [7, 8, 9]
        max_steps = candidate_steps[seed % len(candidate_steps)]
        if max_steps % 16 in forbid_nuisance:
            for step in candidate_steps:
                if step % 16 not in forbid_nuisance:
                    max_steps = step
                    break
        start_cursor = 0
        if start_len > 0:
            start_cursor = seed % (start_len + 1)
        mutated = dict(suite_row)
        mutated["vocab_id"] = suite_row.get("vocab_id")
        mutated["start_text"] = start_text
        mutated["goal_text"] = goal_text
        mutated["start_cursor"] = int(start_cursor)
        mutated["slip_ppm"] = 0
        mutated["obs_window"] = int(suite_row.get("obs_window", 16))
        mutated["max_steps"] = int(max_steps)
        delay_class = _semantic_signature_fields(mutated).get("delay_class")
        nuisance_class = int(max_steps) % 16
        if isinstance(delay_class, int) and delay_class in forbid_delay:
            continue
        if nuisance_class in forbid_nuisance:
            continue
        return mutated
    return dict(suite_row)


def _base_family(
    *,
    parent_suite_row: dict[str, Any],
    mutated_suite_rows: list[dict[str, Any]],
    parent_witness_hash: str,
    salt: str,
) -> dict[str, Any]:
    max_steps = parent_suite_row.get("max_steps")
    if not isinstance(max_steps, int) or max_steps <= 0:
        max_steps = 16
    max_bound = max_steps
    for row in mutated_suite_rows:
        row_steps = row.get("max_steps")
        if isinstance(row_steps, int) and row_steps > max_bound:
            max_bound = row_steps
    choices = [{"suite_row": parent_suite_row}] + [{"suite_row": row} for row in mutated_suite_rows]
    family = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": int(max_bound),
            "max_instance_bytes": 4096,
            "max_instantiation_gas": 10000,
            "max_shrink_gas": 10000,
        },
        "instantiator": {
            "op": "KEYED_RAND_CHOICE_V1",
            "choices": choices,
            "tag": "witness_choice",
        },
        "x-provenance": "witness_family_generalizer_v2",
        "x-parent_witness_hash": parent_witness_hash,
        "x-salt": salt,
    }
    family["family_id"] = ""
    family["signature"] = compute_signature(family)
    for _ in range(6):
        new_id = compute_family_id(family)
        if new_id == family.get("family_id"):
            new_sig = compute_signature(family)
            if new_sig == family.get("signature"):
                break
            family["signature"] = new_sig
            continue
        family["family_id"] = new_id
        family["signature"] = compute_signature(family)
    family["family_id"] = compute_family_id(family)
    return family


def propose_witness_family_v2(
    *,
    epoch_id: str,
    epoch_key: bytes,
    witness_index_path: Path,
    frontier_hash: str,
    macro_active_set_hash: str | None,
    out_dir: Path,
) -> dict[str, Any] | None:
    _ = frontier_hash, macro_active_set_hash
    preferred_envs = None
    if isinstance(epoch_id, str):
        tail = epoch_id.split("_")[-1]
        if tail.isdigit():
            idx = int(tail) % 3
            cycle = [
                ["editworld-v1", "gridworld-v1", "lineworld-v1"],
                ["gridworld-v1", "lineworld-v1", "editworld-v1"],
                ["lineworld-v1", "editworld-v1", "gridworld-v1"],
            ]
            preferred_envs = cycle[idx]
    parent = _load_parent_witness(witness_index_path, preferred_envs=preferred_envs)
    if parent is None:
        return None
    parent_hash, parent_witness = parent
    parent_suite_row = parent_witness.get("suite_row")
    parent_suite_row_hash = parent_witness.get("suite_row_hash")
    if not isinstance(parent_suite_row, dict) or not isinstance(parent_suite_row_hash, str):
        return None

    frontier_threshold = _frontier_threshold(out_dir)
    frontier_sigs = _frontier_signatures(out_dir)
    frontier_fields = _frontier_env_fields(out_dir)

    env_kind = parent_suite_row.get("env", "gridworld-v1")
    constants = require_constants()
    editworld = constants.get("editworld", {})
    vocab_id = editworld.get("vocab_id")
    vocabs = editworld.get("vocabs", {})
    vocab = vocabs.get(vocab_id, []) if isinstance(vocabs, dict) else []
    max_goal_len = int(editworld.get("max_goal_len", 64))
    forbidden_nuisance: set[int] = set()
    forbidden_delay: set[int] = set()
    if env_kind == "editworld-v1" and frontier_fields:
        for env, fields in frontier_fields:
            if env != "editworld-v1":
                continue
            nuisance = fields.get("nuisance_class")
            delay = fields.get("delay_class")
            if isinstance(nuisance, int):
                forbidden_nuisance.add(nuisance)
            if isinstance(delay, int):
                forbidden_delay.add(delay)

    seed_val = _mutation_seed(epoch_key, parent_suite_row)
    mutated_suite_rows: list[dict[str, Any]] = []
    for offset in range(4):
        seed = seed_val + offset
        if env_kind == "lineworld-v1":
            candidate = _mutate_lineworld(
                parent_suite_row,
                seed,
                forbidden_nuisance=forbidden_nuisance,
                forbidden_delay=forbidden_delay,
            )
        elif env_kind == "editworld-v1":
            candidate = _mutate_editworld(
                parent_suite_row,
                vocab if isinstance(vocab, list) else [],
                max_goal_len,
                seed,
                forbidden_nuisance=forbidden_nuisance,
                forbidden_delay=forbidden_delay,
            )
        else:
            candidate = _mutate_gridworld(
                parent_suite_row,
                seed,
                forbidden_nuisance=forbidden_nuisance,
                forbidden_delay=forbidden_delay,
            )
        cand_hash = hash_json(candidate)
        if cand_hash == parent_suite_row_hash:
            continue
        if all(hash_json(existing) != cand_hash for existing in mutated_suite_rows):
            mutated_suite_rows.append(candidate)
        if len(mutated_suite_rows) >= 2:
            break

    if len(mutated_suite_rows) < 2:
        return None

    replay_key = hashlib.sha256(WITNESS_REPLAY_KEY_DOMAIN_V1.encode("utf-8") + _parse_prefixed_hash(parent_hash)).digest()
    probe_keys = constants.get("family_semantics", {})
    probe_a = probe_keys.get("probe_key_a")
    probe_b = probe_keys.get("probe_key_b")
    if not isinstance(probe_a, str) or not isinstance(probe_b, str):
        return None
    probe_a_bytes = _parse_prefixed_hash(probe_a)
    probe_b_bytes = _parse_prefixed_hash(probe_b)

    for attempt in range(2048):
        salt = f"wit-{epoch_id}-{attempt:03d}"
        family = _base_family(
            parent_suite_row=parent_suite_row,
            mutated_suite_rows=mutated_suite_rows,
            parent_witness_hash=parent_hash,
            salt=salt,
        )
        if frontier_threshold is not None and family.get("family_id") >= frontier_threshold:
            continue
        replay_hash = _suite_row_hash_for_key(family, replay_key)
        if replay_hash != parent_suite_row_hash:
            continue
        hash_a = _suite_row_hash_for_key(family, probe_a_bytes)
        hash_b = _suite_row_hash_for_key(family, probe_b_bytes)
        if hash_a is None or hash_b is None:
            continue
        if hash_a == replay_hash or hash_b == replay_hash:
            continue
        if hash_a == hash_b:
            continue
        epoch_suite = _suite_row_for_key(family, epoch_key)
        if not isinstance(epoch_suite, dict):
            continue
        if hash_json(epoch_suite) == parent_suite_row_hash:
            continue
        epoch_max_steps = epoch_suite.get("max_steps")
        if isinstance(epoch_max_steps, int) and epoch_max_steps > 8:
            continue
        if frontier_sigs:
            nov_ok, _dist = novelty_pass(family, frontier_sigs)
            if not nov_ok:
                continue
        out_dir.mkdir(parents=True, exist_ok=True)
        content_hash = hash_json(family).split(":", 1)[1]
        write_canon_json(out_dir / f"{content_hash}.json", family)
        return family

    return None
