"""Deterministic multi-epoch RSI campaign runner (real or synthetic)."""

from __future__ import annotations

import argparse
import json
import base64
import shutil
from pathlib import Path
from typing import Any

from .canon import canon_bytes, hash_json, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line
from .constants import meta_identities, require_constants
from .epoch import _load_state_hashes, derive_epoch_key, run_epoch
from .ctime.macro import load_macro_defs
from .family_dsl.runtime import compute_family_id, compute_signature
from .proposals.inbox import (
    INBOX_FAMILY_DIR,
    INBOX_MACRO_DIR,
    INBOX_MECH_PATCH_DIR,
    INBOX_META_PATCH_DIR,
    INBOX_ONTOLOGY_V2_DIR,
)
from .proposers.family_generalizer_v1 import propose_next_family
from .proposers.macro_miner_v1 import mine_macros
from .proposers.meta_patch_searcher_v1 import propose_meta_patch
from .proposers.policy_synthesizer_v1 import synthesize_policy_patch
from .witness_family_generalizer_v2 import propose_witness_family_v2
from .suites.anchor import build_anchor_pack
from .rsi_tracker import update_rsi_tracker
from .ontology_v2.eval import evaluate_epoch as evaluate_ontology_v2, maybe_evict as maybe_evict_ontology_v2
from .rsi_tracker import build_rsi_ontology_receipt_v2


def _hash_file(path: Path) -> str:
    if path.suffix == ".json":
        payload = load_canon_json(path)
        return sha256_prefixed(canon_bytes(payload))
    return sha256_prefixed(path.read_bytes())


def _family_id(idx: int) -> str:
    return hash_json({"family_index": idx})


def _family_hash(fid: str) -> str:
    return hash_json({"family_id": fid})


def _frontier_payload(families: list[dict[str, Any]], m_frontier: int, compression_hash: str) -> dict[str, Any]:
    payload = {
        "schema": "frontier_v1",
        "schema_version": 1,
        "frontier_id": "",
        "families": families,
        "M_FRONTIER": m_frontier,
        "signature_version": 1,
        "compression_proof_hash": compression_hash,
    }
    payload["frontier_id"] = hash_json({k: v for k, v in payload.items() if k != "frontier_id"})
    return payload


def _anchor_pack(frontier_hash: str, family_id: str) -> dict[str, Any]:
    payload = {
        "schema": "anchor_pack_v1",
        "schema_version": 1,
        "pack_id": "",
        "frontier_hash": frontier_hash,
        "families": [
            {
                "family_id": family_id,
                "theta_list": [{}],
            }
        ],
    }
    payload["pack_id"] = hash_json(payload)
    return payload


def _work_meter(epoch_id: str, env_steps: int, meta: dict[str, str]) -> dict[str, Any]:
    payload = {
        "schema": "work_meter_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "env_steps_total": env_steps,
        "oracle_calls_total": 0,
        "verifier_gas_total": 0,
        "bytes_hashed_total": 0,
        "candidates_fully_evaluated": 0,
        "short_circuits_total": 0,
        "meter_version": 1,
        "collection_rules_hash": "sha256:" + "0" * 64,
    }
    payload["x-meta"] = meta
    return payload


def _selection(epoch_id: str, selected_candidate_id: str | None, meta: dict[str, str]) -> dict[str, Any]:
    payload = {
        "schema": "selection_v1_5r",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "selected_candidate_id": selected_candidate_id,
    }
    payload["x-meta"] = meta
    return payload


def _worstcase(epoch_id: str, worst_anchor: int, worst_pressure: int, worst_heldout: int, meta: dict[str, str]) -> dict[str, Any]:
    payload = {
        "schema": "worstcase_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "worst_anchor": worst_anchor,
        "worst_pressure": worst_pressure,
        "worst_heldout": worst_heldout,
    }
    payload["x-meta"] = meta
    return payload


def _rho_report(epoch_id: str, rho_num: int, rho_den: int, macro_active_set_hash: str, trace_hash: str, meta: dict[str, str]) -> dict[str, Any]:
    payload = {
        "schema": "rho_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "encoder_rule_id": "greedy-longest-match-v1",
        "macro_active_set_hash": macro_active_set_hash,
        "trace_corpus_hashes": [trace_hash],
        "rho_num": rho_num,
        "rho_den": rho_den,
        "rho_value": f"{rho_num}/{rho_den}",
        "rho_reason_codes": [],
    }
    payload["report_id"] = hash_json(payload)
    payload["x-meta"] = meta
    return payload


def default_campaign(constants: dict[str, Any]) -> dict[str, Any]:
    r_insert = int(constants.get("rsi", {}).get("R_insertions", 5))
    return {
        "schema": "rsi_campaign_v1",
        "schema_version": 1,
        "seed": 7,
        "N_epochs": r_insert * 2 + 1,
        "frontier_insertions": [
            {"epoch": 1 + idx * 2, "family_bundle_ref": f"family_bundle_{idx+1}"}
            for idx in range(r_insert)
        ],
        "recovery_candidates": [
            {"after_insertion_id": idx, "candidate_bundle_ref": f"candidate_bundle_{idx+1}"}
            for idx in range(r_insert)
        ],
        "expected_ignition_insertion_index": r_insert - 1,
    }


def _base_policy_def(action_value: int = 3, *, name: str = "policy_right") -> dict[str, Any]:
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


def _base_family(signature_salt: str | None = None) -> dict[str, Any]:
    inst_value = {
        "suite_row": {
            "env": "gridworld-v1",
            "start": {"x": 0, "y": 0},
            "goal": {"x": 0, "y": 1},
            "walls": [],
            "max_steps": 2,
        }
    }
    if signature_salt is not None:
        inst_value["signature_salt"] = signature_salt
    family = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": 1,
            "max_instance_bytes": 64,
            "max_instantiation_gas": 32,
            "max_shrink_gas": 32,
        },
        "instantiator": {"op": "CONST", "value": inst_value},
    }
    family["signature"] = compute_signature(family)
    family["family_id"] = compute_family_id(family)
    return family


def _write_base_state(
    state_dir: Path,
    constants: dict[str, Any],
    *,
    families: list[dict[str, Any]] | None = None,
    policy_action: int = 3,
    anchor_families: list[dict[str, Any]] | None = None,
) -> tuple[Path, Path, list[dict[str, Any]]]:
    current_dir = state_dir / "current"
    current_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "epochs").mkdir(parents=True, exist_ok=True)

    base_ontology = current_dir / "base_ontology.json"
    base_mech = current_dir / "base_mech.json"
    write_canon_json(base_ontology, {"schema": "base_ontology_v1", "schema_version": 1})
    base_mech_payload = {
        "schema": "base_mech_v1",
        "schema_version": 1,
        "candidate_symbol": "policy_right",
        "baseline_symbol": "policy_right",
        "oracle_symbol": "policy_right",
        "definitions": [_base_policy_def(policy_action)],
    }
    write_canon_json(base_mech, base_mech_payload)

    write_canon_json(
        current_dir / "macro_active_set_v1.json",
        {
            "schema": "macro_active_set_v1",
            "schema_version": 1,
            "active_macro_ids": [],
            "ledger_head_hash": "sha256:" + "0" * 64,
        },
    )
    (current_dir / "macro_ledger_v1.jsonl").write_text("", encoding="utf-8")
    write_canon_json(
        current_dir / "pressure_schedule_v1.json",
        {"schema": "pressure_schedule_v1", "schema_version": 1, "p_t": 0, "history": []},
    )
    write_canon_json(
        current_dir / "meta_patch_set_v1.json",
        {"schema": "meta_patch_set_v1", "schema_version": 1, "active_patch_ids": []},
    )

    write_canon_json(
        current_dir / "mech_patch_active_set_v1.json",
        {
            "schema": "mech_patch_active_set_v1",
            "schema_version": 1,
            "active_patch_ids": [],
            "ledger_head_hash": "sha256:" + "0" * 64,
        },
    )

    ontology_root = current_dir / "ontology"
    (ontology_root / "defs").mkdir(parents=True, exist_ok=True)
    (ontology_root / "reports").mkdir(parents=True, exist_ok=True)
    (ontology_root / "receipts").mkdir(parents=True, exist_ok=True)
    (ontology_root / "snapshots").mkdir(parents=True, exist_ok=True)
    meta = meta_identities()
    write_canon_json(
        ontology_root / "ontology_active_set_v2.json",
        {
            "schema": "ontology_active_set_v2",
            "schema_version": 2,
            "active_ontology_id": None,
            "active_snapshot_hash": None,
            "activation_epoch": None,
            "x-meta": meta,
        },
    )
    (ontology_root / "ontology_ledger_v2.jsonl").write_text("", encoding="utf-8")
    write_canon_json(
        ontology_root / "ontology_state_v2.json",
        {"schema": "ontology_state_v2", "schema_version": 2, "bad_epochs": 0},
    )

    if families is None:
        families = [_base_family()]

    families_dir = current_dir / "families"
    families_dir.mkdir(parents=True, exist_ok=True)
    frontier_families: list[dict[str, Any]] = []
    for fam in families:
        fam_hash = hash_json(fam)
        write_canon_json(families_dir / f"{fam_hash.split(':', 1)[1]}.json", fam)
        frontier_families.append({"family_id": fam["family_id"], "family_hash": fam_hash})

    frontier_payload = _frontier_payload(
        frontier_families,
        int(constants.get("sr", {}).get("m_frontier", 16)),
        "sha256:" + "0" * 64,
    )
    write_canon_json(current_dir / "frontier_v1.json", frontier_payload)
    required_name = _required_policy_name(_hash_file(current_dir / "frontier_v1.json"))
    if required_name != base_mech_payload.get("candidate_symbol"):
        base_mech_payload["candidate_symbol"] = required_name
        base_mech_payload["baseline_symbol"] = required_name
        base_mech_payload["oracle_symbol"] = required_name
        base_mech_payload["definitions"] = [_base_policy_def(policy_action, name=required_name)]
        write_canon_json(base_mech, base_mech_payload)

    n_anchor = int(constants.get("sr", {}).get("n_anchor_per_family", 1))
    if anchor_families is None:
        anchor_families = families
    anchor_pack = build_anchor_pack(
        frontier_hash=_hash_file(current_dir / "frontier_v1.json"),
        families=anchor_families,
        n_per_family=n_anchor,
    )
    write_canon_json(current_dir / "anchor_pack_v1.json", anchor_pack)

    return base_ontology, base_mech, families


def _master_key_from_env() -> str:
    from os import getenv

    env_key = getenv("CDEL_SEALED_PRIVKEY")
    if env_key:
        return env_key
    return base64.b64encode(b"\x01" * 32).decode("utf-8")


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = load_canon_json(manifest_path)
    if manifest.get("schema") != "family_manifest_v1":
        raise ValueError("family manifest schema mismatch")
    return manifest


def _reset_inbox(state_dir: Path) -> None:
    for rel in (
        INBOX_FAMILY_DIR,
        INBOX_MACRO_DIR,
        INBOX_MECH_PATCH_DIR,
        INBOX_META_PATCH_DIR,
        INBOX_ONTOLOGY_V2_DIR,
    ):
        inbox = state_dir / rel
        if inbox.exists():
            shutil.rmtree(inbox)
        inbox.mkdir(parents=True, exist_ok=True)


def _reset_state_dir(state_dir: Path) -> None:
    for rel in ("current", "epochs"):
        path = state_dir / rel
        if path.exists():
            shutil.rmtree(path)


def _copy_proposals(paths: list[str], pack_dir: Path, dest_dir: Path) -> None:
    for entry in paths:
        src = Path(entry)
        if not src.is_absolute():
            src = pack_dir / entry
        if not src.exists():
            raise FileNotFoundError(f"proposal not found: {entry}")
        payload = load_canon_json(src)
        content_hash = hash_json(payload).split(":", 1)[1]
        out_path = dest_dir / f"{content_hash}.json"
        write_canon_json(out_path, payload)


def _copy_ontology_inbox(src_root: Path, dest_root: Path) -> None:
    if not src_root.exists():
        raise FileNotFoundError(f"ontology inbox not found: {src_root}")
    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)
    for path in sorted(src_root.rglob("*.json")):
        rel = path.relative_to(src_root)
        target = dest_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = load_canon_json(path)
        write_canon_json(target, payload)


def run_campaign_synthetic(out_dir: Path, campaign: dict[str, Any], strict_rsi: bool = True) -> Path:
    constants = require_constants()
    meta = meta_identities()
    out_dir.mkdir(parents=True, exist_ok=True)

    state_dir = out_dir
    current_dir = state_dir / "current"
    epochs_dir = state_dir / "epochs"
    current_dir.mkdir(parents=True, exist_ok=True)
    epochs_dir.mkdir(parents=True, exist_ok=True)

    # Static state artifacts
    write_canon_json(current_dir / "base_ontology.json", {"schema": "base_ontology_v1", "schema_version": 1})
    write_canon_json(
        current_dir / "base_mech.json",
        {
            "schema": "base_mech_v1",
            "schema_version": 1,
            "candidate_symbol": "baseline",
            "baseline_symbol": "baseline",
            "oracle_symbol": "baseline",
            "definitions": [],
        },
    )
    write_canon_json(
        current_dir / "macro_active_set_v1.json",
        {"schema": "macro_active_set_v1", "schema_version": 1, "active_macro_ids": [], "ledger_head_hash": "sha256:" + "0" * 64},
    )
    (current_dir / "macro_ledger_v1.jsonl").write_text("", encoding="utf-8")
    write_canon_json(
        current_dir / "pressure_schedule_v1.json",
        {"schema": "pressure_schedule_v1", "schema_version": 1, "p_t": 0, "history": []},
    )
    write_canon_json(
        current_dir / "meta_patch_set_v1.json",
        {"schema": "meta_patch_set_v1", "schema_version": 1, "active_patch_ids": []},
    )

    # Initial frontier and anchor pack
    m_frontier = int(constants.get("sr", {}).get("m_frontier", 16))
    initial_family_id = _family_id(0)
    families = [{"family_id": initial_family_id, "family_hash": _family_hash(initial_family_id)}]
    frontier_payload = _frontier_payload(families, m_frontier, "sha256:" + "0" * 64)
    write_canon_json(current_dir / "frontier_v1.json", frontier_payload)
    anchor_pack = _anchor_pack(_hash_file(current_dir / "frontier_v1.json"), initial_family_id)
    write_canon_json(current_dir / "anchor_pack_v1.json", anchor_pack)

    # State ledger init
    state_ledger_path = current_dir / "state_ledger_v1.jsonl"
    state_ledger_path.write_text("", encoding="utf-8")
    prev_state_hash = "sha256:" + "0" * 64

    # Barrier ledger init
    barrier_ledger_path = current_dir / "barrier_ledger_v1.jsonl"
    barrier_ledger_path.write_text("", encoding="utf-8")

    # Tracker state
    rsi_state_path = current_dir / "rsi_tracker_state_v1.json"
    if rsi_state_path.exists():
        rsi_state_path.unlink()

    insertion_epochs = {entry["epoch"]: idx for idx, entry in enumerate(campaign.get("frontier_insertions", []))}

    rho_values = []
    for idx in range(int(campaign.get("N_epochs", 1))):
        rho_values.append((idx // 2 + 1, 10))
    rho_override = {
        int(item.get("epoch")): (int(item.get("rho_num", 0)), int(item.get("rho_den", 1)))
        for item in campaign.get("rho_series", [])
        if isinstance(item, dict) and item.get("epoch") is not None
    }

    barrier_values = campaign.get("barrier_env_steps") or [100 - 10 * idx for idx in range(len(campaign.get("frontier_insertions", [])))]
    worstcase_override = {
        int(epoch): entry
        for epoch, entry in (campaign.get("worstcase_by_epoch") or {}).items()
        if isinstance(entry, dict)
    }

    for epoch_idx in range(1, int(campaign.get("N_epochs", 1)) + 1):
        epoch_id = f"epoch_{epoch_idx}"
        epoch_dir = epochs_dir / epoch_id
        diagnostics_dir = epoch_dir / "diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        (epoch_dir / "receipts").mkdir(parents=True, exist_ok=True)

        frontier_event = None
        if epoch_idx in insertion_epochs:
            insertion_index = insertion_epochs[epoch_idx]
            prev_frontier_hash = _hash_file(current_dir / "frontier_v1.json")
            new_family_id = _family_id(insertion_index + 1)
            families.append({"family_id": new_family_id, "family_hash": _family_hash(new_family_id)})
            frontier_payload = _frontier_payload(families, m_frontier, "sha256:" + "0" * 64)
            write_canon_json(current_dir / "frontier_v1.json", frontier_payload)
            report_payload = {
                "schema": "frontier_update_report_v1",
                "schema_version": 1,
                "admitted_family_id": new_family_id,
            }
            write_canon_json(diagnostics_dir / "frontier_update_report_v1.json", report_payload)
            frontier_event = {
                "event_type": "FRONTIER_ACTIVATE_V1",
                "schema_version": 1,
                "prev_frontier_hash": prev_frontier_hash,
                "new_frontier_hash": _hash_file(current_dir / "frontier_v1.json"),
                "inserted_family_id": new_family_id,
                "compression_detail_hash": _hash_file(diagnostics_dir / "frontier_update_report_v1.json"),
                "reason_code": "FRONTIER_INSERTION",
            }

        pointer_hashes = {
            "frontier_hash": _hash_file(current_dir / "frontier_v1.json"),
            "macro_active_set_hash": _hash_file(current_dir / "macro_active_set_v1.json"),
            "pressure_schedule_hash": _hash_file(current_dir / "pressure_schedule_v1.json"),
            "meta_patch_set_hash": _hash_file(current_dir / "meta_patch_set_v1.json"),
        }
        selected_candidate_id = f"sha256:{epoch_idx:064x}"
        state_entry = {
            "schema": "state_ledger_event_v1",
            "schema_version": 1,
            "epoch_id": epoch_id,
            "selected_candidate_id": selected_candidate_id,
            "pointer_hashes": pointer_hashes,
            "prev_ledger_hash": prev_state_hash,
        }
        if frontier_event is not None:
            state_entry["frontier_event"] = frontier_event
        state_entry["line_hash"] = hash_json({k: v for k, v in state_entry.items() if k != "line_hash"})
        write_jsonl_line(state_ledger_path, state_entry)
        prev_state_hash = state_entry["line_hash"]

        state_head_payload = {
            "schema": "state_ledger_head_v1",
            "schema_version": 1,
            "ledger_head_hash": prev_state_hash,
            "line_count": epoch_idx,
        }
        write_canon_json(current_dir / "state_ledger_head_v1.json", state_head_payload)
        write_canon_json(diagnostics_dir / "state_ledger_head_v1.json", state_head_payload)

        # Reports
        worst_anchor = 1
        worst_pressure = 1
        worst_heldout = 1
        if epoch_idx in worstcase_override:
            override = worstcase_override[epoch_idx]
            worst_anchor = int(override.get("worst_anchor", worst_anchor))
            worst_pressure = int(override.get("worst_pressure", worst_pressure))
            worst_heldout = int(override.get("worst_heldout", worst_heldout))
        worstcase_report = _worstcase(epoch_id, worst_anchor, worst_pressure, worst_heldout, meta)
        write_canon_json(diagnostics_dir / "worstcase_report_v1.json", worstcase_report)

        selection = _selection(epoch_id, selected_candidate_id, meta)
        write_canon_json(epoch_dir / "selection.json", selection)

        env_steps = 0
        if (epoch_idx - 1) in insertion_epochs:
            insertion_index = insertion_epochs.get(epoch_idx - 1)
            if insertion_index is not None and insertion_index < len(barrier_values):
                env_steps = barrier_values[insertion_index]
        work_meter = _work_meter(epoch_id, env_steps, meta)
        write_canon_json(epoch_dir / "work_meter_v1.json", work_meter)

        rho_num, rho_den = rho_values[epoch_idx - 1]
        if epoch_idx in rho_override:
            rho_num, rho_den = rho_override[epoch_idx]
        rho_report = _rho_report(
            epoch_id,
            rho_num,
            rho_den,
            _hash_file(current_dir / "macro_active_set_v1.json"),
            "sha256:" + "1" * 64,
            meta,
        )
        write_canon_json(diagnostics_dir / "rho_report_v1.json", rho_report)

        # Anchor pack copy
        write_canon_json(diagnostics_dir / "anchor_pack_v1.json", anchor_pack)

        # RSI tracker update
        prior_state = None
        if rsi_state_path.exists():
            prior_state = load_canon_json(rsi_state_path)
        rsi_epoch_artifacts = {
            "epoch_id": epoch_id,
            "meta": meta,
            "anchor_pack_hash": _hash_file(diagnostics_dir / "anchor_pack_v1.json"),
            "worstcase_report": worstcase_report,
            "worstcase_report_hash": _hash_file(diagnostics_dir / "worstcase_report_v1.json"),
            "selection": selection,
            "selection_hash": _hash_file(epoch_dir / "selection.json"),
            "work_meter": work_meter,
            "work_meter_hash": _hash_file(epoch_dir / "work_meter_v1.json"),
            "rho_report": rho_report,
            "rho_report_hash": _hash_file(diagnostics_dir / "rho_report_v1.json"),
            "state_ledger_head": state_head_payload,
            "state_ledger_head_hash": _hash_file(diagnostics_dir / "state_ledger_head_v1.json"),
            "state_ledger_event": state_entry,
        }
        rsi_result = update_rsi_tracker(
            constants=constants,
            epoch_artifacts=rsi_epoch_artifacts,
            prior_state=prior_state,
            strict=strict_rsi,
        )
        write_canon_json(rsi_state_path, rsi_result.state)
        write_canon_json(diagnostics_dir / "rsi_window_report_v1.json", rsi_result.window_report)
        if rsi_result.ignition_receipt is not None:
            write_canon_json(diagnostics_dir / "rsi_ignition_receipt_v1.json", rsi_result.ignition_receipt)
        if rsi_result.barrier_entry is not None:
            write_jsonl_line(barrier_ledger_path, rsi_result.barrier_entry)
        (diagnostics_dir / "barrier_ledger_v1.jsonl").write_text(
            barrier_ledger_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    return out_dir


def run_campaign(
    out_dir: Path,
    campaign: dict[str, Any],
    strict_rsi: bool = True,
    strict_integrity: bool = False,
    strict_portfolio: bool = False,
    strict_transfer: bool = False,
    enable_macro_miner: bool = False,
    enable_policy_synthesizer: bool = False,
    enable_family_generalizer: bool = False,
    enable_witness_emission: bool = False,
    enable_witness_family_generalizer_v2: bool = False,
    enable_mech_patch_searcher: bool = False,
    enable_meta_patch_searcher: bool = False,
    *,
    master_key_b64: str | None = None,
    mode: str = "real",
    campaign_pack: dict[str, Any] | None = None,
    pack_path: Path | None = None,
) -> Path:
    if mode == "synthetic":
        return run_campaign_synthetic(out_dir, campaign, strict_rsi=strict_rsi)

    constants = require_constants()
    meta = meta_identities()
    if campaign_pack is None:
        raise ValueError("campaign_pack required for real mode")
    if campaign_pack.get("schema") not in {"rsi_real_campaign_pack_v1", "rsi_real_campaign_pack_v2"}:
        raise ValueError("campaign_pack schema mismatch")
    pack_meta = campaign_pack.get("x-meta") or {}
    for key in ("META_HASH", "KERNEL_HASH", "constants_hash", "toolchain_root"):
        if pack_meta.get(key) != meta.get(key):
            raise ValueError("campaign_pack x-meta mismatch")

    pack_dir = pack_path.parent if pack_path is not None else Path.cwd()
    manifest_ref = campaign_pack.get("x-family_manifest") or "family_manifest_v1.json"
    manifest_path = Path(manifest_ref)
    if not manifest_path.is_absolute():
        manifest_path = pack_dir / manifest_path
    manifest = _load_manifest(manifest_path)

    def _load_family_entries(key: str) -> list[dict[str, Any]]:
        entries = manifest.get(key, [])
        if not isinstance(entries, list):
            raise ValueError(f"manifest {key} must be list")
        families: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("manifest entry must be object")
            path_ref = entry.get("path")
            if not isinstance(path_ref, str):
                raise ValueError("manifest entry missing path")
            path = Path(path_ref)
            if not path.is_absolute():
                path = manifest_path.parent / path
            family = load_canon_json(path)
            fam_hash = hash_json(family)
            if entry.get("family_hash") and entry.get("family_hash") != fam_hash:
                raise ValueError("manifest family_hash mismatch")
            if entry.get("family_id") and entry.get("family_id") != family.get("family_id"):
                raise ValueError("manifest family_id mismatch")
            families.append(family)
        return families

    core_families = _load_family_entries("core_families")
    sacrificial_families = _load_family_entries("sacrificial_families")
    seed_families = core_families + sacrificial_families
    base_policy_action = campaign_pack.get("base_policy_action")
    if base_policy_action is None:
        base_policy_action = 3
    base_policy_action = int(base_policy_action)
    if out_dir.exists():
        _reset_state_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_dir = out_dir
    current_dir = state_dir / "current"
    epochs_dir = state_dir / "epochs"
    current_dir.mkdir(parents=True, exist_ok=True)
    epochs_dir.mkdir(parents=True, exist_ok=True)

    base_ontology, base_mech, _base = _write_base_state(
        state_dir,
        constants,
        families=seed_families,
        anchor_families=core_families,
        policy_action=base_policy_action,
    )
    if master_key_b64 is None:
        master_key_b64 = _master_key_from_env()
    master_key_bytes = base64.b64decode(master_key_b64)

    n_epochs = int(campaign_pack.get("N_epochs", 1))
    family_by_epoch = campaign_pack.get("family_proposals_by_epoch", {})
    macro_by_epoch = campaign_pack.get("macro_proposals_by_epoch", {})
    mech_patch_by_epoch = campaign_pack.get("mech_patch_proposals_by_epoch", {})
    expected_frontier = campaign_pack.get("expected_frontier_events", {})
    insertion_epochs = campaign_pack.get("insertion_epochs", [])
    if not isinstance(insertion_epochs, list):
        insertion_epochs = []
    insertion_epoch_set: set[int] = set()
    for entry in insertion_epochs:
        if isinstance(entry, int):
            insertion_epoch_set.add(entry)
        elif isinstance(entry, str) and entry.isdigit():
            insertion_epoch_set.add(int(entry))
    first_insertion_epoch = min(insertion_epoch_set) if insertion_epoch_set else None
    enable_macro_miner = bool(enable_macro_miner or campaign_pack.get("enable_macro_miner", False))
    enable_policy_synthesizer = bool(
        enable_policy_synthesizer or campaign_pack.get("enable_policy_synthesizer", False)
    )
    enable_family_generalizer = bool(
        enable_family_generalizer or campaign_pack.get("enable_family_generalizer", False)
    )
    enable_witness_emission = bool(
        enable_witness_emission or campaign_pack.get("enable_witness_emission", False)
    )
    enable_witness_family_generalizer_v2 = bool(
        enable_witness_family_generalizer_v2 or campaign_pack.get("enable_witness_family_generalizer_v2", False)
    )
    enable_mech_patch_searcher = bool(
        enable_mech_patch_searcher or campaign_pack.get("enable_mech_patch_searcher", False)
    )
    if enable_mech_patch_searcher:
        enable_policy_synthesizer = True
    macro_miner_top_k = int(campaign_pack.get("macro_miner_top_k", 0) or 0)
    macro_miner_trace_window = int(campaign_pack.get("macro_miner_trace_window", 1) or 1)
    macro_epochs = campaign_pack.get("macro_proposal_epochs")
    policy_synth_epochs = campaign_pack.get("policy_synthesizer_epochs")
    mech_patch_epochs = campaign_pack.get("mech_patch_proposal_epochs")
    meta_patch_epochs = campaign_pack.get("meta_patch_proposal_epochs")
    enable_meta_patch_searcher = bool(
        enable_meta_patch_searcher or campaign_pack.get("enable_meta_patch_searcher", False)
    )

    ontology_cfg = campaign_pack.get("ontology_v2") if isinstance(campaign_pack, dict) else None
    ontology_enabled = bool(ontology_cfg.get("enabled", False)) if isinstance(ontology_cfg, dict) else False
    ontology_eval_every = int(constants.get("ontology", {}).get("ONTO_EVAL_EVERY_N_EPOCHS", 0) or 0)
    ontology_window = int(constants.get("ontology", {}).get("ONTO_WINDOW_EPOCHS", 0) or 0)
    ontology_inbox_rel = "proposals/ontology_v2"
    if isinstance(ontology_cfg, dict):
        if ontology_cfg.get("eval_every_n_epochs") not in (None, ontology_eval_every):
            raise ValueError("ontology_v2 eval_every_n_epochs mismatch with constants")
        if ontology_cfg.get("window_epochs") not in (None, ontology_window):
            raise ValueError("ontology_v2 window_epochs mismatch with constants")
        inbox_rel = ontology_cfg.get("proposal_inbox")
        if isinstance(inbox_rel, str) and inbox_rel:
            ontology_inbox_rel = inbox_rel

    benchmark_path = campaign_pack.get("meta_benchmark_pack_path")
    if isinstance(benchmark_path, str) and benchmark_path:
        src_path = Path(benchmark_path)
        if not src_path.is_absolute():
            src_path = pack_dir / src_path
        if not src_path.exists():
            raise FileNotFoundError(f"meta_benchmark_pack_path not found: {benchmark_path}")
        bench_payload = load_canon_json(src_path)
        bench_out = state_dir / "current" / "meta_benchmark_pack_v1.json"
        write_canon_json(bench_out, bench_payload)
        for case in bench_payload.get("cases", []) if isinstance(bench_payload, dict) else []:
            if not isinstance(case, dict):
                continue
            for key in ("state_snapshot_path", "inbox_snapshot_path"):
                rel = case.get(key)
                if not isinstance(rel, str) or not rel:
                    continue
                src_case = (src_path.parent / rel) if not Path(rel).is_absolute() else Path(rel)
                dest_case = state_dir / "current" / rel
                if src_case.exists():
                    if dest_case.exists():
                        shutil.rmtree(dest_case)
                    shutil.copytree(src_case, dest_case)

    mech_benchmark_path = campaign_pack.get("mech_benchmark_pack_path") or campaign_pack.get(
        "mech_benchmark_pack_v1_path"
    )
    if isinstance(mech_benchmark_path, str) and mech_benchmark_path:
        src_path = Path(mech_benchmark_path)
        if not src_path.is_absolute():
            src_path = pack_dir / src_path
        if not src_path.exists():
            raise FileNotFoundError(f"mech_benchmark_pack_path not found: {mech_benchmark_path}")
        bench_payload = load_canon_json(src_path)
        bench_out = state_dir / "current" / "mech_benchmark_pack_v1.json"
        write_canon_json(bench_out, bench_payload)
        for case in bench_payload.get("cases", []) if isinstance(bench_payload, dict) else []:
            if not isinstance(case, dict):
                continue
            inst_rel = case.get("instance_pack_path")
            if not isinstance(inst_rel, str) or not inst_rel:
                continue
            src_case = (src_path.parent / inst_rel) if not Path(inst_rel).is_absolute() else Path(inst_rel)
            dest_case = state_dir / "current" / inst_rel
            dest_case.parent.mkdir(parents=True, exist_ok=True)
            if src_case.exists():
                shutil.copy2(src_case, dest_case)

    def _preferred_envs(epoch_name: str) -> list[str] | None:
        if not isinstance(epoch_name, str):
            return None
        tail = epoch_name.split("_")[-1]
        if not tail.isdigit():
            return None
        idx = int(tail) % 3
        cycle = [
            ["editworld-v1", "gridworld-v1", "lineworld-v1"],
            ["gridworld-v1", "lineworld-v1", "editworld-v1"],
            ["lineworld-v1", "editworld-v1", "gridworld-v1"],
        ]
        return cycle[idx]

    def _index_env_rank(index_path: Path, envs: list[str] | None) -> int | None:
        if not envs:
            return None
        payload = load_canon_json(index_path)
        by_env = payload.get("witnesses_by_env_kind")
        if not isinstance(by_env, dict):
            return None
        for rank, env in enumerate(envs):
            bucket = by_env.get(env)
            if not isinstance(bucket, dict):
                continue
            for kind in ("anchor", "pressure", "gate"):
                entries = bucket.get(kind)
                if isinstance(entries, list) and entries:
                    return rank
        return None

    for epoch_idx in range(1, n_epochs + 1):
        epoch_id = f"epoch_{epoch_idx}"
        epoch_dir = epochs_dir / epoch_id
        _reset_inbox(state_dir)
        fam_list = family_by_epoch.get(str(epoch_idx), [])
        mac_list = macro_by_epoch.get(str(epoch_idx), [])
        patch_list = mech_patch_by_epoch.get(str(epoch_idx), [])
        if not isinstance(fam_list, list) or not isinstance(mac_list, list) or not isinstance(patch_list, list):
            raise ValueError("campaign pack proposals must be lists")
        _copy_proposals(fam_list, pack_dir, state_dir / INBOX_FAMILY_DIR)
        _copy_proposals(mac_list, pack_dir, state_dir / INBOX_MACRO_DIR)
        _copy_proposals(patch_list, pack_dir, state_dir / INBOX_MECH_PATCH_DIR)
        if ontology_enabled:
            inbox_src = Path(ontology_inbox_rel)
            if not inbox_src.is_absolute():
                inbox_src = pack_dir / inbox_src
            _copy_ontology_inbox(inbox_src, state_dir / INBOX_ONTOLOGY_V2_DIR)

        macro_trace_paths: list[Path] = []
        if macro_miner_trace_window > 0:
            start_idx = max(1, epoch_idx - macro_miner_trace_window)
            for idx in range(start_idx, epoch_idx):
                macro_trace_paths.append(epochs_dir / f"epoch_{idx}" / "traces" / "trace_heldout_v1.jsonl")

        witness_proposed = False
        if (
            enable_witness_family_generalizer_v2
            and epoch_idx in insertion_epoch_set
            and epoch_idx > 1
            and first_insertion_epoch is not None
            and epoch_idx == first_insertion_epoch
        ):
            witness_index_path = None
            best_rank = None
            preferred_envs = _preferred_envs(epoch_id)
            for back in range(1, epoch_idx):
                candidate = epochs_dir / f"epoch_{epoch_idx - back}" / "diagnostics" / "instance_witness_index_v1.json"
                if not candidate.exists():
                    continue
                if preferred_envs:
                    rank = _index_env_rank(candidate, preferred_envs)
                    if rank is None:
                        continue
                    if best_rank is None or rank < best_rank:
                        witness_index_path = candidate
                        best_rank = rank
                        if rank == 0:
                            break
                else:
                    witness_index_path = candidate
                    break
            if witness_index_path is not None:
                base_state_hashes = _load_state_hashes(state_dir)
                frontier_hash = base_state_hashes.get("frontier_hash")
                if isinstance(frontier_hash, str):
                    epoch_key = derive_epoch_key(master_key_bytes, epoch_id, base_state_hashes, frontier_hash)
                    macro_active_set_hash = _hash_file(state_dir / "current" / "macro_active_set_v1.json")
                    witness_family = propose_witness_family_v2(
                        epoch_id=epoch_id,
                        epoch_key=epoch_key,
                        witness_index_path=witness_index_path,
                        frontier_hash=frontier_hash,
                        macro_active_set_hash=macro_active_set_hash,
                        out_dir=state_dir / INBOX_FAMILY_DIR,
                    )
                    if witness_family is not None:
                        witness_proposed = True

        if enable_family_generalizer and epoch_idx in insertion_epoch_set and not witness_proposed:
            propose_next_family(
                manifest=manifest,
                manifest_path=manifest_path,
                state_dir=state_dir,
                out_dir=state_dir / INBOX_FAMILY_DIR,
            )

        if enable_meta_patch_searcher and epoch_idx > 0:
            run_meta = True
            if isinstance(meta_patch_epochs, list) and meta_patch_epochs:
                allowed_epochs = {int(e) for e in meta_patch_epochs}
                run_meta = epoch_idx in allowed_epochs
            if run_meta:
                propose_meta_patch(
                    state_dir=state_dir,
                    out_dir=state_dir / INBOX_META_PATCH_DIR,
                )

        if enable_macro_miner and epoch_idx > 1 and macro_miner_top_k > 0:
            run_miner = True
            if isinstance(macro_epochs, list) and macro_epochs:
                allowed_epochs = {int(e) for e in macro_epochs}
                run_miner = epoch_idx in allowed_epochs
            if run_miner:
                prev_diag = epochs_dir / f"epoch_{epoch_idx-1}" / "diagnostics"
                active_set = load_canon_json(state_dir / "current" / "macro_active_set_v1.json")
                active_ids = list(active_set.get("active_macro_ids", [])) if isinstance(active_set, dict) else []
                active_macros = load_macro_defs(state_dir / "current" / "macros", allowed=active_ids)
                mine_macros(
                    trace_paths=macro_trace_paths,
                    active_macros=active_macros,
                    out_dir=state_dir / INBOX_MACRO_DIR,
                    diagnostics_dir=prev_diag,
                    epoch_id=f"epoch_{epoch_idx-1}",
                    top_k=macro_miner_top_k,
                )

        if enable_policy_synthesizer and epoch_idx > 1:
            run_synth = True
            synth_epochs = None
            if enable_mech_patch_searcher and isinstance(mech_patch_epochs, list) and mech_patch_epochs:
                synth_epochs = mech_patch_epochs
            elif isinstance(policy_synth_epochs, list) and policy_synth_epochs:
                synth_epochs = policy_synth_epochs
            if isinstance(synth_epochs, list) and epoch_idx not in synth_epochs:
                run_synth = False
            if run_synth:
                prev_diag = epochs_dir / f"epoch_{epoch_idx-1}" / "diagnostics"
                synthesize_policy_patch(
                    state_dir=state_dir,
                    diagnostics_dir=prev_diag,
                    out_dir=state_dir / INBOX_MECH_PATCH_DIR,
                )

        run_epoch(
            epoch_id=epoch_id,
            base_ontology=base_ontology,
            base_mech=base_mech,
            state_dir=state_dir,
            out_dir=epoch_dir,
            master_key_b64=master_key_b64,
            created_unix_ms=0,
            strict_rsi=strict_rsi,
            strict_integrity=strict_integrity,
            strict_portfolio=strict_portfolio,
            strict_transfer=strict_transfer,
            enable_mech_patch_searcher=enable_mech_patch_searcher,
            macro_trace_paths=macro_trace_paths,
        )

        if ontology_enabled and ontology_eval_every > 0 and epoch_idx % ontology_eval_every == 0:
            start = max(1, epoch_idx - max(ontology_window, 1) + 1)
            window_epochs = list(range(start, epoch_idx + 1))
            evaluate_ontology_v2(
                state_dir=state_dir,
                epoch_id=epoch_id,
                meta=meta,
                constants=constants,
                window_epochs=window_epochs,
                strict=True,
            )
            maybe_evict_ontology_v2(state_dir=state_dir, epoch_id=epoch_id, meta=meta, constants=constants)

        expected = expected_frontier.get(str(epoch_idx))
        if expected:
            state_ledger_path = state_dir / "current" / "state_ledger_v1.jsonl"
            if not state_ledger_path.exists():
                raise SystemExit("CAMPAIGN_EXPECTED_FRONTIER_INSERTION_MISSING")
            found_event = False
            for raw in state_ledger_path.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                payload = json.loads(raw)
                if payload.get("epoch_id") != epoch_id:
                    continue
                frontier_event = payload.get("frontier_event")
                if isinstance(frontier_event, dict) and frontier_event.get("event_type") == "FRONTIER_ACTIVATE_V1":
                    found_event = True
                    break
            if not found_event:
                raise SystemExit("CAMPAIGN_EXPECTED_FRONTIER_INSERTION_MISSING")

    portfolio_expected = campaign_pack.get("portfolio_expected") if isinstance(campaign_pack, dict) else None
    if isinstance(portfolio_expected, dict) and portfolio_expected.get("must_emit_portfolio_receipt"):
        receipts = list((state_dir / "epochs").glob("epoch_*/diagnostics/rsi_portfolio_receipt_v1.json"))
        if not receipts:
            raise SystemExit("CAMPAIGN_EXPECTED_PORTFOLIO_RECEIPT_MISSING")

    transfer_expected = campaign_pack.get("transfer_expected") if isinstance(campaign_pack, dict) else None
    if isinstance(transfer_expected, dict) and transfer_expected.get("must_emit_transfer_receipt"):
        receipts = list((state_dir / "epochs").glob("epoch_*/diagnostics/rsi_transfer_receipt_v1.json"))
        if not receipts:
            raise SystemExit("CAMPAIGN_EXPECTED_TRANSFER_RECEIPT_MISSING")

    if ontology_enabled:
        final_epoch_id = f"epoch_{n_epochs}"
        diagnostics_dir = epochs_dir / final_epoch_id / "diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        receipt = build_rsi_ontology_receipt_v2(
            run_id=out_dir.name,
            final_epoch=final_epoch_id,
            ontology_root=state_dir / "current" / "ontology",
            constants=constants,
            meta=meta,
        )
        write_canon_json(diagnostics_dir / "rsi_ontology_receipt_v2.json", receipt)

    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--campaign", required=False)
    parser.add_argument("--campaign_pack", required=False)
    parser.add_argument("--strict-rsi", action="store_true")
    parser.add_argument("--strict-integrity", action="store_true")
    parser.add_argument("--strict-portfolio", action="store_true")
    parser.add_argument("--strict-transfer", action="store_true")
    parser.add_argument("--enable_macro_miner", action="store_true")
    parser.add_argument("--enable_policy_synthesizer", action="store_true")
    parser.add_argument("--enable_family_generalizer", action="store_true")
    parser.add_argument("--enable_witness_emission", action="store_true")
    parser.add_argument("--enable_witness_family_generalizer_v2", action="store_true")
    parser.add_argument("--enable_mech_patch_searcher", action="store_true")
    parser.add_argument("--enable_meta_patch_searcher", action="store_true")
    parser.add_argument("--mode", choices=["real", "synthetic"], default="real")
    args = parser.parse_args()

    constants = require_constants()
    campaign: dict[str, Any] = {}
    campaign_pack = None
    pack_path = None
    if args.mode == "synthetic":
        if args.campaign:
            campaign = json.loads(Path(args.campaign).read_text(encoding="utf-8"))
        else:
            campaign = default_campaign(constants)
            write_canon_json(Path(args.out_dir) / "rsi_campaign_v1.json", campaign)
    else:
        if args.campaign_pack:
            pack_path = Path(args.campaign_pack)
        else:
            pack_path = Path("campaigns/rsi_real_ignite_v1/rsi_real_campaign_pack_v1.json")
        if not pack_path.exists():
            raise SystemExit("campaign_pack missing for real mode")
        campaign_pack = load_canon_json(pack_path)

    run_campaign(
        Path(args.out_dir),
        campaign,
        strict_rsi=args.strict_rsi,
        strict_integrity=args.strict_integrity,
        strict_portfolio=args.strict_portfolio,
        strict_transfer=args.strict_transfer,
        enable_macro_miner=args.enable_macro_miner,
        enable_policy_synthesizer=args.enable_policy_synthesizer,
        enable_family_generalizer=args.enable_family_generalizer,
        enable_witness_emission=args.enable_witness_emission,
        enable_witness_family_generalizer_v2=args.enable_witness_family_generalizer_v2,
        enable_mech_patch_searcher=args.enable_mech_patch_searcher,
        enable_meta_patch_searcher=args.enable_meta_patch_searcher,
        mode=args.mode,
        campaign_pack=campaign_pack,
        pack_path=pack_path,
    )


if __name__ == "__main__":
    main()
