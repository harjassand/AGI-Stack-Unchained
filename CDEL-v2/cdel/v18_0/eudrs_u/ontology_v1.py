"""Ontology loader + deterministic dependency resolution (v1).

Phase 6 directive (normative):
  - Load an ontology handle map and its concept definitions via ArtifactRefV1.
  - Enforce GCJ-1 canonical bytes + sha256 match for every loaded artifact.
  - Validate dependency handles exist, graph is acyclic, and produce deterministic
    topological order (Kahn + ready-set ordered by handle ascending).

This module is RE2: deterministic, fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Callable, Final

from ..omega_common_v1 import OmegaV18Error, ensure_sha256, fail, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_strict

_REASON_SCHEMA_INVALID: Final[str] = "EUDRSU_MCL_SCHEMA_INVALID"
_REASON_DEP_HANDLE_MISSING: Final[str] = "EUDRSU_MCL_DEP_HANDLE_MISSING"
_REASON_DEP_CYCLE: Final[str] = "EUDRSU_MCL_DEP_CYCLE"
_REASON_HASH_MISMATCH: Final[str] = "EUDRSU_MCL_HASH_MISMATCH"

_CONCEPT_HANDLE_RE = re.compile(r"^concept/[a-z0-9][a-z0-9._/-]{0,127}$")
_OPSET_ID_RE = re.compile(r"^opset:eudrs_u_v1:sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class OntologyV1:
    handle_map_obj: dict[str, Any]
    concept_defs_by_handle: dict[str, dict[str, Any]]
    topo_order_handles: list[str]


def _sha256_prefixed(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(bytes(raw)).hexdigest()}"


def _load_gcj1_json_and_verify(*, raw: bytes, expected_artifact_id: str) -> dict[str, Any]:
    """Parse strict JSON, require GCJ-1 canonical bytes, and sha256 match."""

    if not isinstance(raw, (bytes, bytearray, memoryview)):
        fail(_REASON_SCHEMA_INVALID)
    b = bytes(raw)
    digest = _sha256_prefixed(b)
    if digest != str(expected_artifact_id).strip():
        fail(_REASON_HASH_MISMATCH)

    try:
        obj = gcj1_loads_strict(b)
    except OmegaV18Error:
        fail(_REASON_SCHEMA_INVALID)
    except Exception:  # noqa: BLE001 - fail-closed
        fail(_REASON_SCHEMA_INVALID)

    canon = gcj1_canon_bytes(obj)
    if canon != b:
        fail(_REASON_HASH_MISMATCH)

    if not isinstance(obj, dict):
        fail(_REASON_SCHEMA_INVALID)
    return dict(obj)


def _require_ascii_handle(handle: Any) -> str:
    if not isinstance(handle, str) or not handle:
        fail(_REASON_SCHEMA_INVALID)
    try:
        handle.encode("ascii", errors="strict")
    except Exception:
        fail(_REASON_SCHEMA_INVALID)
    if _CONCEPT_HANDLE_RE.fullmatch(handle) is None:
        fail(_REASON_SCHEMA_INVALID)
    return handle


def _require_concept_def_v1(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        fail(_REASON_SCHEMA_INVALID)

    try:
        validate_schema(obj, "concept_def_v1")
    except Exception:  # noqa: BLE001 - fail-closed
        fail(_REASON_SCHEMA_INVALID)

    schema_id = str(obj.get("schema_id", "")).strip()
    if schema_id != "concept_def_v1":
        fail(_REASON_SCHEMA_INVALID)

    concept_id = ensure_sha256(obj.get("concept_id"), reason=_REASON_SCHEMA_INVALID)
    dc1_id = str(obj.get("dc1_id", "")).strip()
    if dc1_id != "dc1:q32_v1":
        fail(_REASON_SCHEMA_INVALID)

    opset_id = str(obj.get("opset_id", "")).strip()
    if _OPSET_ID_RE.fullmatch(opset_id) is None:
        fail(_REASON_SCHEMA_INVALID)

    handle = _require_ascii_handle(obj.get("handle"))

    deps_raw = obj.get("deps")
    if not isinstance(deps_raw, list):
        fail(_REASON_SCHEMA_INVALID)
    deps: list[str] = []
    prev: str | None = None
    seen: set[str] = set()
    for item in deps_raw:
        h = _require_ascii_handle(item)
        if prev is not None and h < prev:
            fail(_REASON_SCHEMA_INVALID)
        prev = h
        if h in seen:
            fail(_REASON_SCHEMA_INVALID)
        seen.add(h)
        deps.append(h)

    shard_ref = require_artifact_ref_v1(obj.get("shard_ref"), reason=_REASON_SCHEMA_INVALID)
    if not str(shard_ref.get("artifact_relpath", "")).endswith(".concept_shard_v1.bin"):
        fail(_REASON_SCHEMA_INVALID)

    unify_caps_raw = obj.get("unify_caps")
    if not isinstance(unify_caps_raw, dict):
        fail(_REASON_SCHEMA_INVALID)
    if set(unify_caps_raw.keys()) != {"region_node_cap_u32", "backtrack_step_cap_u32", "candidate_leaf_cap_u32"}:
        fail(_REASON_SCHEMA_INVALID)

    def _cap(name: str) -> int:
        v = unify_caps_raw.get(name)
        if not isinstance(v, int) or v < 1:
            fail(_REASON_SCHEMA_INVALID)
        if v > 0xFFFFFFFF:
            fail(_REASON_SCHEMA_INVALID)
        return int(v)

    region_node_cap_u32 = _cap("region_node_cap_u32")
    if region_node_cap_u32 > 64:
        fail(_REASON_SCHEMA_INVALID)
    _cap("backtrack_step_cap_u32")
    _cap("candidate_leaf_cap_u32")

    # Self-hash check for concept_id (normative).
    tmp = dict(obj)
    tmp["concept_id"] = "sha256:" + ("0" * 64)
    computed = _sha256_prefixed(gcj1_canon_bytes(tmp))
    if computed != concept_id:
        fail(_REASON_SCHEMA_INVALID)

    return dict(obj)


def load_ontology_v1(oroot_ref: dict, registry_load_bytes: Callable[[dict[str, str]], bytes]) -> OntologyV1:
    if not callable(registry_load_bytes):
        fail(_REASON_SCHEMA_INVALID)

    oroot = require_artifact_ref_v1(oroot_ref, reason=_REASON_SCHEMA_INVALID)
    raw = registry_load_bytes(oroot)
    handle_map_obj = _load_gcj1_json_and_verify(raw=raw, expected_artifact_id=oroot["artifact_id"])

    try:
        validate_schema(handle_map_obj, "ontology_handle_map_v1")
    except Exception:  # noqa: BLE001 - fail-closed
        fail(_REASON_SCHEMA_INVALID)

    if str(handle_map_obj.get("schema_id", "")).strip() != "ontology_handle_map_v1":
        fail(_REASON_SCHEMA_INVALID)
    if str(handle_map_obj.get("dc1_id", "")).strip() != "dc1:q32_v1":
        fail(_REASON_SCHEMA_INVALID)
    opset_id = str(handle_map_obj.get("opset_id", "")).strip()
    if _OPSET_ID_RE.fullmatch(opset_id) is None:
        fail(_REASON_SCHEMA_INVALID)
    epoch_u64 = handle_map_obj.get("epoch_u64")
    if not isinstance(epoch_u64, int) or epoch_u64 < 0:
        fail(_REASON_SCHEMA_INVALID)

    concepts_raw = handle_map_obj.get("concepts")
    if not isinstance(concepts_raw, list):
        fail(_REASON_SCHEMA_INVALID)

    # Enforce deterministic ordering + uniqueness.
    concept_defs_by_handle: dict[str, dict[str, Any]] = {}
    prev_handle: str | None = None
    for row in concepts_raw:
        if not isinstance(row, dict) or set(row.keys()) != {"handle", "concept_def_ref"}:
            fail(_REASON_SCHEMA_INVALID)
        handle = _require_ascii_handle(row.get("handle"))
        if prev_handle is not None and handle <= prev_handle:
            fail(_REASON_SCHEMA_INVALID)
        prev_handle = handle

        ref = require_artifact_ref_v1(row.get("concept_def_ref"), reason=_REASON_SCHEMA_INVALID)
        raw_def = registry_load_bytes(ref)
        def_obj = _load_gcj1_json_and_verify(raw=raw_def, expected_artifact_id=ref["artifact_id"])
        def_obj = _require_concept_def_v1(def_obj)

        if str(def_obj.get("handle", "")).strip() != handle:
            fail(_REASON_SCHEMA_INVALID)

        if handle in concept_defs_by_handle:
            fail(_REASON_SCHEMA_INVALID)
        concept_defs_by_handle[handle] = dict(def_obj)

    # Dependency existence checks.
    handles = sorted(concept_defs_by_handle.keys())
    handle_set = set(handles)
    for h, obj in concept_defs_by_handle.items():
        deps = obj.get("deps", [])
        if not isinstance(deps, list):
            fail(_REASON_SCHEMA_INVALID)
        for dep_h in deps:
            if dep_h not in handle_set:
                fail(_REASON_DEP_HANDLE_MISSING)

    # Kahn topological order on edges concept -> dep (concept depends on dep).
    indeg: dict[str, int] = {h: 0 for h in handles}
    out_edges: dict[str, list[str]] = {h: [] for h in handles}
    for h in handles:
        deps = concept_defs_by_handle[h].get("deps", [])
        if not isinstance(deps, list):
            fail(_REASON_SCHEMA_INVALID)
        for dep_h in deps:
            # Edge: h -> dep_h
            out_edges[h].append(str(dep_h))
            indeg[str(dep_h)] = int(indeg.get(str(dep_h), 0)) + 1

    ready = [h for h in handles if int(indeg.get(h, 0)) == 0]
    ready.sort()

    topo: list[str] = []
    while ready:
        cur = ready.pop(0)  # ready set kept sorted => deterministic min selection.
        topo.append(cur)
        for nxt in out_edges.get(cur, []):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                ready.append(nxt)
        ready.sort()

    if len(topo) != len(handles):
        fail(_REASON_DEP_CYCLE)

    return OntologyV1(
        handle_map_obj=dict(handle_map_obj),
        concept_defs_by_handle=dict(concept_defs_by_handle),
        topo_order_handles=list(topo),
    )


def resolve_concept_by_handle_v1(ont: OntologyV1, handle: str) -> dict:
    if not isinstance(ont, OntologyV1) or not isinstance(handle, str):
        fail(_REASON_SCHEMA_INVALID)
    obj = ont.concept_defs_by_handle.get(str(handle))
    if obj is None:
        fail(_REASON_DEP_HANDLE_MISSING)
    return dict(obj)


def topo_order_concepts_v1(ont: OntologyV1) -> list[str]:
    if not isinstance(ont, OntologyV1):
        fail(_REASON_SCHEMA_INVALID)
    return list(ont.topo_order_handles)


__all__ = [
    "OntologyV1",
    "load_ontology_v1",
    "resolve_concept_by_handle_v1",
    "topo_order_concepts_v1",
]

