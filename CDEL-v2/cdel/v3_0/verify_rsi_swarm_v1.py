"""Verifier for RSI swarm v3.0 runs."""

from __future__ import annotations

import argparse
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from .barrier_ledger import load_barrier_ledger, validate_barrier_chain
from .constants import meta_identities, require_constants
from .immutable_core import load_lock, validate_lock, validate_receipt
from .swarm_ledger import load_swarm_ledger, validate_swarm_chain


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_relpath(state_dir: Path, relpath: str) -> Path:
    repo_path = _repo_root() / relpath
    if repo_path.exists():
        return repo_path
    return state_dir / relpath


def _hash_json(payload: Any) -> str:
    return sha256_prefixed(canon_bytes(payload))


def compute_swarm_run_id(pack: dict[str, Any]) -> str:
    payload = {"pack": pack, "spec_version": "v3_0"}
    return _hash_json(payload)


def _load_required_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        _fail("SCHEMA_INVALID")
    return payload


def _ensure_hash_match(expected: str, actual: str) -> None:
    if expected != actual:
        _fail("CANON_HASH_MISMATCH")


def _accept_ref_hash(event: dict[str, Any]) -> str:
    payload = dict(event)
    payload.pop("event_hash", None)
    inner = dict(payload.get("payload") or {})
    inner.pop("barrier_entry_hash", None)
    inner.pop("barrier_ledger_head_hash_new", None)
    payload["payload"] = inner
    return sha256_prefixed(canon_bytes(payload))


def _swarm_end_ref_hash(event: dict[str, Any]) -> str:
    payload = dict(event)
    payload.pop("event_hash", None)
    inner = dict(payload.get("payload") or {})
    inner.pop("swarm_ledger_head_hash", None)
    payload["payload"] = inner
    return sha256_prefixed(canon_bytes(payload))


def _task_id_from_spec(task_spec: dict[str, Any]) -> str:
    return _hash_json(task_spec)


def _result_id_from_manifest(manifest: dict[str, Any]) -> str:
    return _hash_json(manifest)


def _proposal_id_from_payload(payload: dict[str, Any]) -> str:
    return _hash_json(payload)


def _load_task_spec(state_dir: Path, relpath: str) -> dict[str, Any]:
    path = state_dir / relpath
    return _load_required_json(path)


def _load_result_manifest(state_dir: Path, relpath: str) -> dict[str, Any]:
    path = state_dir / relpath
    return _load_required_json(path)


def _verify_artifacts(state_dir: Path, manifest: dict[str, Any]) -> None:
    artifacts = manifest.get("artifacts")
    if artifacts is None:
        return
    if not isinstance(artifacts, list):
        _fail("SCHEMA_INVALID")
    for art in artifacts:
        if not isinstance(art, dict):
            _fail("SCHEMA_INVALID")
        relpath = art.get("relpath")
        if not isinstance(relpath, str):
            _fail("SCHEMA_INVALID")
        path = state_dir / relpath
        if not path.exists():
            _fail("MISSING_ARTIFACT")
        expected = art.get("sha256")
        if isinstance(expected, str) and expected.startswith("sha256:"):
            digest = sha256_prefixed(path.read_bytes())
            if digest != expected:
                _fail("CANON_HASH_MISMATCH")


def _verify_optional_barrier_proposal(state_dir: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
    proposal = manifest.get("optional_barrier_proposal")
    if not isinstance(proposal, dict):
        _fail("SCHEMA_INVALID")
    present = proposal.get("present")
    if not isinstance(present, bool):
        _fail("SCHEMA_INVALID")
    if not present:
        return None
    relpath = proposal.get("proposal_relpath")
    if not isinstance(relpath, str):
        _fail("SCHEMA_INVALID")
    path = state_dir / relpath
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        _fail("SCHEMA_INVALID")
    return payload


def _capabilities_from_pack(pack: dict[str, Any]) -> list[dict[str, Any]]:
    agents = pack.get("agents")
    if not isinstance(agents, list):
        _fail("SCHEMA_INVALID")
    return agents


def _agent_caps_map(agents: list[dict[str, Any]]) -> dict[str, set[str]]:
    caps: dict[str, set[str]] = {}
    for agent in agents:
        agent_id = agent.get("agent_id")
        if not isinstance(agent_id, str):
            _fail("SCHEMA_INVALID")
        caps_list = agent.get("capabilities")
        if not isinstance(caps_list, list):
            _fail("SCHEMA_INVALID")
        caps[agent_id] = {str(c) for c in caps_list}
    return caps


def _assign_tasks_deterministic(task_specs: list[dict[str, Any]], agents: list[dict[str, Any]]) -> dict[str, str]:
    agents_sorted = sorted(agents, key=lambda a: a.get("agent_id", ""))
    caps_map = _agent_caps_map(agents_sorted)
    agent_ids = [a.get("agent_id") for a in agents_sorted]
    expected: dict[str, str] = {}
    task_specs_sorted = sorted(task_specs, key=lambda t: _task_id_from_spec(t))
    for idx, task in enumerate(task_specs_sorted):
        required = set(task.get("required_capabilities") or [])
        assigned = None
        if agent_ids:
            start_idx = idx % len(agent_ids)
            for offset in range(len(agent_ids)):
                candidate = agent_ids[(start_idx + offset) % len(agent_ids)]
                if candidate and required.issubset(caps_map.get(candidate, set())):
                    assigned = candidate
                    break
        expected[_task_id_from_spec(task)] = assigned or "NONE"
    return expected


def verify(state_dir: Path) -> dict[str, Any]:
    constants = require_constants()
    meta = meta_identities()

    lock_rel = constants.get("IMMUTABLE_CORE_LOCK_REL")
    if not isinstance(lock_rel, str):
        _fail("IMMUTABLE_CORE_ATTESTATION_INVALID")

    lock_path = _repo_root() / lock_rel
    if not lock_path.exists():
        _fail("MISSING_ARTIFACT")
    lock = load_lock(lock_path)
    try:
        validate_lock(lock)
    except Exception as exc:  # noqa: BLE001
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID") from exc

    receipt_path = state_dir / "diagnostics" / "immutable_core_receipt_v1.json"
    if not receipt_path.exists():
        _fail("IMMUTABLE_CORE_ATTESTATION_MISSING")
    try:
        receipt = load_canon_json(receipt_path)
        validate_receipt(receipt, lock)
    except Exception as exc:  # noqa: BLE001
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID") from exc

    swarm_path = state_dir / "ledger" / "swarm_ledger_v1.jsonl"
    events = load_swarm_ledger(swarm_path)
    swarm_head_hash = validate_swarm_chain(events)

    if not events:
        _fail("SCHEMA_INVALID")
    init_event = events[0]
    if init_event.get("event_type") != "SWARM_INIT":
        _fail("SCHEMA_INVALID")
    init_payload = init_event.get("payload")
    if not isinstance(init_payload, dict):
        _fail("SCHEMA_INVALID")

    pack_relpath = init_payload.get("pack_relpath")
    if not isinstance(pack_relpath, str):
        _fail("SCHEMA_INVALID")
    pack_path = _resolve_relpath(state_dir, pack_relpath)
    pack = _load_required_json(pack_path)
    if pack.get("schema") != "rsi_real_swarm_pack_v1" or pack.get("spec_version") != "v3_0":
        _fail("SCHEMA_INVALID")
    pack_hash = _hash_json(pack)
    _ensure_hash_match(init_payload.get("pack_hash"), pack_hash)

    run_id = compute_swarm_run_id(pack)
    _ensure_hash_match(init_payload.get("swarm_run_id"), run_id)

    icore_expected = init_payload.get("icore_id_expected")
    if icore_expected != lock.get("core_id"):
        _fail("SWARM_AGENT_ATTESTATION_MISMATCH")

    agents = _capabilities_from_pack(pack)
    agent_ids_sorted = sorted([a.get("agent_id") for a in agents if isinstance(a.get("agent_id"), str)])

    swarm_cfg = pack.get("swarm") if isinstance(pack.get("swarm"), dict) else None
    if not isinstance(swarm_cfg, dict):
        _fail("SCHEMA_INVALID")
    if init_payload.get("num_agents") != swarm_cfg.get("num_agents"):
        _fail("SCHEMA_INVALID")
    if init_payload.get("max_epochs") != swarm_cfg.get("max_epochs"):
        _fail("SCHEMA_INVALID")
    if init_payload.get("commit_policy") != swarm_cfg.get("commit_policy"):
        _fail("SCHEMA_INVALID")
    if init_payload.get("commit_policy") != constants.get("SWARM_COMMIT_POLICY"):
        _fail("SCHEMA_INVALID")

    agent_registers = [e for e in events if e.get("event_type") == "AGENT_REGISTER"]
    if len(agent_registers) != len(agent_ids_sorted):
        _fail("SCHEMA_INVALID")

    seen_agents: set[str] = set()
    for event in agent_registers:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        agent_id = payload.get("agent_id")
        if agent_id not in agent_ids_sorted:
            _fail("SCHEMA_INVALID")
        if agent_id in seen_agents:
            _fail("SCHEMA_INVALID")
        seen_agents.add(agent_id)
        receipt_rel = payload.get("agent_icore_receipt_relpath")
        if not isinstance(receipt_rel, str):
            _fail("SCHEMA_INVALID")
        receipt_path = state_dir / receipt_rel
        if not receipt_path.exists():
            _fail("IMMUTABLE_CORE_ATTESTATION_MISSING")
        try:
            agent_receipt = load_canon_json(receipt_path)
            validate_receipt(agent_receipt, lock)
        except Exception as exc:  # noqa: BLE001
            raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID") from exc
        if payload.get("core_id_observed") != icore_expected:
            _fail("SWARM_AGENT_ATTESTATION_MISMATCH")

    task_assign_events = [e for e in events if e.get("event_type") == "TASK_ASSIGN"]
    task_result_events = [e for e in events if e.get("event_type") == "TASK_RESULT"]
    result_verify_events = [e for e in events if e.get("event_type") == "RESULT_VERIFY"]
    propose_events = [e for e in events if e.get("event_type") == "BARRIER_UPDATE_PROPOSE"]
    accept_events = [e for e in events if e.get("event_type") == "BARRIER_UPDATE_ACCEPT"]
    epoch_begin_events = [e for e in events if e.get("event_type") == "EPOCH_BEGIN"]
    epoch_end_events = [e for e in events if e.get("event_type") == "EPOCH_END"]
    swarm_end_events = [e for e in events if e.get("event_type") == "SWARM_END"]

    if len(swarm_end_events) != 1:
        _fail("SCHEMA_INVALID")

    # TASK_ASSIGN -> TASK_RESULT closure
    results_by_task: dict[str, dict[str, Any]] = {}
    results_by_id: dict[str, dict[str, Any]] = {}
    manifest_by_result: dict[str, dict[str, Any]] = {}
    optional_proposal_by_result: dict[str, dict[str, Any]] = {}
    for event in task_result_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        task_id = payload.get("task_id")
        result_id = payload.get("result_id")
        if not isinstance(task_id, str) or not isinstance(result_id, str):
            _fail("SCHEMA_INVALID")
        if result_id in results_by_id:
            _fail("SCHEMA_INVALID")
        results_by_task[task_id] = event
        results_by_id[result_id] = event
        manifest_rel = payload.get("result_manifest_relpath")
        if not isinstance(manifest_rel, str):
            _fail("SCHEMA_INVALID")
        manifest = _load_result_manifest(state_dir, manifest_rel)
        manifest_by_result[result_id] = manifest
        _ensure_hash_match(result_id, _result_id_from_manifest(manifest))
        if manifest.get("task_id") != task_id:
            _fail("SCHEMA_INVALID")
        if manifest.get("agent_id") != payload.get("agent_id"):
            _fail("SCHEMA_INVALID")
        _verify_artifacts(state_dir, manifest)
        proposal_payload = _verify_optional_barrier_proposal(state_dir, manifest)
        if proposal_payload is not None:
            optional_proposal_by_result[result_id] = proposal_payload
        receipt_rel = manifest.get("agent_receipt_relpath")
        if not isinstance(receipt_rel, str):
            _fail("SCHEMA_INVALID")
        if not (state_dir / receipt_rel).exists():
            _fail("MISSING_ARTIFACT")

    epoch_begin_by_index: dict[int, dict[str, Any]] = {}
    for event in epoch_begin_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        epoch_index = int(payload.get("epoch_index", -1))
        if epoch_index in epoch_begin_by_index:
            _fail("SCHEMA_INVALID")
        epoch_begin_by_index[epoch_index] = payload

    for event in task_assign_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        task_id = payload.get("task_id")
        if not isinstance(task_id, str):
            _fail("SCHEMA_INVALID")
        if task_id not in results_by_task:
            _fail("MISSING_ARTIFACT")
        task_spec_rel = payload.get("task_spec_relpath")
        if not isinstance(task_spec_rel, str):
            _fail("SCHEMA_INVALID")
        task_spec = _load_task_spec(state_dir, task_spec_rel)
        _ensure_hash_match(task_id, _task_id_from_spec(task_spec))
        epoch_index = int(payload.get("epoch_index", -1))
        epoch_payload = epoch_begin_by_index.get(epoch_index)
        if not epoch_payload:
            _fail("SCHEMA_INVALID")
        if payload.get("base_barrier_head_hash") != epoch_payload.get("barrier_ledger_head_hash"):
            _fail("NONDETERMINISM")

    verify_by_result: dict[str, dict[str, Any]] = {}
    for event in result_verify_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        result_id = payload.get("result_id")
        if not isinstance(result_id, str):
            _fail("SCHEMA_INVALID")
        if result_id not in results_by_id:
            _fail("SWARM_EVENT_REFERENCE_MISSING")
        verify_by_result[result_id] = event
        receipt_rel = payload.get("verifier_receipt_relpath")
        if not isinstance(receipt_rel, str):
            _fail("SCHEMA_INVALID")
        if not (state_dir / receipt_rel).exists():
            _fail("MISSING_ARTIFACT")

    for event in task_result_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        result_id = payload.get("result_id")
        if result_id not in verify_by_result:
            _fail("MISSING_ARTIFACT")

    # Barrier ledger checks
    barrier_path = state_dir / "ledger" / "barrier_ledger_v2.jsonl"
    barrier_entries = load_barrier_ledger(barrier_path)
    barrier_head_hash = validate_barrier_chain(barrier_entries)
    entries_by_hash = {entry.get("entry_hash"): entry for entry in barrier_entries}

    accept_hashes = set()
    accept_ref_hashes = set()
    accept_by_entry_hash: dict[str, dict[str, Any]] = {}
    for event in accept_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        if payload.get("accepted") is not True:
            continue
        accept_hashes.add(event.get("event_hash"))
        accept_ref_hashes.add(_accept_ref_hash(event))
        entry_hash = payload.get("barrier_entry_hash")
        if isinstance(entry_hash, str):
            if entry_hash not in entries_by_hash:
                _fail("SWARM_EVENT_REFERENCE_MISSING")
            accept_by_entry_hash[entry_hash] = event
        else:
            _fail("SCHEMA_INVALID")

    for entry in barrier_entries:
        swarm_event_hash = entry.get("swarm_event_hash")
        entry_hash = entry.get("entry_hash")
        if entry_hash not in accept_by_entry_hash:
            _fail("SWARM_EVENT_REFERENCE_MISSING")
        accept_event = accept_by_entry_hash[entry_hash]
        accept_event_hash = accept_event.get("event_hash")
        accept_ref_hash = _accept_ref_hash(accept_event)
        if swarm_event_hash not in {accept_event_hash, accept_ref_hash}:
            _fail("SWARM_EVENT_REFERENCE_MISSING")

    # Deterministic assignment per epoch
    tasks_by_epoch: dict[int, list[dict[str, Any]]] = {}
    assigns_by_epoch: dict[int, list[dict[str, Any]]] = {}
    for event in task_assign_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        epoch_index = int(payload.get("epoch_index", -1))
        assigns_by_epoch.setdefault(epoch_index, []).append(event)
        task_spec_rel = payload.get("task_spec_relpath")
        if isinstance(task_spec_rel, str):
            task_spec = _load_task_spec(state_dir, task_spec_rel)
            tasks_by_epoch.setdefault(epoch_index, []).append(task_spec)

    for epoch, task_specs in tasks_by_epoch.items():
        expected_assignments = _assign_tasks_deterministic(task_specs, agents)
        assign_events = assigns_by_epoch.get(epoch, [])
        task_ids_in_ledger = [e.get("payload", {}).get("task_id") for e in assign_events]
        sorted_task_ids = sorted(expected_assignments.keys())
        if task_ids_in_ledger != sorted_task_ids:
            _fail("NONDETERMINISM")
        for event in assign_events:
            payload = event.get("payload")
            if not isinstance(payload, dict):
                _fail("SCHEMA_INVALID")
            task_id = payload.get("task_id")
            if task_id not in expected_assignments:
                _fail("SCHEMA_INVALID")
            if payload.get("agent_id") != expected_assignments[task_id]:
                _fail("NONDETERMINISM")

    # Result verification ordering
    ok_results = []
    for event in task_result_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        if payload.get("status") == "OK":
            ok_results.append(
                (
                    payload.get("task_id"),
                    payload.get("agent_id"),
                    payload.get("result_id"),
                )
            )
    ok_results_sorted = sorted(ok_results)
    verify_order = [
        (
            (event.get("payload") or {}).get("result_id"),
        )
        for event in result_verify_events
        if results_by_id.get((event.get("payload") or {}).get("result_id"), {}).get("payload", {}).get("status") == "OK"
    ]
    verify_result_ids = [rid for (rid,) in verify_order]
    expected_result_ids = [rid for _, _, rid in ok_results_sorted]
    if verify_result_ids != expected_result_ids:
        _fail("NONDETERMINISM")

    # Barrier update selection determinism
    result_verdicts: dict[str, str] = {}
    for event in result_verify_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        result_verdicts[payload.get("result_id")] = payload.get("verdict")

    proposals_by_epoch: dict[int, list[dict[str, Any]]] = {}
    proposal_ids_by_epoch: dict[int, list[str]] = {}
    for event in propose_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        result_id = payload.get("result_id")
        if not isinstance(result_id, str):
            _fail("SCHEMA_INVALID")
        if result_verdicts.get(result_id) != "VALID":
            continue
        if result_id not in results_by_id:
            _fail("SWARM_EVENT_REFERENCE_MISSING")
        relpath = payload.get("proposed_barrier_entry_relpath")
        if not isinstance(relpath, str):
            _fail("SCHEMA_INVALID")
        base_head = payload.get("base_barrier_head_hash")
        task_event = results_by_id.get(result_id)
        epoch_index = int(task_event.get("payload", {}).get("epoch_index", -1)) if task_event else -1
        epoch_payload = epoch_begin_by_index.get(epoch_index)
        if not epoch_payload:
            _fail("SCHEMA_INVALID")
        if base_head != epoch_payload.get("barrier_ledger_head_hash"):
            _fail("NONDETERMINISM")
        proposal_path = state_dir / relpath
        if not proposal_path.exists():
            _fail("MISSING_ARTIFACT")
        proposal = load_canon_json(proposal_path)
        if not isinstance(proposal, dict):
            _fail("SCHEMA_INVALID")
        optional_payload = optional_proposal_by_result.get(result_id)
        manifest = manifest_by_result.get(result_id)
        if manifest is not None:
            opt = manifest.get("optional_barrier_proposal")
            if isinstance(opt, dict) and opt.get("present") is True:
                if opt.get("proposal_relpath") != relpath:
                    _fail("CANON_HASH_MISMATCH")
        if optional_payload is not None and proposal != optional_payload:
            _fail("CANON_HASH_MISMATCH")
        proposal_id = _proposal_id_from_payload(proposal)
        if payload.get("proposal_id") != proposal_id:
            _fail("CANON_HASH_MISMATCH")
        # ensure proposal fields align with manifest when present
        if optional_payload is not None:
            if proposal.get("barrier_prev") != optional_payload.get("barrier_prev"):
                _fail("CANON_HASH_MISMATCH")
            if proposal.get("barrier_next") != optional_payload.get("barrier_next"):
                _fail("CANON_HASH_MISMATCH")
            if proposal.get("recovery_bundle_id") != optional_payload.get("recovery_bundle_id"):
                _fail("CANON_HASH_MISMATCH")
        proposals_by_epoch.setdefault(epoch_index, []).append(proposal)
        proposal_ids_by_epoch.setdefault(epoch_index, []).append(proposal_id)

    alpha_num = int(pack.get("swarm", {}).get("barrier_alpha_num", constants.get("SWARM_BARRIER_ALPHA_NUM", 19)))
    alpha_den = int(pack.get("swarm", {}).get("barrier_alpha_den", constants.get("SWARM_BARRIER_ALPHA_DEN", 20)))
    k_const = int(constants.get("SWARM_MAX_ACCEPTS_PER_EPOCH", 0))
    k_pack = int(pack.get("swarm", {}).get("max_accepts_per_epoch", k_const))
    max_accepts = min(k_const, k_pack) if k_const else k_pack

    accepts_by_epoch: dict[int, list[str]] = {}
    for event in accept_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        if payload.get("accepted") is not True:
            continue
        proposal_id = payload.get("proposal_id")
        if not isinstance(proposal_id, str):
            _fail("SCHEMA_INVALID")
        # infer epoch from proposal_id mapping
        epoch_index = None
        for epoch, proposal_ids in proposal_ids_by_epoch.items():
            if proposal_id in proposal_ids:
                epoch_index = epoch
                break
        if epoch_index is None:
            _fail("SCHEMA_INVALID")
        accepts_by_epoch.setdefault(epoch_index, []).append(proposal_id)

    for epoch, proposals in proposals_by_epoch.items():
        scored: list[tuple[Fraction, str]] = []
        for proposal in proposals:
            prev_val = proposal.get("barrier_prev")
            next_val = proposal.get("barrier_next")
            if not isinstance(prev_val, int) or not isinstance(next_val, int):
                _fail("SCHEMA_INVALID")
            if next_val * alpha_den > prev_val * alpha_num:
                continue
            proposal_id = _proposal_id_from_payload(proposal)
            scored.append((Fraction(prev_val, next_val), proposal_id))
        # sort by decreasing score (prev/next), tie by proposal_id
        scored.sort(key=lambda item: (-item[0], item[1]))
        expected_ids = [proposal_id for _, proposal_id in scored[:max_accepts]]
        actual_ids = accepts_by_epoch.get(epoch, [])
        if actual_ids != expected_ids:
            _fail("NONDETERMINISM")

    # SWARM_END head hashes
    end_payload = swarm_end_events[0].get("payload")
    if not isinstance(end_payload, dict):
        _fail("SCHEMA_INVALID")
    end_ref = _swarm_end_ref_hash(swarm_end_events[0])
    if end_payload.get("swarm_ledger_head_hash") not in {swarm_head_hash, end_ref}:
        _fail("SWARM_LEDGER_HASH_MISMATCH")
    if end_payload.get("barrier_ledger_head_hash") != barrier_head_hash:
        _fail("SWARM_BARRIER_LEDGER_MISMATCH")

    receipt = {
        "schema": "rsi_swarm_receipt_v1",
        "spec_version": "v3_0",
        "run_id": run_id,
        "pack_hash": pack_hash,
        "constitution_hash": meta.get("META_HASH", ""),
        "verdict": "VALID",
        "reason": "OK",
        "num_agents": int(init_payload.get("num_agents", len(agents))),
        "epochs_executed": len(epoch_begin_events),
        "swarm_ledger_head_hash": swarm_head_hash,
        "barrier_ledger_head_hash": barrier_head_hash,
    }
    return receipt


def _write_receipt(state_dir: Path, receipt: dict[str, Any]) -> None:
    out_path = state_dir / "diagnostics" / "rsi_swarm_receipt_v1.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(canon_bytes(receipt) + b"\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify RSI swarm v3.0 run")
    parser.add_argument("--state_dir", required=True)
    args = parser.parse_args()

    try:
        receipt = verify(Path(args.state_dir))
        _write_receipt(Path(args.state_dir), receipt)
    except Exception as exc:  # noqa: BLE001
        reason = str(exc) if str(exc) else "unknown"
        receipt = {
            "schema": "rsi_swarm_receipt_v1",
            "spec_version": "v3_0",
            "run_id": "",
            "pack_hash": "",
            "constitution_hash": "",
            "verdict": "INVALID",
            "reason": reason,
            "num_agents": 0,
            "epochs_executed": 0,
            "swarm_ledger_head_hash": "",
            "barrier_ledger_head_hash": "",
        }
        try:
            _write_receipt(Path(args.state_dir), receipt)
        except Exception:
            pass
        print(f"INVALID: {reason}")
        return

    print("VALID")


if __name__ == "__main__":
    main()
