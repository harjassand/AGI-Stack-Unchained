"""Compile deterministic RSI real-mode campaign families and pack."""

from __future__ import annotations

import argparse
import base64
import shutil
import os
from pathlib import Path
from typing import Any

from ..canon import canon_bytes, hash_json, load_canon_json, sha256_prefixed, write_canon_json
from ..constants import meta_identities, require_constants
from ..cmeta.work_meter import WorkMeter, set_current_meter
from ..ctime.macro import compute_macro_id, compute_rent_bits
from ..epoch import build_epoch_commit, derive_epoch_key
from ..eval_runner import eval_instance
from ..family_dsl.runtime import compute_family_id, compute_signature
from ..sr_cegar.frontier import compress_frontier
from ..sr_cegar.gates import learnability_pass, novelty_pass
from ..suites.anchor import build_anchor_pack
from ..suites.pressure import build_pressure_pack


def _hash_file(path: Path) -> str:
    if path.suffix == ".json":
        payload = load_canon_json(path)
        return sha256_prefixed(canon_bytes(payload))
    return sha256_prefixed(path.read_bytes())


def _master_key_bytes() -> bytes:
    env_key = os.environ.get("CDEL_SEALED_PRIVKEY")
    if env_key:
        return base64.b64decode(env_key)
    return b"\x01" * 32


def _policy_def(action_value: int) -> dict[str, Any]:
    return {
        "name": "policy_right",
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


def _corridor_family(corridor_len: int, salt: str) -> dict[str, Any]:
    suite_row = {
        "env": "gridworld-v1",
        "start": {"x": 0, "y": 0},
        "goal": {"x": int(corridor_len), "y": 0},
        "walls": [],
        "max_steps": int(corridor_len),
    }
    family = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": max(8, int(corridor_len)),
            "max_instance_bytes": 4096,
            "max_instantiation_gas": 10000,
            "max_shrink_gas": 10000,
        },
        "instantiator": {"op": "CONST", "value": {"suite_row": suite_row}},
        "x-salt": salt,
    }
    family["signature"] = compute_signature(family)
    family["family_id"] = compute_family_id(family)
    return family


def _pick_family(
    *,
    kind: str,
    corridor_len: int,
    prefix_set: set[str],
    existing_ids: set[str],
    frontier: list[dict[str, Any]] | None = None,
    epoch_id: str | None = None,
    epoch_commit: dict[str, Any] | None = None,
    k_t: bytes | None = None,
    max_tries: int = 10000,
) -> dict[str, Any]:
    for idx in range(max_tries):
        salt = f"{kind}-{idx:06d}"
        candidate = _corridor_family(corridor_len, salt)
        fam_hex = candidate["family_id"].split(":", 1)[1]
        if fam_hex[0] not in prefix_set:
            continue
        if candidate["family_id"] in existing_ids:
            continue
        if frontier is not None:
            ok, _ = novelty_pass(candidate, frontier)
            if not ok:
                continue
        if epoch_id is not None and epoch_commit is not None and k_t is not None:
            learn_ok = learnability_pass(
                candidate,
                epoch_id=epoch_id,
                epoch_commit=epoch_commit,
                k_t=k_t,
                diagnostics_dir=None,
            )
            if not learn_ok:
                continue
        return candidate
    raise RuntimeError(f"failed to generate {kind} family")


def _write_base_state(state_dir: Path, base_mech: dict[str, Any]) -> None:
    current = state_dir / "current"
    current.mkdir(parents=True, exist_ok=True)
    write_canon_json(current / "base_ontology.json", {"schema": "base_ontology_v1", "schema_version": 1})
    write_canon_json(current / "base_mech.json", base_mech)
    write_canon_json(
        current / "macro_active_set_v1.json",
        {
            "schema": "macro_active_set_v1",
            "schema_version": 1,
            "active_macro_ids": [],
            "ledger_head_hash": "sha256:" + "0" * 64,
        },
    )
    (current / "macro_ledger_v1.jsonl").write_text("", encoding="utf-8")
    write_canon_json(
        current / "pressure_schedule_v1.json",
        {"schema": "pressure_schedule_v1", "schema_version": 1, "p_t": 0, "history": []},
    )
    write_canon_json(
        current / "meta_patch_set_v1.json",
        {"schema": "meta_patch_set_v1", "schema_version": 1, "active_patch_ids": []},
    )


def _base_state_hashes(state_dir: Path) -> dict[str, str]:
    current = state_dir / "current"
    required = {
        "base_ontology_hash": current / "base_ontology.json",
        "base_mech_hash": current / "base_mech.json",
        "frontier_hash": current / "frontier_v1.json",
        "macro_active_set_hash": current / "macro_active_set_v1.json",
        "macro_ledger_hash": current / "macro_ledger_v1.jsonl",
        "pressure_schedule_hash": current / "pressure_schedule_v1.json",
        "meta_patch_set_hash": current / "meta_patch_set_v1.json",
    }
    hashes: dict[str, str] = {}
    for key, path in required.items():
        hashes[key] = _hash_file(path)
    return hashes


def _write_frontier(state_dir: Path, families: list[dict[str, Any]], m_frontier: int) -> dict[str, Any]:
    current = state_dir / "current"
    payload = {
        "schema": "frontier_v1",
        "schema_version": 1,
        "frontier_id": "",
        "families": [
            {"family_id": fam["family_id"], "family_hash": hash_json(fam)} for fam in families
        ],
        "M_FRONTIER": int(m_frontier),
        "signature_version": 1,
        "compression_proof_hash": "sha256:" + "0" * 64,
    }
    payload["frontier_id"] = hash_json({k: v for k, v in payload.items() if k != "frontier_id"})
    write_canon_json(current / "frontier_v1.json", payload)
    return payload


def _measure_env_steps(
    *,
    epoch_id: str,
    families: list[dict[str, Any]],
    anchor_families: list[dict[str, Any]],
    frontier_hash: str,
    base_mech: dict[str, Any],
    n_anchor: int,
    n_pressure: int,
    pressure_level: int,
) -> int:
    anchor_pack = build_anchor_pack(frontier_hash=frontier_hash, families=anchor_families, n_per_family=n_anchor)
    pressure_pack = build_pressure_pack(
        frontier_hash=frontier_hash, families=families, n_per_family=n_pressure, pressure_level=pressure_level
    )
    meter = WorkMeter(epoch_id, "sha256:" + "0" * 64)
    set_current_meter(meter)
    for pack in (anchor_pack, pressure_pack):
        for entry in pack.get("families", []):
            fam_id = entry.get("family_id")
            family = next((f for f in families if f.get("family_id") == fam_id), None)
            if family is None:
                continue
            for theta in entry.get("theta_list", []):
                eval_instance(
                    epoch_id=epoch_id,
                    family=family,
                    theta=theta,
                    epoch_commit={"commitment": "sha256:" + "0" * 64},
                    base_mech=base_mech,
                    receipt_hash="sha256:" + "0" * 64,
                    epoch_key=b"\x00" * 32,
                )
    set_current_meter(None)
    return int(meter.snapshot().get("env_steps_total", 0))


def _alpha_ok(barriers: list[int], alpha_num: int, alpha_den: int, k_accel: int) -> bool:
    if len(barriers) < 2 or k_accel <= 0:
        return False
    streak = 0
    for idx in range(len(barriers) - 1):
        prev_val = barriers[idx]
        next_val = barriers[idx + 1]
        if next_val * alpha_den <= prev_val * alpha_num:
            streak += 1
        else:
            streak = 0
        if streak >= k_accel:
            return True
    return False


def compile_campaign(
    out_dir: Path,
    state_dir: Path,
    *,
    core_len: int | None = None,
    insert_len: int | None = None,
    sac_len: int | None = None,
    skip_alpha_check: bool = False,
) -> Path:
    constants = require_constants()
    meta = meta_identities()
    m_frontier = int(constants["sr"]["m_frontier"])
    r_insert = int(constants["rsi"]["R_insertions"])
    k_accel = int(constants["rsi"]["K_accel"])
    alpha_num = int(constants["rsi"]["alpha_num"])
    alpha_den = int(constants["rsi"]["alpha_den"])
    n_anchor = int(constants["sr"]["n_anchor_per_family"])
    n_pressure = int(constants["sr"]["n_pressure_per_family"])

    base_mech = {
        "schema": "base_mech_v1",
        "schema_version": 1,
        "candidate_symbol": "policy_right",
        "baseline_symbol": "policy_right",
        "oracle_symbol": "policy_right",
        "definitions": [_policy_def(3)],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    families_dir = out_dir / "families"
    macros_dir = out_dir / "macros"
    families_dir.mkdir(parents=True, exist_ok=True)
    macros_dir.mkdir(parents=True, exist_ok=True)

    core_count = m_frontier - r_insert
    if core_count <= 0:
        raise ValueError("m_frontier must be > R_insertions")

    core_len = 10 if core_len is None else int(core_len)
    insert_len = 10 if insert_len is None else int(insert_len)
    sac_len = 32 if sac_len is None else int(sac_len)

    attempt = 0
    while True:
        attempt += 1
        existing_ids: set[str] = set()
        core_families: list[dict[str, Any]] = []
        sac_families: list[dict[str, Any]] = []
        insertion_families: list[dict[str, Any]] = []

        # Generate core families with low hash prefix
        for idx in range(core_count):
            fam = _pick_family(
                kind=f"core{idx}",
                corridor_len=core_len,
                prefix_set={"0", "1"},
                existing_ids=existing_ids,
            )
            existing_ids.add(fam["family_id"])
            core_families.append(fam)

        # Generate sacrificial families with high hash prefix
        for idx in range(r_insert):
            fam = _pick_family(
                kind=f"sac{idx}",
                corridor_len=sac_len,
                prefix_set={"f"},
                existing_ids=existing_ids,
            )
            existing_ids.add(fam["family_id"])
            sac_families.append(fam)

        # Prepare temp state for gating and hashing
        if state_dir.exists():
            shutil.rmtree(state_dir)
        _write_base_state(state_dir, base_mech)

        frontier = core_families + sac_families
        removed_sacrificial: set[str] = set()
        barriers: list[int] = []
        ok_sequence = True

        # Generate insertion families sequentially
        for i in range(r_insert):
            insertion_epoch = 3 + i * 2
            frontier_payload = _write_frontier(state_dir, frontier, m_frontier)
            base_state_hashes = _base_state_hashes(state_dir)
            master_key = _master_key_bytes()
            k_t = derive_epoch_key(master_key, f"epoch_{insertion_epoch}", base_state_hashes, frontier_payload["frontier_id"])
            epoch_commit = build_epoch_commit(
                epoch_id=f"epoch_{insertion_epoch}",
                base_state_hashes=base_state_hashes,
                frontier_hash=frontier_payload["frontier_id"],
                master_key=master_key,
                created_unix_ms=0,
            )

            candidate = _pick_family(
                kind=f"ins{i}",
                corridor_len=insert_len,
                prefix_set={"0"},
                existing_ids=existing_ids,
                frontier=frontier,
                epoch_id=f"epoch_{insertion_epoch}",
                epoch_commit=epoch_commit,
                k_t=k_t,
            )
            existing_ids.add(candidate["family_id"])
            insertion_families.append(candidate)

            selected, _report = compress_frontier(frontier + [candidate], [], m_frontier)
            selected_ids = {fam.get("family_id") for fam in selected}
            if candidate["family_id"] not in selected_ids:
                ok_sequence = False
                break
            removed = [fam for fam in frontier if fam.get("family_id") not in selected_ids]
            if len(removed) != 1:
                ok_sequence = False
                break
            removed_id = removed[0].get("family_id")
            if removed_id not in {fam["family_id"] for fam in sac_families}:
                ok_sequence = False
                break
            if removed_id in removed_sacrificial:
                ok_sequence = False
                break
            removed_sacrificial.add(removed_id)
            frontier = selected

            # Measure barrier scalar for recovery epoch (next epoch)
            recovery_epoch = insertion_epoch + 1
            frontier_payload = _write_frontier(state_dir, frontier, m_frontier)
            env_steps = _measure_env_steps(
                epoch_id=f"epoch_{recovery_epoch}",
                families=frontier,
                anchor_families=core_families,
                frontier_hash=frontier_payload["frontier_id"],
                base_mech=base_mech,
                n_anchor=n_anchor,
                n_pressure=n_pressure,
                pressure_level=0,
            )
            barriers.append(env_steps)

        if ok_sequence and (skip_alpha_check or _alpha_ok(barriers, alpha_num, alpha_den, k_accel)):
            break
        if skip_alpha_check:
            raise RuntimeError("unable to satisfy compression sequence with fixed lengths")
        sac_len += 4
        if sac_len > 64:
            raise RuntimeError("unable to satisfy alpha constraints")

    # Emit families
    def _emit_family(fam: dict[str, Any], role: str, corridor_len: int) -> dict[str, Any]:
        fam_hash = hash_json(fam)
        rel_path = f"families/{fam_hash.split(':', 1)[1]}.json"
        write_canon_json(out_dir / rel_path, fam)
        return {
            "family_id": fam.get("family_id"),
            "family_hash": fam_hash,
            "path": rel_path,
            "corridor_len": corridor_len,
            "role": role,
        }

    manifest = {
        "schema": "family_manifest_v1",
        "schema_version": 1,
        "core_families": [_emit_family(fam, "core", core_len) for fam in core_families],
        "sacrificial_families": [_emit_family(fam, "sacrificial", sac_len) for fam in sac_families],
        "insertion_families": [_emit_family(fam, "insertion", insert_len) for fam in insertion_families],
    }
    write_canon_json(out_dir / "family_manifest_v1.json", manifest)

    # Macro proposal
    macro_def = {
        "schema": "macro_def_v1",
        "schema_version": 1,
        "macro_id": "",
        "body": [
            {"name": "MOVE", "args": {"dir": 3}},
            {"name": "MOVE", "args": {"dir": 3}},
        ],
        "guard": None,
        "admission_epoch": 0,
        "rent_bits": 0,
    }
    macro_def["rent_bits"] = compute_rent_bits(macro_def)
    macro_def["macro_id"] = compute_macro_id(macro_def)
    macro_path = macros_dir / f"{macro_def['macro_id'].split(':', 1)[1]}.json"
    write_canon_json(macro_path, macro_def)

    # Campaign pack
    insertion_epochs = [3 + 2 * i for i in range(r_insert)]
    macro_epochs = [4]
    family_by_epoch = {
        str(epoch): [manifest["insertion_families"][idx]["path"]]
        for idx, epoch in enumerate(insertion_epochs)
    }
    macro_by_epoch = {str(macro_epochs[0]): [f"macros/{macro_path.name}"]}
    expected_frontier = {str(epoch): {"min_insertions": 1} for epoch in insertion_epochs}

    pack = {
        "schema": "rsi_real_campaign_pack_v1",
        "schema_version": 1,
        "N_epochs": 2 + 2 * r_insert,
        "insertion_epochs": insertion_epochs,
        "macro_proposal_epochs": macro_epochs,
        "family_proposals_by_epoch": family_by_epoch,
        "macro_proposals_by_epoch": macro_by_epoch,
        "expected_frontier_events": expected_frontier,
        "x-family_manifest": "family_manifest_v1.json",
        "x-meta": meta,
    }
    write_canon_json(out_dir / "rsi_real_campaign_pack_v1.json", pack)

    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--state_dir", required=False)
    parser.add_argument("--core_len", type=int, required=False)
    parser.add_argument("--insert_len", type=int, required=False)
    parser.add_argument("--sac_len", type=int, required=False)
    parser.add_argument("--skip_alpha_check", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    state_dir = Path(args.state_dir) if args.state_dir else out_dir / "_compile_state"
    compile_campaign(
        out_dir,
        state_dir,
        core_len=args.core_len,
        insert_len=args.insert_len,
        sac_len=args.sac_len,
        skip_alpha_check=args.skip_alpha_check,
    )


if __name__ == "__main__":
    main()
