"""Verifier for RSI swarm v3.1 runs (recursive subswarms)."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from .barrier_ledger import load_barrier_ledger, validate_barrier_chain
from .constants import meta_identities, require_constants
from .immutable_core import load_lock, validate_lock, validate_receipt
from .swarm_ledger import (
    compute_event_hash,
    compute_event_ref_hash,
    load_swarm_ledger,
    validate_swarm_chain,
)


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


def _normalized_pack_for_hash(pack: dict[str, Any]) -> dict[str, Any]:
    payload = dict(pack)
    payload.pop("pack_hash", None)
    parent_link = payload.get("parent_link")
    if isinstance(parent_link, dict) and parent_link.get("present") is True:
        parent_link = dict(parent_link)
        if "spawn_event_ref_hash" in parent_link:
            # Break the spawn-event hash cycle deterministically.
            parent_link["spawn_event_ref_hash"] = "__SELF__"
        payload["parent_link"] = parent_link
    return payload


def compute_pack_hash(pack: dict[str, Any]) -> str:
    return _hash_json(_normalized_pack_for_hash(pack))


def compute_swarm_run_id(pack: dict[str, Any]) -> str:
    payload = {
        "schema": pack.get("schema"),
        "spec_version": pack.get("spec_version"),
        "pack": _normalized_pack_for_hash(pack),
    }
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


def _check_relpath(relpath: str) -> None:
    if relpath.startswith("/") or relpath.startswith("\\"):
        _fail("PATH_TRAVERSAL")
    if "\\" in relpath:
        _fail("PATH_TRAVERSAL")
    parts = Path(relpath).parts
    if any(part == ".." for part in parts):
        _fail("PATH_TRAVERSAL")


def _scan_relpaths(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key.endswith("_relpath") and isinstance(value, str):
                _check_relpath(value)
            _scan_relpaths(value)
    elif isinstance(payload, list):
        for item in payload:
            _scan_relpaths(item)


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
        _check_relpath(relpath)
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
    _check_relpath(relpath)
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


def _compute_export_bundle_hash(bundle: dict[str, Any]) -> str:
    payload = dict(bundle)
    payload.pop("export_bundle_hash", None)
    return _hash_json(payload)


def _compute_joined_artifact_set_hash(exports: list[dict[str, Any]]) -> str:
    exports_sorted = sorted(exports, key=lambda row: (row.get("sha256", ""), row.get("relpath", "")))
    payload = {"exports": exports_sorted}
    return _hash_json(payload)


@dataclass
class NodeInfo:
    run_id: str
    parent_run_id: str | None
    depth: int
    out_dir_relpath: str


@dataclass
class VerifyContext:
    lock: dict[str, Any]
    constants: dict[str, Any]
    root_dir: Path
    visited: set[str]
    nodes: list[NodeInfo]
    allow_child: bool = False
    node_count: int = 0
    max_total_nodes: int = 0
    max_depth: int = 0


@dataclass
class ParentLink:
    parent_run_id: str
    parent_task_id: str
    sponsor_agent_id: str
    spawn_event_ref_hash: str
    depth: int
    subswarm_slot: int


def _verify_node(
    state_dir: Path,
    ctx: VerifyContext,
    expected_parent: ParentLink | None = None,
) -> dict[str, Any]:
    constants = ctx.constants
    meta = meta_identities()

    # Immutable core receipt
    receipt_path = state_dir / "diagnostics" / "immutable_core_receipt_v1.json"
    if not receipt_path.exists():
        _fail("IMMUTABLE_CORE_ATTESTATION_MISSING")
    try:
        receipt = load_canon_json(receipt_path)
        validate_receipt(receipt, ctx.lock)
    except Exception as exc:  # noqa: BLE001
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID") from exc

    # Swarm ledger
    swarm_path = state_dir / "ledger" / "swarm_ledger_v2.jsonl"
    events = load_swarm_ledger(swarm_path)
    swarm_head_hash, swarm_head_ref_hash = validate_swarm_chain(events)

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
    _check_relpath(pack_relpath)
    pack_path = _resolve_relpath(state_dir, pack_relpath)
    pack = _load_required_json(pack_path)
    if pack.get("schema") != "rsi_real_swarm_pack_v2" or pack.get("spec_version") != "v3_1":
        _fail("SCHEMA_INVALID")
    pack_hash = compute_pack_hash(pack)
    _ensure_hash_match(init_payload.get("pack_hash"), pack_hash)

    run_id = compute_swarm_run_id(pack)
    _ensure_hash_match(init_payload.get("swarm_run_id"), run_id)

    icore_expected = init_payload.get("icore_id_expected")
    if icore_expected != ctx.lock.get("core_id"):
        _fail("SWARM_AGENT_ATTESTATION_MISMATCH")

    # Parent link validation
    parent_link_payload = pack.get("parent_link")
    if not isinstance(parent_link_payload, dict):
        _fail("SCHEMA_INVALID")
    parent_present = parent_link_payload.get("present")
    if not isinstance(parent_present, bool):
        _fail("SCHEMA_INVALID")
    if expected_parent is None:
        if parent_present:
            if not ctx.allow_child:
                _fail("SUBSWARM_PARENT_LINK_MISMATCH")
            required = [
                "parent_swarm_run_id",
                "parent_task_id",
                "sponsor_agent_id",
                "spawn_event_ref_hash",
                "depth",
                "subswarm_slot",
            ]
            for key in required:
                if key not in parent_link_payload:
                    _fail("SUBSWARM_PARENT_LINK_MISMATCH")
            # Type checks for child self-verification
            if not isinstance(parent_link_payload.get("parent_swarm_run_id"), str):
                _fail("SUBSWARM_PARENT_LINK_MISMATCH")
            if not isinstance(parent_link_payload.get("parent_task_id"), str):
                _fail("SUBSWARM_PARENT_LINK_MISMATCH")
            if not isinstance(parent_link_payload.get("sponsor_agent_id"), str):
                _fail("SUBSWARM_PARENT_LINK_MISMATCH")
            if not isinstance(parent_link_payload.get("spawn_event_ref_hash"), str):
                _fail("SUBSWARM_PARENT_LINK_MISMATCH")
            depth = int(parent_link_payload.get("depth", -1))
            if depth < 1:
                _fail("SUBSWARM_PARENT_LINK_MISMATCH")
            if not isinstance(parent_link_payload.get("subswarm_slot"), int):
                _fail("SUBSWARM_PARENT_LINK_MISMATCH")
            parent_run_id = parent_link_payload.get("parent_swarm_run_id")
        else:
            depth = 0
            parent_run_id = None
    else:
        if not parent_present:
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        required = [
            "parent_swarm_run_id",
            "parent_task_id",
            "sponsor_agent_id",
            "spawn_event_ref_hash",
            "depth",
            "subswarm_slot",
        ]
        for key in required:
            if key not in parent_link_payload:
                _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        if parent_link_payload.get("parent_swarm_run_id") != expected_parent.parent_run_id:
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        if parent_link_payload.get("parent_task_id") != expected_parent.parent_task_id:
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        if parent_link_payload.get("sponsor_agent_id") != expected_parent.sponsor_agent_id:
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        if parent_link_payload.get("spawn_event_ref_hash") != expected_parent.spawn_event_ref_hash:
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        if int(parent_link_payload.get("depth", -1)) != expected_parent.depth:
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        if int(parent_link_payload.get("subswarm_slot", -1)) != expected_parent.subswarm_slot:
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        depth = int(parent_link_payload.get("depth"))
        parent_run_id = expected_parent.parent_run_id

    # Track node
    if run_id in ctx.visited:
        _fail("SUBSWARM_CYCLE_DETECTED")
    ctx.visited.add(run_id)
    ctx.node_count += 1
    if ctx.max_total_nodes == 0 and expected_parent is None:
        ctx.max_total_nodes = int(pack.get("swarm", {}).get("subswarm", {}).get("max_total_nodes", constants.get("SUBSWARM_MAX_TOTAL_NODES", 0)))
    if ctx.max_depth == 0 and expected_parent is None:
        ctx.max_depth = int(pack.get("swarm", {}).get("subswarm", {}).get("max_depth", constants.get("SUBSWARM_MAX_DEPTH", 0)))

    if ctx.max_total_nodes and ctx.node_count > ctx.max_total_nodes:
        _fail("SUBSWARM_NODE_LIMIT_EXCEEDED")
    if ctx.max_depth and depth > ctx.max_depth:
        _fail("SUBSWARM_DEPTH_LIMIT_EXCEEDED")

    out_rel = "."
    try:
        out_rel = str(state_dir.resolve().relative_to(ctx.root_dir.resolve())).replace("\\", "/") or "."
    except Exception:
        out_rel = "."
    if not any(node.run_id == run_id for node in ctx.nodes):
        ctx.nodes.append(NodeInfo(run_id=run_id, parent_run_id=parent_run_id, depth=depth, out_dir_relpath=out_rel))

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

    # Agent register events
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
        _check_relpath(receipt_rel)
        receipt_path = state_dir / receipt_rel
        if not receipt_path.exists():
            _fail("IMMUTABLE_CORE_ATTESTATION_MISSING")
        try:
            agent_receipt = load_canon_json(receipt_path)
            validate_receipt(agent_receipt, ctx.lock)
        except Exception as exc:  # noqa: BLE001
            raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID") from exc
        if payload.get("core_id_observed") != icore_expected:
            _fail("SWARM_AGENT_ATTESTATION_MISMATCH")

    # Scan relpaths for path traversal
    for event in events:
        payload = event.get("payload")
        if isinstance(payload, dict):
            _scan_relpaths(payload)

    task_assign_events = [e for e in events if e.get("event_type") == "TASK_ASSIGN"]
    task_result_events = [e for e in events if e.get("event_type") == "TASK_RESULT"]
    result_verify_events = [e for e in events if e.get("event_type") == "RESULT_VERIFY"]
    propose_events = [e for e in events if e.get("event_type") == "BARRIER_UPDATE_PROPOSE"]
    accept_events = [e for e in events if e.get("event_type") == "BARRIER_UPDATE_ACCEPT"]
    epoch_begin_events = [e for e in events if e.get("event_type") == "EPOCH_BEGIN"]
    epoch_end_events = [e for e in events if e.get("event_type") == "EPOCH_END"]
    swarm_end_events = [e for e in events if e.get("event_type") == "SWARM_END"]
    spawn_events = [e for e in events if e.get("event_type") == "SUBSWARM_SPAWN"]
    join_attempt_events = [e for e in events if e.get("event_type") == "SUBSWARM_JOIN_ATTEMPT"]
    join_accept_events = [e for e in events if e.get("event_type") == "SUBSWARM_JOIN_ACCEPT"]
    join_reject_events = [e for e in events if e.get("event_type") == "SUBSWARM_JOIN_REJECT"]

    if len(swarm_end_events) != 1:
        _fail("SCHEMA_INVALID")

    # TASK_RESULT closure + manifests
    results_by_task: dict[str, dict[str, Any]] = {}
    results_by_id: dict[str, dict[str, Any]] = {}
    manifest_by_result: dict[str, dict[str, Any]] = {}
    optional_proposal_by_result: dict[str, dict[str, Any]] = {}
    spawn_request_by_result: dict[str, dict[str, Any]] = {}

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
        _check_relpath(manifest_rel)
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
        _check_relpath(receipt_rel)
        if not (state_dir / receipt_rel).exists():
            _fail("MISSING_ARTIFACT")
        spawn_child = manifest.get("spawn_child")
        if not isinstance(spawn_child, dict):
            _fail("SCHEMA_INVALID")
        present = spawn_child.get("present")
        if not isinstance(present, bool):
            _fail("SCHEMA_INVALID")
        if present:
            spawn_request_by_result[result_id] = spawn_child

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
        _check_relpath(task_spec_rel)
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
        _check_relpath(receipt_rel)
        if not (state_dir / receipt_rel).exists():
            _fail("MISSING_ARTIFACT")

    for event in task_result_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        result_id = payload.get("result_id")
        if result_id not in verify_by_result:
            _fail("MISSING_ARTIFACT")

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
        _check_relpath(relpath)
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
        scored.sort(key=lambda item: (-item[0], item[1]))
        expected_ids = [proposal_id for _, proposal_id in scored[:max_accepts]]
        actual_ids = accepts_by_epoch.get(epoch, [])
        if actual_ids != expected_ids:
            _fail("NONDETERMINISM")

    # Spawn + join tracking
    spawn_by_child: dict[str, dict[str, Any]] = {}
    spawn_epoch_by_child: dict[str, int] = {}
    spawn_ref_by_child: dict[str, str] = {}
    child_depth_by_child: dict[str, int] = {}
    children_by_task: dict[str, set[int]] = {}

    for event in spawn_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        child_run_id = payload.get("child_swarm_run_id")
        if not isinstance(child_run_id, str):
            _fail("SCHEMA_INVALID")
        if child_run_id in spawn_by_child:
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        spawn_by_child[child_run_id] = payload
        spawn_epoch_by_child[child_run_id] = int(payload.get("parent_epoch_index", -1))
        spawn_ref_by_child[child_run_id] = event.get("event_ref_hash")
        child_depth = int(payload.get("depth", -1))
        if child_depth != depth + 1:
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        child_depth_by_child[child_run_id] = child_depth
        parent_task_id = payload.get("parent_task_id")
        subswarm_slot = payload.get("subswarm_slot")
        if isinstance(parent_task_id, str) and isinstance(subswarm_slot, int):
            slots = children_by_task.setdefault(parent_task_id, set())
            if subswarm_slot in slots:
                _fail("SUBSWARM_PARENT_LINK_MISMATCH")
            slots.add(subswarm_slot)

    # Join uniqueness
    joined_children: set[str] = set()
    for event in join_accept_events + join_reject_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        child_run_id = payload.get("child_swarm_run_id")
        if not isinstance(child_run_id, str):
            _fail("SCHEMA_INVALID")
        if child_run_id in joined_children:
            _fail("SUBSWARM_DUPLICATE_JOIN")
        joined_children.add(child_run_id)

    # Verify spawn ordering determinism per epoch
    spawn_requests_by_epoch: dict[int, list[dict[str, Any]]] = {}
    for result_id, spawn_request in spawn_request_by_result.items():
        if result_verdicts.get(result_id) != "VALID":
            continue
        task_event = results_by_id.get(result_id)
        epoch_index = int(task_event.get("payload", {}).get("epoch_index", -1)) if task_event else -1
        spawn_requests_by_epoch.setdefault(epoch_index, []).append({
            "parent_task_id": manifest_by_result[result_id].get("task_id"),
            "sponsor_agent_id": manifest_by_result[result_id].get("agent_id"),
            "subswarm_slot": spawn_request.get("subswarm_slot"),
        })

    max_spawns_per_epoch = int(pack.get("swarm", {}).get("subswarm", {}).get("max_spawns_per_epoch", constants.get("SUBSWARM_MAX_SPAWNS_PER_EPOCH", 0)))
    for epoch_index, requests in spawn_requests_by_epoch.items():
        ordered = sorted(requests, key=lambda r: (str(r.get("parent_task_id")), str(r.get("sponsor_agent_id")), int(r.get("subswarm_slot", -1))))
        expected = ordered[:max_spawns_per_epoch] if max_spawns_per_epoch else ordered
        actual = [
            e.get("payload") for e in spawn_events if (e.get("payload") or {}).get("parent_epoch_index") == epoch_index
        ]
        actual_keys = [
            (p.get("parent_task_id"), p.get("sponsor_agent_id"), p.get("subswarm_slot"))
            for p in actual
        ]
        expected_keys = [
            (p.get("parent_task_id"), p.get("sponsor_agent_id"), p.get("subswarm_slot"))
            for p in expected
        ]
        if actual_keys != expected_keys:
            _fail("NONDETERMINISM")

    # Verify join attempts ordering + outcomes
    join_attempts_by_epoch: dict[int, list[dict[str, Any]]] = {}
    for event in join_attempt_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        epoch_index = int(payload.get("parent_epoch_index", -1))
        join_attempts_by_epoch.setdefault(epoch_index, []).append(payload)

    join_accept_by_epoch: dict[int, list[dict[str, Any]]] = {}
    for event in join_accept_events:
        payload = event.get("payload")
        if isinstance(payload, dict):
            epoch_index = int(payload.get("parent_epoch_index", -1))
            join_accept_by_epoch.setdefault(epoch_index, []).append(payload)

    join_reject_by_epoch: dict[int, list[dict[str, Any]]] = {}
    for event in join_reject_events:
        payload = event.get("payload")
        if isinstance(payload, dict):
            epoch_index = int(payload.get("parent_epoch_index", -1))
            join_reject_by_epoch.setdefault(epoch_index, []).append(payload)

    # Ensure join phase happens before task assignment within each epoch
    join_indices_by_epoch: dict[int, list[int]] = {}
    task_indices_by_epoch: dict[int, list[int]] = {}
    for idx, event in enumerate(events):
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if event.get("event_type") in {"SUBSWARM_JOIN_ATTEMPT", "SUBSWARM_JOIN_ACCEPT", "SUBSWARM_JOIN_REJECT"}:
            epoch_index = int(payload.get("parent_epoch_index", -1))
            join_indices_by_epoch.setdefault(epoch_index, []).append(idx)
        if event.get("event_type") == "TASK_ASSIGN":
            epoch_index = int(payload.get("epoch_index", -1))
            task_indices_by_epoch.setdefault(epoch_index, []).append(idx)

    for epoch_index, join_indices in join_indices_by_epoch.items():
        task_indices = task_indices_by_epoch.get(epoch_index, [])
        if task_indices and max(join_indices) > min(task_indices):
            _fail("NONDETERMINISM")

    max_joins_per_epoch = int(pack.get("swarm", {}).get("subswarm", {}).get("max_joins_per_epoch", constants.get("SUBSWARM_MAX_JOINS_PER_EPOCH", 0)))
    join_timeout_epochs = int(pack.get("swarm", {}).get("subswarm", {}).get("join_timeout_epochs", constants.get("SUBSWARM_JOIN_TIMEOUT_EPOCHS", 0)))

    join_status_by_child: dict[str, str] = {}
    for epoch_index in sorted(epoch_begin_by_index.keys()):
        pending = [child for child, spawn_epoch in spawn_epoch_by_child.items() if spawn_epoch < epoch_index and join_status_by_child.get(child) is None]
        pending_sorted = sorted(pending, key=lambda c: (child_depth_by_child.get(c, 0), c))
        expected_children = pending_sorted[:max_joins_per_epoch] if max_joins_per_epoch else pending_sorted
        attempts = join_attempts_by_epoch.get(epoch_index, [])
        actual_children = [a.get("child_swarm_run_id") for a in attempts]
        if actual_children != expected_children:
            _fail("NONDETERMINISM")

        accept_children = {p.get("child_swarm_run_id") for p in join_accept_by_epoch.get(epoch_index, [])}
        reject_children = {p.get("child_swarm_run_id") for p in join_reject_by_epoch.get(epoch_index, [])}

        # no accept/reject without attempt
        extra = (accept_children | reject_children) - set(actual_children)
        if extra:
            _fail("SUBSWARM_DUPLICATE_JOIN")

        # validate outcomes
        for child_run_id in actual_children:
            spawn_epoch = spawn_epoch_by_child.get(child_run_id, -1)
            expected_receipt_rel = None
            for attempt in attempts:
                if attempt.get("child_swarm_run_id") == child_run_id:
                    expected_receipt_rel = attempt.get("expected_child_receipt_relpath")
                    break
            receipt_exists = False
            receipt_valid = False
            if isinstance(expected_receipt_rel, str):
                _check_relpath(expected_receipt_rel)
                receipt_path = state_dir / expected_receipt_rel
                receipt_exists = receipt_path.exists()
                if receipt_exists:
                    try:
                        child_receipt = load_canon_json(receipt_path)
                        receipt_valid = child_receipt.get("verdict") == "VALID"
                    except Exception:
                        receipt_valid = False
            timeout = join_timeout_epochs and (epoch_index - spawn_epoch) > join_timeout_epochs
            has_accept = child_run_id in accept_children
            has_reject = child_run_id in reject_children
            if not receipt_exists and not timeout:
                if has_accept or has_reject:
                    _fail("SUBSWARM_NOT_READY")
            elif timeout:
                if not has_reject:
                    _fail("SUBSWARM_TIMEOUT")
            elif receipt_valid:
                if not has_accept:
                    _fail("SUBSWARM_NOT_READY")
            else:
                if not has_reject:
                    _fail("SUBSWARM_NOT_READY")

        for child_run_id in accept_children | reject_children:
            join_status_by_child[child_run_id] = "JOINED"

    # Barrier ledger checks
    barrier_path = state_dir / "ledger" / "barrier_ledger_v3.jsonl"
    barrier_entries = load_barrier_ledger(barrier_path)
    for entry in barrier_entries:
        _scan_relpaths(entry)
    barrier_head_hash = validate_barrier_chain(barrier_entries)
    entries_by_hash = {entry.get("entry_hash"): entry for entry in barrier_entries}

    accept_ref_by_entry_hash: dict[str, dict[str, Any]] = {}
    for event in accept_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        if payload.get("accepted") is not True:
            continue
        entry_hash = payload.get("barrier_entry_hash")
        if isinstance(entry_hash, str):
            if entry_hash not in entries_by_hash:
                _fail("SWARM_EVENT_REFERENCE_MISSING")
            accept_ref = event.get("event_ref_hash")
            accept_ref_by_entry_hash[entry_hash] = event
        else:
            _fail("SCHEMA_INVALID")

    for entry in barrier_entries:
        swarm_event_ref = entry.get("swarm_event_ref_hash")
        entry_hash = entry.get("entry_hash")
        if entry_hash not in accept_ref_by_entry_hash:
            _fail("SWARM_EVENT_REFERENCE_MISSING")
        accept_event = accept_ref_by_entry_hash[entry_hash]
        accept_ref_hash = accept_event.get("event_ref_hash")
        if swarm_event_ref != accept_ref_hash:
            _fail("SWARM_EVENT_REFERENCE_MISSING")
        evidence = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else None
        if evidence is None:
            _fail("SCHEMA_INVALID")
        subswarm_prov = evidence.get("subswarm_provenance") if isinstance(evidence.get("subswarm_provenance"), dict) else None
        if subswarm_prov is None:
            _fail("SCHEMA_INVALID")
        if subswarm_prov.get("present") is True:
            join_ref = subswarm_prov.get("join_accept_event_ref_hash")
            if not isinstance(join_ref, str):
                _fail("SWARM_EVENT_REFERENCE_MISSING")
            join_event = next((e for e in join_accept_events if e.get("event_ref_hash") == join_ref), None)
            if join_event is None:
                _fail("SWARM_EVENT_REFERENCE_MISSING")
            join_payload = join_event.get("payload") or {}
            if join_payload.get("export_bundle_hash") != subswarm_prov.get("export_bundle_hash"):
                _fail("CANON_HASH_MISMATCH")
            staleness = join_payload.get("staleness") or {}
            if staleness.get("is_stale") is True:
                _fail("STALE_BASE_BARRIER_UPDATE")

    # SWARM_END head hashes
    end_payload = swarm_end_events[0].get("payload")
    if not isinstance(end_payload, dict):
        _fail("SCHEMA_INVALID")
    end_ref = compute_event_ref_hash(swarm_end_events[0])
    if end_payload.get("swarm_ledger_head_ref_hash") != end_ref:
        _fail("SWARM_LEDGER_HASH_MISMATCH")
    if end_payload.get("barrier_ledger_head_ref_hash") != barrier_head_hash:
        _fail("BARRIER_LEDGER_HASH_MISMATCH")

    # Recursive subswarm checks
    child_nodes: list[dict[str, Any]] = []
    for event in spawn_events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        child_run_id = payload.get("child_swarm_run_id")
        if not isinstance(child_run_id, str):
            _fail("SCHEMA_INVALID")
        child_pack_rel = payload.get("child_pack_relpath")
        child_out_rel = payload.get("child_out_dir_relpath")
        sponsor_agent = payload.get("sponsor_agent_id")
        if not isinstance(child_pack_rel, str) or not isinstance(child_out_rel, str) or not isinstance(sponsor_agent, str):
            _fail("SCHEMA_INVALID")
        _check_relpath(child_pack_rel)
        _check_relpath(child_out_rel)
        if not child_out_rel.startswith(f"agents/{sponsor_agent}/subswarms/sha256_"):
            _fail("PATH_TRAVERSAL")
        child_pack_path = state_dir / child_pack_rel
        if not child_pack_path.exists():
            _fail("MISSING_ARTIFACT")
        child_pack = load_canon_json(child_pack_path)
        if not isinstance(child_pack, dict):
            _fail("SCHEMA_INVALID")
        _ensure_hash_match(payload.get("child_pack_hash"), compute_pack_hash(child_pack))
        _ensure_hash_match(child_run_id, compute_swarm_run_id(child_pack))
        parent_link_payload = child_pack.get("parent_link")
        if not isinstance(parent_link_payload, dict) or parent_link_payload.get("present") is not True:
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        if parent_link_payload.get("parent_swarm_run_id") != run_id:
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        if parent_link_payload.get("parent_task_id") != payload.get("parent_task_id"):
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        if parent_link_payload.get("sponsor_agent_id") != sponsor_agent:
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        if parent_link_payload.get("spawn_event_ref_hash") != event.get("event_ref_hash"):
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        if int(parent_link_payload.get("depth", -1)) != int(payload.get("depth", -1)):
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        if int(parent_link_payload.get("subswarm_slot", -1)) != int(payload.get("subswarm_slot", -1)):
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        child_dir = state_dir / child_out_rel
        if not child_dir.exists():
            _fail("MISSING_ARTIFACT")
        # ensure child directory is within root
        try:
            child_dir.resolve().relative_to(ctx.root_dir.resolve())
        except Exception:
            _fail("PATH_TRAVERSAL")
        # record child node in tree even if not joined yet
        try:
            child_out_rel = str(child_dir.resolve().relative_to(ctx.root_dir.resolve())).replace("\\", "/")
        except Exception:
            child_out_rel = child_out_rel
        if not any(node.run_id == child_run_id for node in ctx.nodes):
            ctx.nodes.append(NodeInfo(run_id=child_run_id, parent_run_id=run_id, depth=int(payload.get("depth", 0)), out_dir_relpath=child_out_rel))

        parent_link = ParentLink(
            parent_run_id=run_id,
            parent_task_id=payload.get("parent_task_id"),
            sponsor_agent_id=sponsor_agent,
            spawn_event_ref_hash=event.get("event_ref_hash"),
            depth=int(payload.get("depth", 0)),
            subswarm_slot=int(payload.get("subswarm_slot", -1)),
        )
        child_nodes.append({
            "child_run_id": child_run_id,
            "child_dir": child_dir,
            "parent_link": parent_link,
        })

    # Recursively verify children for join accepts
    child_receipts: dict[str, dict[str, Any]] = {}
    for join_event in join_accept_events:
        payload = join_event.get("payload")
        if not isinstance(payload, dict):
            _fail("SCHEMA_INVALID")
        child_run_id = payload.get("child_swarm_run_id")
        if not isinstance(child_run_id, str):
            _fail("SCHEMA_INVALID")
        child_match = next((c for c in child_nodes if c["child_run_id"] == child_run_id), None)
        if child_match is None:
            _fail("SWARM_EVENT_REFERENCE_MISSING")
        child_dir = child_match["child_dir"]
        # receipt exists and valid
        child_receipt_rel = payload.get("child_receipt_relpath")
        if not isinstance(child_receipt_rel, str):
            _fail("SCHEMA_INVALID")
        _check_relpath(child_receipt_rel)
        receipt_path = state_dir / child_receipt_rel
        if not receipt_path.exists():
            _fail("MISSING_ARTIFACT")
        child_receipt = load_canon_json(receipt_path)
        if not isinstance(child_receipt, dict) or child_receipt.get("verdict") != "VALID":
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        # re-verify child
        child_receipt_verified = _verify_node(child_dir, ctx, expected_parent=child_match["parent_link"])
        child_receipts[child_run_id] = child_receipt_verified
        # ensure ledger heads match
        if payload.get("child_swarm_ledger_head_ref_hash") != child_receipt_verified.get("swarm_ledger_head_ref_hash"):
            _fail("SWARM_LEDGER_HASH_MISMATCH")
        if payload.get("child_barrier_ledger_head_ref_hash") != child_receipt_verified.get("barrier_ledger_head_ref_hash"):
            _fail("BARRIER_LEDGER_HASH_MISMATCH")
        # export bundle validation
        export_rel = payload.get("export_bundle_relpath")
        if not isinstance(export_rel, str):
            _fail("SCHEMA_INVALID")
        _check_relpath(export_rel)
        export_path = state_dir / export_rel
        if not export_path.exists():
            _fail("MISSING_ARTIFACT")
        export_bundle = load_canon_json(export_path)
        if not isinstance(export_bundle, dict):
            _fail("SCHEMA_INVALID")
        expected_export_hash = _compute_export_bundle_hash(export_bundle)
        if payload.get("export_bundle_hash") != expected_export_hash:
            _fail("CANON_HASH_MISMATCH")
        exports = export_bundle.get("exports")
        if not isinstance(exports, list):
            _fail("SCHEMA_INVALID")
        joined_hash = _compute_joined_artifact_set_hash(exports)
        if payload.get("joined_artifact_set_hash") != joined_hash:
            _fail("CANON_HASH_MISMATCH")
        # staleness check
        staleness = payload.get("staleness")
        if not isinstance(staleness, dict):
            _fail("SCHEMA_INVALID")
        is_stale = bool(staleness.get("is_stale"))
        at_spawn = payload.get("base_barrier_head_ref_hash_at_spawn")
        now_head = payload.get("base_barrier_head_ref_hash_now")
        if (at_spawn != now_head) != is_stale:
            _fail("STALE_BASE_BARRIER_UPDATE")

    # Non-stalling criterion for demo: barrier update accepted before join accept for at least one child
    if spawn_events and join_accept_events:
        barrier_accept_indices = [i for i, e in enumerate(events) if e.get("event_type") == "BARRIER_UPDATE_ACCEPT"]
        join_accept_indices = [i for i, e in enumerate(events) if e.get("event_type") == "SUBSWARM_JOIN_ACCEPT"]
        if barrier_accept_indices and join_accept_indices:
            if min(barrier_accept_indices) > min(join_accept_indices):
                _fail("NONDETERMINISM")

    # Build receipt
    receipt = {
        "schema": "rsi_swarm_receipt_v2",
        "spec_version": "v3_1",
        "run_id": run_id,
        "pack_hash": pack_hash,
        "constitution_hash": meta.get("META_HASH", ""),
        "verdict": "VALID",
        "reason": "OK",
        "num_agents": int(init_payload.get("num_agents", len(agents))),
        "epochs_executed": len(epoch_begin_events),
        "swarm_ledger_head_ref_hash": swarm_head_ref_hash,
        "barrier_ledger_head_ref_hash": barrier_head_hash,
    }
    return receipt


def _write_receipt(state_dir: Path, receipt: dict[str, Any]) -> None:
    out_path = state_dir / "diagnostics" / "rsi_swarm_receipt_v2.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(canon_bytes(receipt) + b"\n")


def verify(state_dir: Path, *, allow_child: bool = False) -> dict[str, Any]:
    constants = require_constants()
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

    ctx = VerifyContext(lock=lock, constants=constants, root_dir=state_dir, visited=set(), nodes=[], allow_child=allow_child)
    receipt = _verify_node(state_dir, ctx)

    # Verify swarm_tree_report_v1.json
    tree_path = state_dir / "diagnostics" / "swarm_tree_report_v1.json"
    if not tree_path.exists():
        _fail("MISSING_ARTIFACT")
    tree_report = load_canon_json(tree_path)
    if not isinstance(tree_report, dict):
        _fail("SCHEMA_INVALID")
    if tree_report.get("root_swarm_run_id") != receipt.get("run_id"):
        _fail("SUBSWARM_PARENT_LINK_MISMATCH")
    nodes_reported = tree_report.get("nodes")
    if not isinstance(nodes_reported, list):
        _fail("SCHEMA_INVALID")
    discovered = sorted(
        [(n.run_id, n.parent_run_id, n.depth, n.out_dir_relpath) for n in ctx.nodes],
        key=lambda row: row[0],
    )
    reported = sorted(
        [(n.get("swarm_run_id"), n.get("parent_swarm_run_id"), n.get("depth"), n.get("out_dir_relpath")) for n in nodes_reported],
        key=lambda row: row[0],
    )
    if discovered != reported:
        _fail("SUBSWARM_PARENT_LINK_MISMATCH")

    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify RSI swarm v3.1 run")
    parser.add_argument("--state_dir", required=True)
    parser.add_argument("--allow_child", action="store_true", help="Allow verifying a non-root node without parent context")
    args = parser.parse_args()

    try:
        receipt = verify(Path(args.state_dir), allow_child=bool(args.allow_child))
        _write_receipt(Path(args.state_dir), receipt)
    except Exception as exc:  # noqa: BLE001
        reason = str(exc) if str(exc) else "unknown"
        receipt = {
            "schema": "rsi_swarm_receipt_v2",
            "spec_version": "v3_1",
            "run_id": "",
            "pack_hash": "",
            "constitution_hash": "",
            "verdict": "INVALID",
            "reason": reason,
            "num_agents": 0,
            "epochs_executed": 0,
            "swarm_ledger_head_ref_hash": "",
            "barrier_ledger_head_ref_hash": "",
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
