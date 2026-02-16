"""SCI witness-conditioned family generalizer (v1.7r).

Outputs a family_dsl_v1 proposal into current/inbox/family_proposals_v1/
that is replay-verifiable against a parent science witness.

Hard requirements:
- replay_key = sha256(SCI_WITNESS_REPLAY_KEY_DOMAIN_V1 || parent_witness_hash_bytes)
- epoch lag: parent witness epoch < current epoch
- mutation: probe keys must not replay the parent suite_row
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, hash_json, load_canon_json, write_canon_json

# Reuse stable family DSL runtime + novelty gate machinery.
from cdel.v1_6r.constants import require_constants
from cdel.v1_6r.family_dsl.runtime import compute_family_id, compute_signature, instantiate_family
from cdel.v1_6r.sr_cegar.gates import novelty_pass


SCI_WITNESS_REPLAY_KEY_DOMAIN_V1 = "SCI_WITNESS_REPLAY_KEY_V1"


def _parse_prefixed_hash(value: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError("hash value missing")
    hex_part = value.split(":", 1)[1] if ":" in value else value
    return bytes.fromhex(hex_part)


def _epoch_index(epoch_id: str) -> int | None:
    if not isinstance(epoch_id, str):
        return None
    tail = epoch_id.split("_")[-1]
    if tail.isdigit():
        return int(tail)
    return None


def _lag_ok(parent_epoch_id: str, current_epoch_id: str) -> bool:
    p = _epoch_index(parent_epoch_id)
    c = _epoch_index(current_epoch_id)
    if p is not None and c is not None:
        return p < c
    # Fallback: lexicographic if unknown format
    return parent_epoch_id < current_epoch_id


def _frontier_threshold(out_dir: Path) -> str | None:
    """Optional: avoid proposing family_ids lexicographically beyond a frontier threshold."""
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
    """Load frontier family signatures (for novelty gate)."""
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


def _load_parent_science_witness(
    witness_index_path: Path, preferred_envs: list[str] | None = None
) -> tuple[str, dict[str, Any]] | None:
    idx_payload = load_canon_json(witness_index_path)
    if not isinstance(idx_payload, dict):
        return None
    by_env = idx_payload.get("by_env_kind", {})
    if not isinstance(by_env, dict):
        return None

    def _hashes_for_env(env_kind: str) -> list[str]:
        env_bucket = by_env.get(env_kind)
        if not isinstance(env_bucket, dict):
            return []
        hashes: list[str] = []
        for kind in ("anchor", "pressure"):
            kind_list = env_bucket.get(kind)
            if isinstance(kind_list, list):
                hashes.extend([h for h in kind_list if isinstance(h, str)])
        return sorted(set(hashes))

    search_envs = preferred_envs or []
    for env_kind in search_envs:
        hashes = _hashes_for_env(env_kind)
        if hashes:
            parent_hash = hashes[0]
            witness_path = (
                witness_index_path.parent / "science_instance_witnesses_v1" / f"{parent_hash.split(':', 1)[1]}.json"
            )
            if witness_path.exists():
                witness = load_canon_json(witness_path)
                if isinstance(witness, dict):
                    return parent_hash, witness

    # Fallback: smallest hash across all envs
    all_hashes: list[str] = []
    for env_kind in by_env.keys():
        if isinstance(env_kind, str):
            all_hashes.extend(_hashes_for_env(env_kind))
    if not all_hashes:
        return None
    parent_hash = sorted(set(all_hashes))[0]
    witness_path = witness_index_path.parent / "science_instance_witnesses_v1" / f"{parent_hash.split(':', 1)[1]}.json"
    if not witness_path.exists():
        return None
    witness = load_canon_json(witness_path)
    if not isinstance(witness, dict):
        return None
    return parent_hash, witness


def _mutation_seed(epoch_key: bytes, suite_row: dict[str, Any]) -> int:
    material = epoch_key + canon_bytes(suite_row)
    return int.from_bytes(hashlib.sha256(material).digest()[:4], "little")


def _clamp_int(x: int, lo: int, hi: int) -> int:
    return lo if x < lo else hi if x > hi else x


def _mutate_wmworld(suite_row: dict[str, Any], seed_val: int) -> dict[str, Any]:
    # Safe, small deterministic mutations that preserve schema invariants.
    delta = 1 + (seed_val % 3)
    mutated = dict(suite_row)
    gen = dict(mutated.get("generator", {}) if isinstance(mutated.get("generator"), dict) else {})
    # Expand true separator ranges deterministically.
    wmin = int(gen.get("w_true_min", -3))
    wmax = int(gen.get("w_true_max", 3))
    bmin = int(gen.get("b_true_min", -3))
    bmax = int(gen.get("b_true_max", 3))
    gen["w_true_min"] = _clamp_int(wmin - delta, -9, 9)
    gen["w_true_max"] = _clamp_int(wmax + delta, -9, 9)
    if gen["w_true_min"] > gen["w_true_max"]:
        gen["w_true_min"], gen["w_true_max"] = gen["w_true_max"], gen["w_true_min"]
    gen["b_true_min"] = _clamp_int(bmin - (delta % 2), -9, 9)
    gen["b_true_max"] = _clamp_int(bmax + (delta % 2), -9, 9)
    if gen["b_true_min"] > gen["b_true_max"]:
        gen["b_true_min"], gen["b_true_max"] = gen["b_true_max"], gen["b_true_min"]
    mutated["generator"] = gen

    # Also perturb max_steps slightly (bounded) to help avoid signature collisions elsewhere.
    ms = int(mutated.get("max_steps", 128))
    mutated["max_steps"] = _clamp_int(ms + (delta % 5), 8, 256)
    return mutated


def _mutate_causalworld(suite_row: dict[str, Any], seed_val: int) -> dict[str, Any]:
    delta = 1 + (seed_val % 3)
    mutated = dict(suite_row)
    gen = dict(mutated.get("generator", {}) if isinstance(mutated.get("generator"), dict) else {})
    # Small coefficient tweaks.
    a_z = int(gen.get("a_z", 2))
    a_w = int(gen.get("a_w", 2))
    gen["a_z"] = _clamp_int(a_z + (delta % 2), -9, 9)
    gen["a_w"] = _clamp_int(a_w - (delta % 2), -9, 9)
    mutated["generator"] = gen

    ms = int(mutated.get("max_steps", 96))
    mutated["max_steps"] = _clamp_int(ms + (delta % 5), 8, 256)
    return mutated


def _base_family(
    *,
    parent_suite_row: dict[str, Any],
    mutated_suite_rows: list[dict[str, Any]],
    parent_witness_hash: str,
    salt: str,
) -> dict[str, Any]:
    max_steps = parent_suite_row.get("max_steps")
    if not isinstance(max_steps, int) or max_steps <= 0:
        max_steps = 64
    max_bound = max_steps
    for row in mutated_suite_rows:
        row_steps = row.get("max_steps")
        if isinstance(row_steps, int) and row_steps > max_bound:
            max_bound = row_steps

    choices = [{"suite_row": parent_suite_row}] + [{"suite_row": row} for row in mutated_suite_rows]
    family: dict[str, Any] = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": int(max_bound),
            "max_instance_bytes": 16384,
            "max_instantiation_gas": 20000,
            "max_shrink_gas": 20000,
        },
        "instantiator": {
            "op": "KEYED_RAND_CHOICE_V1",
            "choices": choices,
            "tag": "science_witness_choice",
        },
        "x-provenance": "witness_family_generalizer_science_v1",
        "x-parent_witness_hash": parent_witness_hash,
        "x-salt": salt,
    }

    # Fixpoint-ish stabilization (same approach as v1_6r witness family generalizer).
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
    family["signature"] = compute_signature(family)
    return family


def propose_witness_family_science_v1(
    *,
    epoch_id: str,
    epoch_key: bytes,
    witness_index_path: Path,
    frontier_hash: str,
    out_dir: Path,
) -> dict[str, Any] | None:
    _ = frontier_hash

    parent = _load_parent_science_witness(witness_index_path)
    if parent is None:
        return None
    parent_hash, parent_witness = parent

    parent_epoch = parent_witness.get("epoch_id")
    if not isinstance(parent_epoch, str):
        return None
    if not _lag_ok(parent_epoch, epoch_id):
        return None

    parent_suite_row = parent_witness.get("suite_row")
    parent_suite_row_hash = parent_witness.get("suite_row_hash")
    if not isinstance(parent_suite_row, dict) or not isinstance(parent_suite_row_hash, str):
        return None

    env_kind = parent_witness.get("env_kind")
    if not isinstance(env_kind, str):
        env_kind = parent_suite_row.get("env")
    if env_kind not in ("wmworld-v1", "causalworld-v1"):
        return None

    seed_val = _mutation_seed(epoch_key, parent_suite_row)
    mutated_suite_rows: list[dict[str, Any]] = []
    for offset in range(8):
        seed = seed_val + offset
        if env_kind == "wmworld-v1":
            candidate = _mutate_wmworld(parent_suite_row, seed)
        else:
            candidate = _mutate_causalworld(parent_suite_row, seed)

        cand_hash = hash_json(candidate)
        if cand_hash == parent_suite_row_hash:
            continue
        if all(hash_json(existing) != cand_hash for existing in mutated_suite_rows):
            mutated_suite_rows.append(candidate)
        if len(mutated_suite_rows) >= 2:
            break
    if len(mutated_suite_rows) < 2:
        return None

    # Derive replay_key deterministically from parent witness hash.
    replay_key = hashlib.sha256(
        SCI_WITNESS_REPLAY_KEY_DOMAIN_V1.encode("utf-8") + _parse_prefixed_hash(parent_hash)
    ).digest()

    # Probe keys (from constants) are used to enforce "mutation" on two fixed keys.
    constants = require_constants()
    probe_keys = constants.get("family_semantics", {})
    probe_a = probe_keys.get("probe_key_a")
    probe_b = probe_keys.get("probe_key_b")
    if not isinstance(probe_a, str) or not isinstance(probe_b, str):
        return None
    probe_a_bytes = _parse_prefixed_hash(probe_a)
    probe_b_bytes = _parse_prefixed_hash(probe_b)

    frontier_threshold = _frontier_threshold(out_dir)
    frontier_sigs = _frontier_signatures(out_dir)

    for attempt in range(2048):
        salt = f"sciwit-{epoch_id}-{attempt:03d}"
        family = _base_family(
            parent_suite_row=parent_suite_row,
            mutated_suite_rows=mutated_suite_rows,
            parent_witness_hash=parent_hash,
            salt=salt,
        )

        if frontier_threshold is not None and isinstance(family.get("family_id"), str):
            if family["family_id"] >= frontier_threshold:
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

        # Ensure the epoch_key itself doesn't map back to parent.
        epoch_suite = _suite_row_for_key(family, epoch_key)
        if not isinstance(epoch_suite, dict):
            continue
        if hash_json(epoch_suite) == parent_suite_row_hash:
            continue

        # Optional novelty gate if frontier exists.
        if frontier_sigs:
            nov_ok, _dist = novelty_pass(family, frontier_sigs)
            if not nov_ok:
                continue

        out_dir.mkdir(parents=True, exist_ok=True)
        content_hash = hash_json(family).split(":", 1)[1]
        write_canon_json(out_dir / f"{content_hash}.json", family)
        return family

    return None
