"""Verifier for RSI swarm v3.3 runs (holographic consensus)."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed
from .barrier_ledger import load_barrier_ledger, validate_barrier_chain
from .constants import meta_identities, require_constants
from .immutable_core import load_lock, validate_lock, validate_receipt
from .meta_ledger import apply_meta_updates, build_meta_block, compute_update_id
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


_PATH_RE = re.compile(r"^(@ROOT/)?[A-Za-z0-9._/-]{1,512}$")


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


def _validate_path_string(path_str: str) -> None:
    if path_str.startswith("/") or path_str.startswith("\\"):
        _fail("PATH_TRAVERSAL")
    if "\\" in path_str:
        _fail("PATH_TRAVERSAL")
    if "\x00" in path_str:
        _fail("PATH_TRAVERSAL")
    if not _PATH_RE.match(path_str):
        _fail("PATH_TRAVERSAL")
    parts = path_str.split("/")
    if parts and parts[0] == "@ROOT":
        parts = parts[1:]
    if any(part == ".." for part in parts):
        _fail("PATH_TRAVERSAL")


def _resolve_path(root_dir: Path, node_dir: Path, path_str: str) -> Path:
    _validate_path_string(path_str)
    if path_str.startswith("@ROOT/"):
        rel = path_str[len("@ROOT/"):]
        base = root_dir
    else:
        rel = path_str
        base = node_dir
    target = (base / rel).resolve()
    try:
        target.relative_to(root_dir.resolve())
    except Exception:
        _fail("PATH_TRAVERSAL")
    return target


def _scan_paths(payload: Any, root_dir: Path, node_dir: Path) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, str) and (key.endswith("_relpath") or key.endswith("_path")):
                _resolve_path(root_dir, node_dir, value)
            _scan_paths(value, root_dir, node_dir)
    elif isinstance(payload, list):
        for item in payload:
            _scan_paths(item, root_dir, node_dir)


def _task_id_from_spec(task_spec: dict[str, Any]) -> str:
    return _hash_json(task_spec)


def _result_id_from_manifest(manifest: dict[str, Any]) -> str:
    return _hash_json(manifest)


def _proposal_id_from_payload(payload: dict[str, Any]) -> str:
    return _hash_json(payload)


def _load_task_spec(root_dir: Path, node_dir: Path, relpath: str) -> dict[str, Any]:
    path = _resolve_path(root_dir, node_dir, relpath)
    return _load_required_json(path)


def _load_result_manifest(root_dir: Path, node_dir: Path, relpath: str) -> dict[str, Any]:
    path = _resolve_path(root_dir, node_dir, relpath)
    return _load_required_json(path)


def _verify_artifacts(root_dir: Path, node_dir: Path, manifest: dict[str, Any]) -> None:
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
        path = _resolve_path(root_dir, node_dir, relpath)
        if not path.exists():
            _fail("MISSING_ARTIFACT")
        expected = art.get("sha256")
        if isinstance(expected, str) and expected.startswith("sha256:"):
            digest = sha256_prefixed(path.read_bytes())
            if digest != expected:
                _fail("CANON_HASH_MISMATCH")


def _verify_optional_barrier_proposal(root_dir: Path, node_dir: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
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
    path = _resolve_path(root_dir, node_dir, relpath)
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


def _compute_offer_id(offer: dict[str, Any]) -> str:
    body = dict(offer)
    body.pop("offer_id", None)
    body.pop("offer_hash", None)
    return _hash_json(body)


def _compute_imported_artifacts_set_hash(imports: list[dict[str, Any]]) -> str:
    imports_sorted = sorted(imports, key=lambda row: (row.get("blob_sha256", ""), row.get("local_blob_relpath", "")))
    payload = {"imports": imports_sorted}
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
    child_links: dict[str, "ChildLink"]
    node_receipts: dict[str, dict[str, Any]]
    root_pack: dict[str, Any] | None = None
    root_run_id: str | None = None
    root_meta_cfg: dict[str, Any] | None = None
    root_bridge_cfg: dict[str, Any] | None = None
    root_max_epochs: int = 0
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


@dataclass
class ChildLink:
    run_id: str
    node_dir: Path
    parent_link: ParentLink


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
    swarm_path = state_dir / "ledger" / "swarm_ledger_v5.jsonl"
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
    pack_path = _resolve_path(ctx.root_dir, state_dir, pack_relpath)
    pack = _load_required_json(pack_path)
    if pack.get("schema") != "rsi_real_swarm_pack_v4" or pack.get("spec_version") != "v3_3":
        _fail("SCHEMA_INVALID")
    pack_hash = compute_pack_hash(pack)
    _ensure_hash_match(init_payload.get("pack_hash"), pack_hash)

    run_id = compute_swarm_run_id(pack)
    _ensure_hash_match(init_payload.get("swarm_run_id"), run_id)

    icore_expected = init_payload.get("icore_id_expected")
    if icore_expected != ctx.lock.get("core_id"):
        _fail("SWARM_AGENT_ATTESTATION_MISMATCH")

    if expected_parent is None:
        ctx.root_pack = pack
        ctx.root_run_id = run_id
        swarm_cfg = pack.get("swarm") if isinstance(pack.get("swarm"), dict) else {}
        ctx.root_meta_cfg = swarm_cfg.get("meta") if isinstance(swarm_cfg.get("meta"), dict) else {}
        ctx.root_bridge_cfg = swarm_cfg.get("bridge") if isinstance(swarm_cfg.get("bridge"), dict) else {}
        ctx.root_max_epochs = int(swarm_cfg.get("max_epochs", 0))

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
        receipt_path = _resolve_path(ctx.root_dir, state_dir, receipt_rel)
        if not receipt_path.exists():
            _fail("IMMUTABLE_CORE_ATTESTATION_MISSING")
        try:
            agent_receipt = load_canon_json(receipt_path)
            validate_receipt(agent_receipt, ctx.lock)
        except Exception as exc:  # noqa: BLE001
            raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID") from exc
        if payload.get("core_id_observed") != icore_expected:
            _fail("SWARM_AGENT_ATTESTATION_MISMATCH")

    # Scan path strings for path traversal
    for event in events:
        payload = event.get("payload")
        if isinstance(payload, dict):
            _scan_paths(payload, ctx.root_dir, state_dir)

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
        manifest = _load_result_manifest(ctx.root_dir, state_dir, manifest_rel)
        manifest_by_result[result_id] = manifest
        _ensure_hash_match(result_id, _result_id_from_manifest(manifest))
        if manifest.get("task_id") != task_id:
            _fail("SCHEMA_INVALID")
        if manifest.get("agent_id") != payload.get("agent_id"):
            _fail("SCHEMA_INVALID")
        _verify_artifacts(ctx.root_dir, state_dir, manifest)
        proposal_payload = _verify_optional_barrier_proposal(ctx.root_dir, state_dir, manifest)
        if proposal_payload is not None:
            optional_proposal_by_result[result_id] = proposal_payload
        receipt_rel = manifest.get("agent_receipt_relpath")
        if not isinstance(receipt_rel, str):
            _fail("SCHEMA_INVALID")
        receipt_path = _resolve_path(ctx.root_dir, state_dir, receipt_rel)
        if not receipt_path.exists():
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
        task_spec = _load_task_spec(ctx.root_dir, state_dir, task_spec_rel)
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
        receipt_path = _resolve_path(ctx.root_dir, state_dir, receipt_rel)
        if not receipt_path.exists():
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
            task_spec = _load_task_spec(ctx.root_dir, state_dir, task_spec_rel)
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
        proposal_path = _resolve_path(ctx.root_dir, state_dir, relpath)
        base_head = payload.get("base_barrier_head_hash")
        task_event = results_by_id.get(result_id)
        epoch_index = int(task_event.get("payload", {}).get("epoch_index", -1)) if task_event else -1
        epoch_payload = epoch_begin_by_index.get(epoch_index)
        if not epoch_payload:
            _fail("SCHEMA_INVALID")
        if base_head != epoch_payload.get("barrier_ledger_head_hash"):
            _fail("NONDETERMINISM")
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
                receipt_path = _resolve_path(ctx.root_dir, state_dir, expected_receipt_rel)
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
    barrier_path = state_dir / "ledger" / "barrier_ledger_v5.jsonl"
    barrier_entries = load_barrier_ledger(barrier_path)
    for entry in barrier_entries:
        _scan_paths(entry, ctx.root_dir, state_dir)
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
        local_prov = evidence.get("local_provenance") if isinstance(evidence.get("local_provenance"), dict) else None
        subswarm_prov = evidence.get("subswarm_provenance") if isinstance(evidence.get("subswarm_provenance"), dict) else None
        bridge_prov = evidence.get("bridge_provenance") if isinstance(evidence.get("bridge_provenance"), dict) else None
        if local_prov is None or subswarm_prov is None or bridge_prov is None:
            _fail("SCHEMA_INVALID")

        present_flags = [
            bool(local_prov.get("present")),
            bool(subswarm_prov.get("present")),
            bool(bridge_prov.get("present")),
        ]
        present_count = sum(1 for flag in present_flags if flag)
        if present_count == 0:
            _fail("BARRIER_EVIDENCE_MISSING")
        if present_count > 1:
            _fail("BARRIER_EVIDENCE_AMBIGUOUS")

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

        if bridge_prov.get("present") is True:
            if not isinstance(bridge_prov.get("offer_id"), str):
                _fail("SCHEMA_INVALID")
            if not isinstance(bridge_prov.get("import_accept_event_ref_hash"), str):
                _fail("SCHEMA_INVALID")
            if not isinstance(bridge_prov.get("imported_artifacts_set_hash"), str):
                _fail("SCHEMA_INVALID")
            staleness = bridge_prov.get("staleness")
            if not isinstance(staleness, dict):
                _fail("SCHEMA_INVALID")
            if not isinstance(staleness.get("is_stale"), bool):
                _fail("SCHEMA_INVALID")
            if not isinstance(staleness.get("reason"), str):
                _fail("SCHEMA_INVALID")

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
        child_pack_path = _resolve_path(ctx.root_dir, state_dir, child_pack_rel)
        child_dir = _resolve_path(ctx.root_dir, state_dir, child_out_rel)
        if not child_out_rel.startswith(f"agents/{sponsor_agent}/subswarms/sha256_"):
            _fail("PATH_TRAVERSAL")
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
        existing_link = ctx.child_links.get(child_run_id)
        if existing_link and (existing_link.parent_link != parent_link or existing_link.node_dir != child_dir):
            _fail("SUBSWARM_PARENT_LINK_MISMATCH")
        if not existing_link:
            ctx.child_links[child_run_id] = ChildLink(run_id=child_run_id, node_dir=child_dir, parent_link=parent_link)
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
        receipt_path = _resolve_path(ctx.root_dir, state_dir, child_receipt_rel)
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
        export_path = _resolve_path(ctx.root_dir, state_dir, export_rel)
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
        "schema": "rsi_swarm_receipt_v5",
        "spec_version": "v3_3",
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
    ctx.node_receipts[run_id] = receipt
    return receipt


def _write_receipt(state_dir: Path, receipt: dict[str, Any]) -> None:
    out_path = state_dir / "diagnostics" / "rsi_swarm_receipt_v5.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(canon_bytes(receipt) + b"\n")


def _verify_bridge_exchange(ctx: VerifyContext, root_run_id: str) -> dict[str, dict[str, Any]]:
    exchange_dir = ctx.root_dir / "bridge_exchange"
    offers_dir = exchange_dir / "offers"
    blobs_dir = exchange_dir / "blobs"
    if not offers_dir.exists() or not blobs_dir.exists():
        _fail("MISSING_ARTIFACT")

    offers: dict[str, dict[str, Any]] = {}
    offer_paths = sorted([p for p in offers_dir.glob("sha256_*.bridge_offer_v1.json") if p.is_file()], key=lambda p: p.name)
    for offer_path in offer_paths:
        offer = load_canon_json(offer_path)
        if not isinstance(offer, dict):
            _fail("SCHEMA_INVALID")
        if offer.get("schema") != "bridge_offer_v1" or offer.get("spec_version") != "v3_2":
            _fail("SCHEMA_INVALID")
        offer_id = offer.get("offer_id")
        offer_hash = offer.get("offer_hash")
        if not isinstance(offer_id, str) or not isinstance(offer_hash, str):
            _fail("SCHEMA_INVALID")
        computed = _compute_offer_id(offer)
        if offer_id != computed or offer_hash != computed:
            _fail("BRIDGE_OFFER_HASH_MISMATCH")
        expected_name = f"sha256_{offer_id.split(':', 1)[1]}.bridge_offer_v1.json"
        if offer_path.name != expected_name:
            _fail("BRIDGE_OFFER_HASH_MISMATCH")
        if offer_id in offers:
            _fail("BRIDGE_OFFER_HASH_MISMATCH")

        publisher = offer.get("publisher")
        if not isinstance(publisher, dict):
            _fail("SCHEMA_INVALID")
        publisher_node_relpath = publisher.get("publisher_node_relpath")
        if not isinstance(publisher_node_relpath, str):
            _fail("SCHEMA_INVALID")
        _validate_path_string(publisher_node_relpath)
        if publisher_node_relpath.startswith("@ROOT/"):
            _fail("PATH_TRAVERSAL")

        artifacts = offer.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            _fail("SCHEMA_INVALID")
        for art in artifacts:
            if not isinstance(art, dict):
                _fail("SCHEMA_INVALID")
            blob_sha = art.get("blob_sha256")
            if not isinstance(blob_sha, str):
                _fail("SCHEMA_INVALID")
            blob_hex = blob_sha.split(":", 1)[1] if blob_sha.startswith("sha256:") else ""
            expected_blob_path = f"@ROOT/bridge_exchange/blobs/sha256_{blob_hex}.blob"
            exchange_blob_path = art.get("exchange_blob_path")
            if exchange_blob_path != expected_blob_path:
                _fail("BRIDGE_BLOB_HASH_MISMATCH")
            blob_path = blobs_dir / f"sha256_{blob_hex}.blob"
            if not blob_path.exists():
                _fail("MISSING_ARTIFACT")
            blob_bytes = blob_path.read_bytes()
            if art.get("bytes") != len(blob_bytes):
                _fail("BRIDGE_BLOB_HASH_MISMATCH")
            digest = sha256_prefixed(blob_bytes)
            if digest != blob_sha:
                _fail("BRIDGE_BLOB_HASH_MISMATCH")

        context = offer.get("context_requirements")
        if not isinstance(context, dict):
            _fail("SCHEMA_INVALID")
        if context.get("kind") == "NONE" and context.get("required_barrier_head_ref_hash") != "GENESIS":
            _fail("SCHEMA_INVALID")

        offers[offer_id] = offer
    return offers


def _verify_bridge_imports(ctx: VerifyContext, offers: dict[str, dict[str, Any]], root_run_id: str) -> list[dict[str, str]]:
    knowledge_edges: list[dict[str, str]] = []
    ledger_cache: dict[str, list[dict[str, Any]]] = {}

    for node in ctx.nodes:
        node_dir = ctx.root_dir / node.out_dir_relpath if node.out_dir_relpath != "." else ctx.root_dir
        ledger_path = node_dir / "ledger" / "swarm_ledger_v5.jsonl"
        events = load_swarm_ledger(ledger_path)
        ledger_cache[node.run_id] = events
        import_accepts = [e for e in events if e.get("event_type") == "BRIDGE_IMPORT_ACCEPT"]
        seen: set[str] = set()
        for event in import_accepts:
            payload = event.get("payload")
            if not isinstance(payload, dict):
                _fail("SCHEMA_INVALID")
            offer_id = payload.get("offer_id")
            if not isinstance(offer_id, str):
                _fail("SCHEMA_INVALID")
            if offer_id in seen:
                _fail("BRIDGE_DUPLICATE_ACCEPT")
            seen.add(offer_id)
            offer = offers.get(offer_id)
            if offer is None:
                _fail("MISSING_ARTIFACT")
            if offer.get("root_swarm_run_id") != root_run_id:
                _fail("BRIDGE_WRONG_ROOT")
            if offer.get("icore_id") != ctx.lock.get("core_id"):
                _fail("BRIDGE_ICORE_MISMATCH")
            offer_hex = offer_id.split(":", 1)[1]
            expected_offer_path = f"@ROOT/bridge_exchange/offers/sha256_{offer_hex}.bridge_offer_v1.json"
            if payload.get("offer_path") != expected_offer_path:
                _fail("BRIDGE_OFFER_HASH_MISMATCH")

            import_manifest_rel = payload.get("import_manifest_relpath")
            if not isinstance(import_manifest_rel, str):
                _fail("SCHEMA_INVALID")
            manifest_path = _resolve_path(ctx.root_dir, node_dir, import_manifest_rel)
            if not manifest_path.exists():
                _fail("MISSING_ARTIFACT")
            manifest = load_canon_json(manifest_path)
            if not isinstance(manifest, dict):
                _fail("SCHEMA_INVALID")
            if manifest.get("schema") != "bridge_import_manifest_v1" or manifest.get("spec_version") != "v3_2":
                _fail("SCHEMA_INVALID")
            if manifest.get("offer_id") != offer_id or manifest.get("offer_hash") != offer.get("offer_hash"):
                _fail("CANON_HASH_MISMATCH")
            imports = manifest.get("imports")
            if not isinstance(imports, list) or not imports:
                _fail("SCHEMA_INVALID")
            computed_set_hash = _compute_imported_artifacts_set_hash(imports)
            if manifest.get("imported_artifacts_set_hash") != computed_set_hash:
                _fail("CANON_HASH_MISMATCH")
            if payload.get("imported_artifacts_set_hash") != computed_set_hash:
                _fail("CANON_HASH_MISMATCH")

            offer_blobs = {art.get("blob_sha256") for art in offer.get("artifacts", []) if isinstance(art, dict)}
            for item in imports:
                if not isinstance(item, dict):
                    _fail("SCHEMA_INVALID")
                blob_sha = item.get("blob_sha256")
                if blob_sha not in offer_blobs:
                    _fail("BRIDGE_UNVERIFIED_EXPORT")
                local_rel = item.get("local_blob_relpath")
                if not isinstance(local_rel, str):
                    _fail("SCHEMA_INVALID")
                if local_rel.startswith("@ROOT/"):
                    _fail("BRIDGE_NONLOCAL_EVIDENCE")
                local_path = _resolve_path(ctx.root_dir, node_dir, local_rel)
                if not local_path.exists():
                    _fail("MISSING_ARTIFACT")
                blob_bytes = local_path.read_bytes()
                if item.get("bytes") != len(blob_bytes):
                    _fail("BRIDGE_BLOB_HASH_MISMATCH")
                if sha256_prefixed(blob_bytes) != blob_sha:
                    _fail("BRIDGE_BLOB_HASH_MISMATCH")

            import_receipt_rel = payload.get("import_receipt_relpath")
            if not isinstance(import_receipt_rel, str):
                _fail("SCHEMA_INVALID")
            receipt_path = _resolve_path(ctx.root_dir, node_dir, import_receipt_rel)
            if not receipt_path.exists():
                _fail("MISSING_ARTIFACT")
            receipt = load_canon_json(receipt_path)
            if not isinstance(receipt, dict):
                _fail("SCHEMA_INVALID")
            if receipt.get("schema") != "bridge_import_receipt_v1" or receipt.get("spec_version") != "v3_2":
                _fail("SCHEMA_INVALID")
            receipt_hash = receipt.get("receipt_hash")
            if not isinstance(receipt_hash, str):
                _fail("SCHEMA_INVALID")
            head = dict(receipt)
            head.pop("receipt_hash", None)
            if sha256_prefixed(canon_bytes(head)) != receipt_hash:
                _fail("CANON_HASH_MISMATCH")

            publisher = offer.get("publisher") or {}
            publisher_id = publisher.get("publisher_swarm_run_id")
            if not isinstance(publisher_id, str):
                _fail("SCHEMA_INVALID")
            if publisher_id not in ctx.node_receipts:
                _fail("BRIDGE_PUBLISHER_UNKNOWN")
            if ctx.node_receipts[publisher_id].get("verdict") != "VALID":
                _fail("BRIDGE_PUBLISHER_NOT_VALID")

            pub_events = ledger_cache.get(publisher_id)
            if pub_events is None:
                pub_node = next((n for n in ctx.nodes if n.run_id == publisher_id), None)
                if pub_node is None:
                    _fail("BRIDGE_PUBLISHER_UNKNOWN")
                pub_dir = ctx.root_dir / pub_node.out_dir_relpath if pub_node.out_dir_relpath != "." else ctx.root_dir
                pub_events = load_swarm_ledger(pub_dir / "ledger" / "swarm_ledger_v5.jsonl")
                ledger_cache[publisher_id] = pub_events
            ref_hash = publisher.get("publisher_result_verify_event_ref_hash")
            if not isinstance(ref_hash, str):
                _fail("SCHEMA_INVALID")
            pub_event = next((e for e in pub_events if e.get("event_ref_hash") == ref_hash), None)
            if pub_event is None or pub_event.get("event_type") != "RESULT_VERIFY":
                _fail("BRIDGE_UNVERIFIED_EXPORT")
            pub_payload = pub_event.get("payload") or {}
            if pub_payload.get("verdict") != "VALID":
                _fail("BRIDGE_UNVERIFIED_EXPORT")
            if pub_payload.get("result_id") != publisher.get("publisher_result_id"):
                _fail("BRIDGE_UNVERIFIED_EXPORT")

            knowledge_edges.append({
                "importer_swarm_run_id": node.run_id,
                "publisher_swarm_run_id": publisher_id,
                "offer_id": offer_id,
            })

    return knowledge_edges


def _verify_bridge_barrier_entries(ctx: VerifyContext, offers: dict[str, dict[str, Any]]) -> None:
    for node in ctx.nodes:
        node_dir = ctx.root_dir / node.out_dir_relpath if node.out_dir_relpath != "." else ctx.root_dir
        barrier_path = node_dir / "ledger" / "barrier_ledger_v5.jsonl"
        barrier_entries = load_barrier_ledger(barrier_path)
        swarm_events = load_swarm_ledger(node_dir / "ledger" / "swarm_ledger_v5.jsonl")
        import_accept_by_ref = {e.get("event_ref_hash"): e for e in swarm_events if e.get("event_type") == "BRIDGE_IMPORT_ACCEPT"}

        for entry in barrier_entries:
            evidence = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else None
            if evidence is None:
                _fail("SCHEMA_INVALID")
            bridge_prov = evidence.get("bridge_provenance") if isinstance(evidence.get("bridge_provenance"), dict) else None
            if not bridge_prov or bridge_prov.get("present") is not True:
                continue
            import_ref = bridge_prov.get("import_accept_event_ref_hash")
            if import_ref not in import_accept_by_ref:
                _fail("SWARM_EVENT_REFERENCE_MISSING")
            accept_event = import_accept_by_ref.get(import_ref) or {}
            accept_payload = accept_event.get("payload") or {}
            if accept_payload.get("offer_id") != bridge_prov.get("offer_id"):
                _fail("CANON_HASH_MISMATCH")
            if accept_payload.get("imported_artifacts_set_hash") != bridge_prov.get("imported_artifacts_set_hash"):
                _fail("CANON_HASH_MISMATCH")
            staleness = bridge_prov.get("staleness") or {}
            if staleness.get("is_stale") is True:
                _fail("STALE_CONTEXT_BARRIER_UPDATE")
            offer = offers.get(bridge_prov.get("offer_id"))
            if offer is not None:
                context = offer.get("context_requirements") or {}
                if context.get("kind") == "NONE" and context.get("required_barrier_head_ref_hash") != "GENESIS":
                    _fail("SCHEMA_INVALID")


def _meta_exchange_dirs(root_dir: Path) -> dict[str, Path]:
    exchange_dir = root_dir / "meta_exchange"
    return {
        "exchange_dir": exchange_dir,
        "updates_dir": exchange_dir / "updates",
        "blocks_dir": exchange_dir / "blocks",
        "state_dir": exchange_dir / "state",
        "policy_dir": exchange_dir / "policy",
    }


def _meta_evidence_validator(root_dir: Path, ref: dict[str, Any]) -> bool:
    if ref.get("kind") != "BRIDGE_OFFER_ARTIFACT":
        return False
    offer_id = ref.get("offer_id")
    blob_sha = ref.get("blob_sha256")
    if not isinstance(offer_id, str) or not isinstance(blob_sha, str):
        return False
    if not offer_id.startswith("sha256:") or not blob_sha.startswith("sha256:"):
        return False
    offer_hex = offer_id.split(":", 1)[1]
    offer_path = root_dir / "bridge_exchange" / "offers" / f"sha256_{offer_hex}.bridge_offer_v1.json"
    if not offer_path.exists():
        return False
    offer = load_canon_json(offer_path)
    if not isinstance(offer, dict):
        return False
    expected = _compute_offer_id(offer)
    if offer.get("offer_id") != expected or offer.get("offer_hash") != expected:
        return False
    artifacts = offer.get("artifacts")
    if not isinstance(artifacts, list):
        return False
    if blob_sha not in {art.get("blob_sha256") for art in artifacts if isinstance(art, dict)}:
        return False
    blob_hex = blob_sha.split(":", 1)[1]
    blob_path = root_dir / "bridge_exchange" / "blobs" / f"sha256_{blob_hex}.blob"
    if not blob_path.exists():
        return False
    if sha256_prefixed(blob_path.read_bytes()) != blob_sha:
        return False
    return True


def _load_meta_updates(
    ctx: VerifyContext,
    root_run_id: str,
    icore_id: str,
    max_epochs: int,
    meta_cfg: dict[str, Any],
) -> tuple[dict[int, list[dict[str, Any]]], dict[str, int], dict[str, str]]:
    dirs = _meta_exchange_dirs(ctx.root_dir)
    updates_dir = dirs["updates_dir"]
    if not updates_dir.exists():
        _fail("MISSING_ARTIFACT")

    topic_regex = meta_cfg.get("topic_regex") or r"^[A-Za-z0-9_.:/-]{1,64}$"
    try:
        topic_re = re.compile(topic_regex)
    except re.error:
        topic_re = re.compile(r"^[A-Za-z0-9_.:/-]{1,64}$")

    updates_by_epoch: dict[int, list[dict[str, Any]]] = {i: [] for i in range(max_epochs)}
    update_epoch: dict[str, int] = {}
    update_publishers: dict[str, str] = {}

    node_by_rel = {n.out_dir_relpath: n for n in ctx.nodes}
    ledger_cache: dict[Path, dict[str, Any]] = {}

    for update_path in sorted(updates_dir.glob("sha256_*.meta_update_v1.json")):
        update = load_canon_json(update_path)
        if not isinstance(update, dict):
            _fail("SCHEMA_INVALID")
        if update.get("schema") != "meta_update_v1" or update.get("spec_version") != "v3_3":
            _fail("SCHEMA_INVALID")
        update_id = update.get("update_id")
        update_hash = update.get("update_hash")
        if not isinstance(update_id, str) or not isinstance(update_hash, str):
            _fail("SCHEMA_INVALID")
        expected_id = compute_update_id(update)
        if update_id != expected_id or update_hash != expected_id:
            _fail("META_HASH_MISMATCH")
        name_hex = update_path.name[len("sha256_") : -len(".meta_update_v1.json")]
        if update_id != f"sha256:{name_hex}":
            _fail("META_HASH_MISMATCH")
        if update.get("root_swarm_run_id") != root_run_id:
            _fail("META_WRONG_ROOT")
        if update.get("icore_id") != icore_id:
            _fail("META_ICORE_MISMATCH")
        published_epoch = update.get("published_at_epoch_index")
        if not isinstance(published_epoch, int) or published_epoch < 0 or published_epoch >= max_epochs:
            _fail("SCHEMA_INVALID")

        topics = update.get("topics")
        if not isinstance(topics, list) or not topics or len(topics) > 32:
            _fail("SCHEMA_INVALID")
        for topic in topics:
            if not isinstance(topic, str) or not topic_re.match(topic):
                _fail("SCHEMA_INVALID")

        publisher = update.get("publisher")
        if not isinstance(publisher, dict):
            _fail("SCHEMA_INVALID")
        node_rel = publisher.get("publisher_node_relpath")
        if not isinstance(node_rel, str):
            _fail("SCHEMA_INVALID")
        node = node_by_rel.get(node_rel)
        if node is None:
            _fail("META_UNVERIFIED_UPDATE")
        if publisher.get("publisher_swarm_run_id") != node.run_id:
            _fail("META_UNVERIFIED_UPDATE")
        if int(publisher.get("publisher_depth", -1)) != int(node.depth):
            _fail("META_UNVERIFIED_UPDATE")

        node_dir = ctx.root_dir / node_rel if node_rel != "." else ctx.root_dir
        cached = ledger_cache.get(node_dir)
        if cached is None:
            events = load_swarm_ledger(node_dir / "ledger" / "swarm_ledger_v5.jsonl")
            ref_index = {e.get("event_ref_hash"): e for e in events if isinstance(e.get("event_ref_hash"), str)}
            publish_index: dict[tuple[str, int], dict[str, Any]] = {}
            for e in events:
                if e.get("event_type") == "META_UPDATE_PUBLISH":
                    payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
                    update_id_key = payload.get("update_id")
                    epoch_index = payload.get("epoch_index")
                    if isinstance(update_id_key, str) and isinstance(epoch_index, int):
                        publish_index[(update_id_key, epoch_index)] = e
            cached = {"events": events, "ref_index": ref_index, "publish_index": publish_index}
            ledger_cache[node_dir] = cached

        verify_ref = publisher.get("publisher_result_verify_event_ref_hash")
        result_id = publisher.get("publisher_result_id")
        if not isinstance(verify_ref, str) or not isinstance(result_id, str):
            _fail("META_UNVERIFIED_UPDATE")
        verify_event = cached["ref_index"].get(verify_ref)
        if not verify_event or verify_event.get("event_type") != "RESULT_VERIFY":
            _fail("META_UNVERIFIED_UPDATE")
        verify_payload = verify_event.get("payload") if isinstance(verify_event.get("payload"), dict) else {}
        if verify_payload.get("verdict") != "VALID" or verify_payload.get("result_id") != result_id:
            _fail("META_UNVERIFIED_UPDATE")

        publish_event = cached["publish_index"].get((update_id, published_epoch + 1))
        if not publish_event:
            _fail("META_UNVERIFIED_UPDATE")
        publish_payload = publish_event.get("payload") if isinstance(publish_event.get("payload"), dict) else {}
        expected_path = f"@ROOT/meta_exchange/updates/sha256_{name_hex}.meta_update_v1.json"
        if publish_payload.get("update_id") != update_id:
            _fail("META_UNVERIFIED_UPDATE")
        if publish_payload.get("update_path") != expected_path:
            _fail("META_UNVERIFIED_UPDATE")
        if publish_payload.get("update_kind") != update.get("update_kind"):
            _fail("META_UNVERIFIED_UPDATE")
        if publish_payload.get("topics") != topics:
            _fail("META_UNVERIFIED_UPDATE")

        updates_by_epoch[published_epoch].append(update)
        update_epoch[update_id] = published_epoch
        publisher_id = publisher.get("publisher_swarm_run_id")
        if isinstance(publisher_id, str):
            update_publishers[update_id] = publisher_id

    return updates_by_epoch, update_epoch, update_publishers


def _derive_meta_chain(
    ctx: VerifyContext,
    *,
    root_run_id: str,
    icore_id: str,
    max_epochs: int,
    meta_cfg: dict[str, Any],
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[str, int], dict[str, str]]:
    updates_by_epoch, update_epoch, update_publishers = _load_meta_updates(
        ctx,
        root_run_id=root_run_id,
        icore_id=icore_id,
        max_epochs=max_epochs,
        meta_cfg=meta_cfg,
    )

    dirs = _meta_exchange_dirs(ctx.root_dir)
    blocks_dir = dirs["blocks_dir"]
    state_dir = dirs["state_dir"]
    policy_dir = dirs["policy_dir"]

    prev_state = {"state_hash": "GENESIS", "knowledge_graph": {"assertions": []}}
    prev_policy = {"policy_hash": "GENESIS", "policy": {"bridge": {"subscriptions_add": []}, "task": {"priority": []}}}
    prev_block_id = "GENESIS"

    derived_blocks: dict[int, dict[str, Any]] = {}
    derived_states: dict[int, dict[str, Any]] = {}
    derived_policies: dict[int, dict[str, Any]] = {}

    allowed_kinds = set(meta_cfg.get("allowed_update_kinds") or [])
    knowledge_limits = meta_cfg.get("knowledge_limits") if isinstance(meta_cfg.get("knowledge_limits"), dict) else {}
    policy_limits = meta_cfg.get("policy_limits") if isinstance(meta_cfg.get("policy_limits"), dict) else {}
    max_apply = int(meta_cfg.get("max_updates_apply_per_epoch", 0))

    for epoch in range(max_epochs):
        updates = updates_by_epoch.get(epoch, [])
        new_state, new_policy, accepted, rejected, stats = apply_meta_updates(
            root_swarm_run_id=root_run_id,
            icore_id=icore_id,
            meta_epoch_index=epoch,
            prev_state=prev_state,
            prev_policy=prev_policy,
            updates=updates,
            knowledge_limits=knowledge_limits,
            policy_limits=policy_limits,
            allowed_update_kinds=allowed_kinds,
            max_updates_apply=max_apply,
            evidence_validator=lambda ref: _meta_evidence_validator(ctx.root_dir, ref),
        )

        state_hash = new_state.get("state_hash")
        policy_hash = new_policy.get("policy_hash")
        if not isinstance(state_hash, str) or not isinstance(policy_hash, str):
            _fail("SCHEMA_INVALID")
        state_hex = state_hash.split(":", 1)[1]
        policy_hex = policy_hash.split(":", 1)[1]
        state_path = f"@ROOT/meta_exchange/state/sha256_{state_hex}.meta_state_v1.json"
        policy_path = f"@ROOT/meta_exchange/policy/sha256_{policy_hex}.meta_policy_v1.json"

        block = build_meta_block(
            root_swarm_run_id=root_run_id,
            icore_id=icore_id,
            meta_epoch_index=epoch,
            prev_meta_block_id=prev_block_id,
            accepted_update_ids=accepted,
            rejected_updates=rejected,
            meta_state_hash=state_hash,
            meta_state_path=state_path,
            meta_policy_hash=policy_hash,
            meta_policy_path=policy_path,
            stats=stats,
        )

        # Latency checks against actual block
        block_hex = block.get("meta_block_id", "sha256:").split(":", 1)[1]
        block_path = blocks_dir / f"sha256_{block_hex}.meta_block_v1.json"
        if not block_path.exists():
            _fail("MISSING_ARTIFACT")
        actual_block = load_canon_json(block_path)
        if not isinstance(actual_block, dict):
            _fail("SCHEMA_INVALID")
        actual_ids = list(actual_block.get("accepted_update_ids", []) or [])
        actual_ids.extend([r.get("update_id") for r in actual_block.get("rejected_updates", []) if isinstance(r, dict)])
        epoch_updates = {u.get("update_id") for u in updates if isinstance(u, dict)}
        if set(actual_ids) != epoch_updates:
            _fail("META_LATENCY_VIOLATION")
        for update_id in actual_ids:
            if update_epoch.get(update_id) != epoch:
                _fail("META_LATENCY_VIOLATION")

        # Verify state/policy files exist and match
        state_file = state_dir / f"sha256_{state_hex}.meta_state_v1.json"
        policy_file = policy_dir / f"sha256_{policy_hex}.meta_policy_v1.json"
        if not state_file.exists() or not policy_file.exists():
            _fail("MISSING_ARTIFACT")
        actual_state = load_canon_json(state_file)
        actual_policy = load_canon_json(policy_file)
        if actual_state != new_state or actual_policy != new_policy:
            _fail("META_HASH_MISMATCH")

        if actual_block != block:
            _fail("META_HASH_MISMATCH")

        derived_blocks[epoch] = block
        derived_states[epoch] = new_state
        derived_policies[epoch] = new_policy
        prev_state = new_state
        prev_policy = new_policy
        prev_block_id = block.get("meta_block_id", prev_block_id)

    return derived_blocks, derived_states, derived_policies, update_epoch, update_publishers


def _verify_meta_head_declares(
    ctx: VerifyContext,
    *,
    derived_blocks: dict[int, dict[str, Any]],
    derived_states: dict[int, dict[str, Any]],
    derived_policies: dict[int, dict[str, Any]],
    max_epochs: int,
) -> dict[int, str]:
    policy_by_declared_epoch: dict[int, str] = {0: "GENESIS"}
    for idx in range(max_epochs):
        policy_by_declared_epoch[idx + 1] = derived_policies[idx].get("policy_hash", "GENESIS")

    for node in ctx.nodes:
        node_dir = ctx.root_dir / node.out_dir_relpath if node.out_dir_relpath != "." else ctx.root_dir
        events = load_swarm_ledger(node_dir / "ledger" / "swarm_ledger_v5.jsonl")
        declares: dict[int, dict[str, Any]] = {}
        for event in events:
            if event.get("event_type") != "META_HEAD_DECLARE":
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                _fail("SCHEMA_INVALID")
            declared_at = payload.get("declared_at_epoch_index")
            if not isinstance(declared_at, int):
                _fail("SCHEMA_INVALID")
            if declared_at in declares and declares[declared_at] != payload:
                _fail("META_HEAD_MISMATCH")
            declares[declared_at] = payload

        # genesis
        genesis = declares.get(0)
        if not genesis:
            _fail("META_HEAD_MISMATCH")
        expected_genesis = {
            "declared_at_epoch_index": 0,
            "meta_epoch_index": -1,
            "meta_block_id": "GENESIS",
            "meta_block_path": "GENESIS",
            "meta_state_hash": "GENESIS",
            "meta_policy_hash": "GENESIS",
        }
        if genesis != expected_genesis:
            _fail("META_HEAD_MISMATCH")

        for d in range(1, max_epochs):
            payload = declares.get(d)
            if not payload:
                _fail("META_HEAD_MISMATCH")
            meta_epoch = d - 1
            block = derived_blocks.get(meta_epoch)
            if not block:
                _fail("META_HEAD_MISMATCH")
            block_hex = block.get("meta_block_id", "sha256:").split(":", 1)[1]
            expected = {
                "declared_at_epoch_index": d,
                "meta_epoch_index": meta_epoch,
                "meta_block_id": block.get("meta_block_id"),
                "meta_block_path": f"@ROOT/meta_exchange/blocks/sha256_{block_hex}.meta_block_v1.json",
                "meta_state_hash": derived_states[meta_epoch].get("state_hash"),
                "meta_policy_hash": derived_policies[meta_epoch].get("policy_hash"),
            }
            if payload != expected:
                _fail("META_HEAD_MISMATCH")

        # finalization
        final_payload = declares.get(max_epochs)
        if not final_payload:
            _fail("META_HEAD_MISMATCH")
        final_block = derived_blocks.get(max_epochs - 1)
        if not final_block:
            _fail("META_HEAD_MISMATCH")
        final_hex = final_block.get("meta_block_id", "sha256:").split(":", 1)[1]
        expected_final = {
            "declared_at_epoch_index": max_epochs,
            "meta_epoch_index": max_epochs - 1,
            "meta_block_id": final_block.get("meta_block_id"),
            "meta_block_path": f"@ROOT/meta_exchange/blocks/sha256_{final_hex}.meta_block_v1.json",
            "meta_state_hash": derived_states[max_epochs - 1].get("state_hash"),
            "meta_policy_hash": derived_policies[max_epochs - 1].get("policy_hash"),
        }
        if final_payload != expected_final:
            _fail("META_HEAD_MISMATCH")

    return policy_by_declared_epoch


def _verify_meta_policy_imports(
    ctx: VerifyContext,
    *,
    offers: dict[str, dict[str, Any]],
    policy_by_declared_epoch: dict[int, str],
) -> None:
    for node in ctx.nodes:
        node_dir = ctx.root_dir / node.out_dir_relpath if node.out_dir_relpath != "." else ctx.root_dir
        events = load_swarm_ledger(node_dir / "ledger" / "swarm_ledger_v5.jsonl")
        init_event = events[0] if events else {}
        payload = init_event.get("payload") if isinstance(init_event.get("payload"), dict) else {}
        pack_rel = payload.get("pack_relpath")
        if not isinstance(pack_rel, str):
            _fail("SCHEMA_INVALID")
        pack = _load_required_json(_resolve_path(ctx.root_dir, node_dir, pack_rel))
        bridge_cfg = pack.get("swarm", {}).get("bridge") if isinstance(pack.get("swarm"), dict) else {}
        static_subs = bridge_cfg.get("subscriptions_static") if isinstance(bridge_cfg.get("subscriptions_static"), list) else []

        for event in events:
            if event.get("event_type") != "BRIDGE_IMPORT_ACCEPT":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            epoch_index = payload.get("epoch_index")
            offer_id = payload.get("offer_id")
            if not isinstance(epoch_index, int) or not isinstance(offer_id, str):
                _fail("SCHEMA_INVALID")
            declared_epoch = epoch_index - 1
            policy_hash = policy_by_declared_epoch.get(declared_epoch, "GENESIS")
            subscriptions = set(static_subs)
            if policy_hash != "GENESIS":
                policy_path = ctx.root_dir / "meta_exchange" / "policy" / f"sha256_{policy_hash.split(':', 1)[1]}.meta_policy_v1.json"
                policy = load_canon_json(policy_path)
                if not isinstance(policy, dict):
                    _fail("SCHEMA_INVALID")
                bridge = policy.get("policy") if isinstance(policy.get("policy"), dict) else {}
                bridge = bridge.get("bridge") if isinstance(bridge.get("bridge"), dict) else {}
                subs_add = bridge.get("subscriptions_add") if isinstance(bridge.get("subscriptions_add"), list) else []
                subscriptions.update([s for s in subs_add if isinstance(s, str)])
            offer = offers.get(offer_id)
            if offer is None:
                _fail("MISSING_ARTIFACT")
            offer_topics = offer.get("topics") if isinstance(offer.get("topics"), list) else []
            if not subscriptions.intersection(set(offer_topics)):
                _fail("META_POLICY_IMPORT_VIOLATION")


def _verify_meta_ledger_report(
    ctx: VerifyContext,
    *,
    root_run_id: str,
    icore_id: str,
    max_epochs: int,
    derived_blocks: dict[int, dict[str, Any]],
    derived_states: dict[int, dict[str, Any]],
    derived_policies: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    report_path = ctx.root_dir / "diagnostics" / "meta_ledger_report_v1.json"
    if not report_path.exists():
        _fail("MISSING_ARTIFACT")
    report = load_canon_json(report_path)
    if not isinstance(report, dict):
        _fail("SCHEMA_INVALID")

    meta_blocks = len(derived_blocks)
    meta_updates_published = 0
    seen_updates: set[str] = set()
    for node in ctx.nodes:
        node_dir = ctx.root_dir / node.out_dir_relpath if node.out_dir_relpath != "." else ctx.root_dir
        ledger_path = node_dir / "ledger" / "swarm_ledger_v5.jsonl"
        if not ledger_path.exists():
            continue
        events = load_swarm_ledger(ledger_path)
        for event in events:
            if event.get("event_type") != "META_UPDATE_PUBLISH":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            update_id = payload.get("update_id")
            if isinstance(update_id, str):
                seen_updates.add(update_id)
    meta_updates_published = len(seen_updates)

    accepted = sum(len(b.get("accepted_update_ids", []) or []) for b in derived_blocks.values())
    rejected = sum(len(b.get("rejected_updates", []) or []) for b in derived_blocks.values())

    final_block = derived_blocks.get(max_epochs - 1)
    final_meta_block_id = final_block.get("meta_block_id") if isinstance(final_block, dict) else "GENESIS"
    final_meta_state_hash = derived_states.get(max_epochs - 1, {}).get("state_hash", "GENESIS")
    final_meta_policy_hash = derived_policies.get(max_epochs - 1, {}).get("policy_hash", "GENESIS")

    omega_min = int(ctx.root_meta_cfg.get("omega_min_subscriptions", 0) if ctx.root_meta_cfg else 0)
    omega_stability = int(ctx.root_meta_cfg.get("omega_stability_epochs", 0) if ctx.root_meta_cfg else 0)
    subscriptions = []
    if isinstance(final_meta_policy_hash, str) and final_meta_policy_hash != "GENESIS":
        policy_path = ctx.root_dir / "meta_exchange" / "policy" / f"sha256_{final_meta_policy_hash.split(':', 1)[1]}.meta_policy_v1.json"
        policy = load_canon_json(policy_path)
        if isinstance(policy, dict):
            bridge = policy.get("policy") if isinstance(policy.get("policy"), dict) else {}
            bridge = bridge.get("bridge") if isinstance(bridge.get("bridge"), dict) else {}
            subscriptions = bridge.get("subscriptions_add") if isinstance(bridge.get("subscriptions_add"), list) else []
    subs_ok = len(subscriptions) >= omega_min

    stable = True
    if omega_stability:
        start_idx = max(max_epochs - omega_stability, 0)
        for idx in range(start_idx, max_epochs):
            block = derived_blocks.get(idx)
            if not block or block.get("stats", {}).get("accepted_updates", 0) != 0:
                stable = False
                break

    # final declared meta head consistency
    declared = []
    for node in ctx.nodes:
        node_dir = ctx.root_dir / node.out_dir_relpath if node.out_dir_relpath != "." else ctx.root_dir
        events = load_swarm_ledger(node_dir / "ledger" / "swarm_ledger_v5.jsonl")
        for event in events:
            if event.get("event_type") != "META_HEAD_DECLARE":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            if payload.get("declared_at_epoch_index") == max_epochs:
                declared.append(payload.get("meta_block_id"))
    declared_ok = bool(declared) and all(val == declared[0] for val in declared) and declared[0] == final_meta_block_id

    expected = {
        "schema": "meta_ledger_report_v1",
        "spec_version": "v3_3",
        "root_swarm_run_id": root_run_id,
        "icore_id": icore_id,
        "max_epochs": max_epochs,
        "meta_blocks": meta_blocks,
        "meta_updates_published": meta_updates_published,
        "meta_updates_accepted": accepted,
        "meta_updates_rejected": rejected,
        "final_meta_block_id": final_meta_block_id or "GENESIS",
        "final_meta_state_hash": final_meta_state_hash or "GENESIS",
        "final_meta_policy_hash": final_meta_policy_hash or "GENESIS",
        "omega_ready": bool(declared_ok and subs_ok and stable),
    }
    if report != expected:
        _fail("CANON_HASH_MISMATCH")
    return expected


def _verify_swarm_graph_report(
    ctx: VerifyContext,
    root_run_id: str,
    knowledge_edges: list[dict[str, str]],
    meta_edges: list[dict[str, Any]],
) -> None:
    report_path = ctx.root_dir / "diagnostics" / "swarm_graph_report_v2.json"
    if not report_path.exists():
        _fail("MISSING_ARTIFACT")
    report = load_canon_json(report_path)
    if not isinstance(report, dict):
        _fail("SCHEMA_INVALID")

    nodes_sorted = sorted(
        [
            {
                "swarm_run_id": n.run_id,
                "parent_swarm_run_id": n.parent_run_id,
                "depth": n.depth,
                "out_dir_relpath": n.out_dir_relpath,
            }
            for n in ctx.nodes
        ],
        key=lambda row: row["swarm_run_id"],
    )
    authority_edges = sorted(
        [
            {"parent_swarm_run_id": n.parent_run_id, "child_swarm_run_id": n.run_id}
            for n in ctx.nodes
            if n.parent_run_id is not None
        ],
        key=lambda row: (row["parent_swarm_run_id"], row["child_swarm_run_id"]),
    )
    knowledge_sorted = sorted(
        knowledge_edges,
        key=lambda row: (row.get("importer_swarm_run_id"), row.get("publisher_swarm_run_id"), row.get("offer_id")),
    )
    meta_sorted = sorted(
        meta_edges,
        key=lambda row: (row.get("publisher_swarm_run_id"), row.get("update_id"), int(row.get("meta_epoch_index", 0))),
    )
    expected = {
        "schema": "swarm_graph_report_v2",
        "spec_version": "v3_3",
        "root_swarm_run_id": root_run_id,
        "nodes": nodes_sorted,
        "authority_edges": authority_edges,
        "knowledge_edges": knowledge_sorted,
        "meta_edges": meta_sorted,
    }
    if report != expected:
        _fail("CANON_HASH_MISMATCH")


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

    ctx = VerifyContext(
        lock=lock,
        constants=constants,
        root_dir=state_dir,
        visited=set(),
        nodes=[],
        child_links={},
        node_receipts={},
        allow_child=allow_child,
    )

    receipt = _verify_node(state_dir, ctx)

    # Verify any remaining discovered nodes
    progress = True
    while progress:
        progress = False
        for child_run_id, link in list(ctx.child_links.items()):
            if child_run_id in ctx.visited:
                continue
            _verify_node(link.node_dir, ctx, expected_parent=link.parent_link)
            progress = True

    if allow_child:
        return receipt

    offers = _verify_bridge_exchange(ctx, receipt.get("run_id", ""))
    knowledge_edges = _verify_bridge_imports(ctx, offers, receipt.get("run_id", ""))
    _verify_bridge_barrier_entries(ctx, offers)
    meta_edges: list[dict[str, Any]] = []
    if ctx.root_meta_cfg and ctx.root_meta_cfg.get("enabled"):
        derived_blocks, derived_states, derived_policies, _, update_publishers = _derive_meta_chain(
            ctx,
            root_run_id=receipt.get("run_id", ""),
            icore_id=ctx.lock.get("core_id", ""),
            max_epochs=ctx.root_max_epochs,
            meta_cfg=ctx.root_meta_cfg,
        )
        policy_by_declared_epoch = _verify_meta_head_declares(
            ctx,
            derived_blocks=derived_blocks,
            derived_states=derived_states,
            derived_policies=derived_policies,
            max_epochs=ctx.root_max_epochs,
        )
        _verify_meta_policy_imports(
            ctx,
            offers=offers,
            policy_by_declared_epoch=policy_by_declared_epoch,
        )
        _verify_meta_ledger_report(
            ctx,
            root_run_id=receipt.get("run_id", ""),
            icore_id=ctx.lock.get("core_id", ""),
            max_epochs=ctx.root_max_epochs,
            derived_blocks=derived_blocks,
            derived_states=derived_states,
            derived_policies=derived_policies,
        )
        for epoch, block in derived_blocks.items():
            for update_id in block.get("accepted_update_ids", []) or []:
                publisher_id = update_publishers.get(update_id)
                if not publisher_id:
                    continue
                meta_edges.append(
                    {
                        "publisher_swarm_run_id": publisher_id,
                        "update_id": update_id,
                        "meta_block_id": block.get("meta_block_id"),
                        "meta_epoch_index": epoch,
                    }
                )

    _verify_swarm_graph_report(ctx, receipt.get("run_id", ""), knowledge_edges, meta_edges)

    return receipt
def main() -> None:
    parser = argparse.ArgumentParser(description="Verify RSI swarm v3.3 run")
    parser.add_argument("--state_dir", required=True)
    parser.add_argument("--allow_child", action="store_true", help="Allow verifying a non-root node without parent context")
    args = parser.parse_args()

    try:
        receipt = verify(Path(args.state_dir), allow_child=bool(args.allow_child))
        _write_receipt(Path(args.state_dir), receipt)
    except Exception as exc:  # noqa: BLE001
        reason = str(exc) if str(exc) else "unknown"
        receipt = {
            "schema": "rsi_swarm_receipt_v5",
            "spec_version": "v3_3",
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
