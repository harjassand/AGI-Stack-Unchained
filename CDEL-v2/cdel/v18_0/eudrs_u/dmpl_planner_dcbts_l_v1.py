"""DMPL deterministic planner: DCBTS-L (v1, Phase 2).

Implements the Phase 2 frozen contract for:
  - Action enumeration (enum retrieval + NOOP/USE_CONCEPT actions, aHash ordering).
  - Layered expansions with beam pruning.
  - Replayable rollout traces under mroot (TraceWriterV1).
  - ActionReceipt emission (dmpl_action_receipt_v1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..omega_common_v1 import OmegaV18Error, require_no_absolute_paths, validate_schema
from .dmpl_action_encode_v1 import actenc_det_v1, hash_action_record_v1, make_noop_action_v1, make_use_concept_action_v1
from .dmpl_action_receipt_v1 import emit_action_receipt_v1
from .dmpl_config_load_v1 import DmplRuntime
from .dmpl_gate_v1 import gate_det_v1
from .dmpl_patch_compose_v1 import z_transition_det_v1
from .dmpl_retrieve_v1 import retrieve_det_v1
from .dmpl_reward_proxy_v1 import ufc_proxy_v1
from .dmpl_tensor_io_v1 import parse_tensor_q32_v1, require_shape
from .dmpl_trace_v1 import TraceWriterV1
from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_BUDGET_EXCEEDED,
    DMPL_E_CONCEPT_PATCH_POLICY_VIOLATION,
    DMPL_E_DIM_MISMATCH,
    DMPL_E_DISABLED,
    DMPL_E_HASH_MISMATCH,
    DMPL_E_NONCANON_GCJ1,
    DMPL_E_OPSET_MISMATCH,
    DMPL_OK,
    Q32_ONE,
    _active_artifact_writer,
    _reset_active_artifact_writer,
    _reset_active_op_counter,
    _reset_active_resolver,
    _set_active_artifact_writer,
    _set_active_op_counter,
    _set_active_resolver,
    _sha25632_count,
    _sha256_id_from_hex_digest32,
    _sha256_id_to_digest32,
    _u32_le,
    _add_sat_count,
    _mul_q32_count,
)
from .dmpl_value_v1 import value_det_v1
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical

_Z_HASH_PREFIX = b"DMPL/Z/v1\x00"
_SHA256_ZERO_ID = "sha256:" + ("0" * 64)


@dataclass(frozen=True, slots=True)
class PlanResultV1:
    chosen_action_record_id: str
    chosen_action_hash_id: str
    chosen_action_hash32: bytes
    chosen_node_id: str
    rollout_trace_id: str
    action_receipt_id: str


@dataclass(slots=True)
class _PlanCounters:
    nodes_u32: int = 0
    ops_u64: int = 0
    bytes_u64: int = 0


@dataclass(frozen=True, slots=True)
class _Node:
    node_id: str
    parent_id: str
    depth_u32: int
    ladder_level_u32: int
    z_vec: list[int]
    z_hash_id: str
    action_hash_id: str
    action_record_id: str
    retrieval_result_digest: str
    gate_digest: str
    subplan_id: str
    prefix_score_q32: int
    bound_score_q32: int


def _require_sha256_id(value: Any, *, reason: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != (len("sha256:") + 64):
        raise DMPLError(reason_code=reason, details={"value": str(value)})
    try:
        bytes.fromhex(value.split(":", 1)[1])
    except Exception:
        raise DMPLError(reason_code=reason, details={"value": str(value)})
    return str(value)


def _resolver_load_bytes(resolver: Any, *, artifact_id: str, artifact_type: str, ext: str) -> bytes:
    try:
        fn = getattr(resolver, "load_artifact_bytes")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver missing load_artifact_bytes"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver.load_artifact_bytes not callable"})
    raw = fn(artifact_id=str(artifact_id), artifact_type=str(artifact_type), ext=str(ext))
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "resolver returned non-bytes"})
    return bytes(raw)


def _writer_write_json(writer: Any, artifact_type: str, obj: Any) -> str:
    try:
        fn = getattr(writer, "write_json_artifact")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "writer missing write_json_artifact"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "writer.write_json_artifact not callable"})
    out_id = fn(str(artifact_type), obj)
    return _require_sha256_id(out_id, reason=DMPL_E_HASH_MISMATCH)


def _writer_write_bin(writer: Any, artifact_type: str, raw: bytes) -> str:
    try:
        fn = getattr(writer, "write_bin_artifact")
    except Exception:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "writer missing write_bin_artifact"})
    if not callable(fn):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "writer.write_bin_artifact not callable"})
    out_id = fn(str(artifact_type), bytes(raw))
    return _require_sha256_id(out_id, reason=DMPL_E_HASH_MISMATCH)


def _z_hash_id_and_digest32(z_vec: list[int]) -> tuple[str, bytes]:
    b = bytearray()
    b += _Z_HASH_PREFIX
    for v in z_vec:
        # i64 little-endian (two's complement).
        b += int(v).to_bytes(8, byteorder="little", signed=True)
    digest32 = _sha25632_count(bytes(b))
    return _sha256_id_from_hex_digest32(digest32), bytes(digest32)


def _node_id_from_fields(
    *,
    parent_id: str,
    depth_u32: int,
    ladder_level_u32: int,
    s_hash_id: str,
    z_hash_id: str,
    action_hash_id: str,
    retrieval_result_digest: str,
    gate_digest: str,
    subplan_id: str,
) -> str:
    node_obj = {
        "schema_id": "dmpl_nodehash_v1",
        "parent_id": str(parent_id),
        "depth_u32": int(depth_u32) & 0xFFFFFFFF,
        "ladder_level_u32": int(ladder_level_u32) & 0xFFFFFFFF,
        "s_hash": str(s_hash_id),
        "z_hash": str(z_hash_id),
        "action_hash": str(action_hash_id),
        "retrieval_result_digest": str(retrieval_result_digest),
        "gate_digest": str(gate_digest),
        "subplan_id": str(subplan_id),
    }
    digest32 = _sha25632_count(gcj1_canon_bytes(node_obj))
    return _sha256_id_from_hex_digest32(digest32)


def _record_order_key(node: _Node) -> tuple[int, int, str]:
    # bound desc, depth asc, node_id asc
    return (-int(node.bound_score_q32), int(node.depth_u32), str(node.node_id))


def _finalize_expand_record_with_counters(
    *,
    record_base: dict[str, Any],
    counters: _PlanCounters,
    ops_next_u64: int,
    nodes_next_u32: int,
    caps: dict[str, Any],
    ops_before_expand_u64: int,
) -> dict[str, Any]:
    # Fixed-point for bytes_u64 due to self-referential cap_counters.
    bytes0 = int(counters.bytes_u64)
    guess = bytes0
    final_obj: dict[str, Any] | None = None
    for _ in range(12):
        cap_counters = {"ops_u64": int(ops_next_u64), "bytes_u64": int(guess), "nodes_u32": int(nodes_next_u32)}
        rec = dict(record_base)
        rec["cap_counters"] = cap_counters
        enc = gcj1_canon_bytes(rec)
        enc_len = 4 + len(enc)
        bytes_next = bytes0 + int(enc_len)
        if bytes_next == guess:
            final_obj = rec
            break
        guess = bytes_next
    if final_obj is None:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bytes fixed-point did not converge"})

    # Caps enforcement (hard fail).
    Nmax = int(caps.get("Nmax_u32", 0))
    max_trace_bytes = int(caps.get("max_trace_bytes_u32", 0))
    max_node_ops = int(caps.get("max_node_opcount_u64", 0))
    max_total_ops = int(caps.get("max_total_opcount_u64", 0))

    if int(nodes_next_u32) > int(Nmax):
        raise DMPLError(reason_code=DMPL_E_BUDGET_EXCEEDED, details={"hint": "nodes cap", "nodes": int(nodes_next_u32), "Nmax": int(Nmax)})
    if int(final_obj["cap_counters"]["bytes_u64"]) > int(max_trace_bytes):
        raise DMPLError(
            reason_code=DMPL_E_BUDGET_EXCEEDED,
            details={"hint": "bytes cap", "bytes": int(final_obj["cap_counters"]["bytes_u64"]), "cap": int(max_trace_bytes)},
        )
    if int(ops_next_u64) > int(max_total_ops):
        raise DMPLError(reason_code=DMPL_E_BUDGET_EXCEEDED, details={"hint": "total ops cap", "ops": int(ops_next_u64), "cap": int(max_total_ops)})

    per_node_ops = int(ops_next_u64) - int(ops_before_expand_u64)
    if per_node_ops > int(max_node_ops):
        raise DMPLError(reason_code=DMPL_E_BUDGET_EXCEEDED, details={"hint": "node ops cap", "ops": int(per_node_ops), "cap": int(max_node_ops)})

    return final_obj


def plan_call_v1(runtime: DmplRuntime, plan_query_obj: dict, resolver, artifact_writer) -> PlanResultV1:
    if not isinstance(runtime, DmplRuntime):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "runtime type"})
    if not isinstance(plan_query_obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "plan_query_obj type"})

    # Phase 2: if disabled, fail closed and write nothing.
    if not bool(runtime.config.get("enabled_b", False)):
        raise DMPLError(reason_code=DMPL_E_DISABLED, details={})

    # Install resolver + writer + op counter for this call.
    counters = _PlanCounters()
    tok_ops = _set_active_op_counter(counters)
    tok_res = _set_active_resolver(resolver)
    tok_wr = _set_active_artifact_writer(artifact_writer)

    try:
        # Validate PlanQuery schema and bindings.
        try:
            validate_schema(plan_query_obj, "dmpl_plan_query_v1")
        except Exception:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "plan_query schema"})

        if str(plan_query_obj.get("schema_id", "")).strip() != "dmpl_plan_query_v1":
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "schema_id"})
        if str(plan_query_obj.get("dc1_id", "")).strip() != str(runtime.dc1_id).strip():
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "dc1 mismatch"})
        if str(plan_query_obj.get("opset_id", "")).strip() != str(runtime.opset_id).strip():
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "opset mismatch"})

        plan_query_id = _sha256_id_from_hex_digest32(_sha25632_count(gcj1_canon_bytes(plan_query_obj)))

        dmpl_droot_id = _require_sha256_id(plan_query_obj.get("dmpl_droot_id"), reason=DMPL_E_OPSET_MISMATCH)
        if str(dmpl_droot_id).strip() != str(runtime.droot_id).strip():
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "droot bind"})

        start_state_id = _require_sha256_id(plan_query_obj.get("start_state_id"), reason=DMPL_E_OPSET_MISMATCH)
        state_hash32 = _sha256_id_to_digest32(start_state_id, reason=DMPL_E_HASH_MISMATCH)
        s_hash_id = _sha256_id_from_hex_digest32(state_hash32)

        z0_tensor_bin_id = _require_sha256_id(plan_query_obj.get("z0_tensor_bin_id"), reason=DMPL_E_OPSET_MISMATCH)
        z0_raw = _resolver_load_bytes(resolver, artifact_id=z0_tensor_bin_id, artifact_type="dmpl_tensor_q32_v1", ext="bin")
        if _sha256_id_from_hex_digest32(_sha25632_count(z0_raw)) != str(z0_tensor_bin_id).strip():
            raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "z0 bin hash"})
        dims, z0_vals = parse_tensor_q32_v1(z0_raw)
        require_shape(dims, [int(runtime.dims.d_u32)])
        z0_vec = [int(v) for v in z0_vals]
        z0_hash_id, z0_hash32 = _z_hash_id_and_digest32(z0_vec)

        planner_spec = runtime.config.get("planner_spec")
        if not isinstance(planner_spec, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "planner_spec"})
        ladder_policy = planner_spec.get("ladder_policy")
        if not isinstance(ladder_policy, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "ladder_policy"})
        if bool(ladder_policy.get("refine_enabled_b", False)):
            # Phase 2: coarse-only planner.
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "refine not supported in Phase 2"})
        ladder_level_u32 = int(ladder_policy.get("ell_lo_u32", 0)) & 0xFFFFFFFF

        caps = dict(runtime.caps)
        H_u32 = int(caps.get("H_u32", 0))
        Nmax_u32 = int(caps.get("Nmax_u32", 0))
        Ka_u32 = int(caps.get("Ka_u32", 0))
        beam_width_u32 = int(caps.get("beam_width_u32", 0))

        # Precompute gamma_pow[0..H] (Q32).
        obj_spec = runtime.config.get("objective_spec")
        if not isinstance(obj_spec, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "objective_spec"})
        gamma_q32_obj = obj_spec.get("gamma_q32")
        if not isinstance(gamma_q32_obj, dict) or set(gamma_q32_obj.keys()) != {"q"}:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "gamma_q32"})
        gamma_q32 = int(gamma_q32_obj.get("q", 0))
        gamma_pow: list[int] = [int(Q32_ONE)]
        for _t in range(int(H_u32)):
            gamma_pow.append(_mul_q32_count(int(gamma_pow[-1]), int(gamma_q32)))

        # Trace writer (records emitted during expansions).
        trace = TraceWriterV1(plan_query_id=str(plan_query_id), modelpack_hash32=bytes(runtime.modelpack_hash32), opset_id=str(runtime.opset_id))

        # Root node.
        root_node_id = _node_id_from_fields(
            parent_id="",
            depth_u32=0,
            ladder_level_u32=ladder_level_u32,
            s_hash_id=str(s_hash_id),
            z_hash_id=str(z0_hash_id),
            action_hash_id="",
            retrieval_result_digest=_SHA256_ZERO_ID,
            gate_digest=_SHA256_ZERO_ID,
            subplan_id="",
        )
        root = _Node(
            node_id=str(root_node_id),
            parent_id="",
            depth_u32=0,
            ladder_level_u32=ladder_level_u32,
            z_vec=z0_vec,
            z_hash_id=str(z0_hash_id),
            action_hash_id="",
            action_record_id="",
            retrieval_result_digest=_SHA256_ZERO_ID,
            gate_digest=_SHA256_ZERO_ID,
            subplan_id="",
            prefix_score_q32=0,
            bound_score_q32=0,
        )

        nodes_by_id: dict[str, _Node] = {str(root.node_id): root}
        open_list: list[_Node] = [root]

        # Concept loader for patch/value stages (concept shard JSON by id).
        concept_cache: dict[str, dict[str, Any]] = {}

        def _concept_loader(concept_shard_id: str) -> dict[str, Any]:
            cid = str(concept_shard_id)
            hit = concept_cache.get(cid)
            if hit is not None:
                return hit
            raw = _resolver_load_bytes(resolver, artifact_id=cid, artifact_type="dmpl_concept_shard_v1", ext="json")
            if _sha256_id_from_hex_digest32(_sha25632_count(raw)) != cid:
                raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "concept shard hash"})
            try:
                obj = gcj1_loads_and_verify_canonical(raw)
            except OmegaV18Error:
                raise DMPLError(reason_code=DMPL_E_NONCANON_GCJ1, details={"hint": "concept shard noncanon"})
            if not isinstance(obj, dict):
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "concept shard not dict"})
            require_no_absolute_paths(obj)
            try:
                validate_schema(obj, "dmpl_concept_shard_v1")
            except Exception:
                raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "concept shard schema"})
            concept_cache[cid] = dict(obj)
            return concept_cache[cid]

        # Main loop.
        a_hash32_enum = b"\x00" * 32
        while True:
            if not open_list:
                break
            open_list.sort(key=_record_order_key)
            best = open_list[0]

            if int(best.depth_u32) == int(H_u32):
                break
            if int(counters.nodes_u32) == int(Nmax_u32):
                break

            # Expand the shallowest layer present.
            min_depth = min(int(n.depth_u32) for n in open_list)
            layer = [n for n in open_list if int(n.depth_u32) == int(min_depth)]
            rest = [n for n in open_list if int(n.depth_u32) != int(min_depth)]
            layer.sort(key=_record_order_key)
            open_list = rest

            for parent in layer:
                if int(counters.nodes_u32) == int(Nmax_u32):
                    break
                if int(parent.depth_u32) >= int(H_u32):
                    continue

                z_t = list(parent.z_vec)
                z_t_hash32 = _sha256_id_to_digest32(parent.z_hash_id, reason=DMPL_E_HASH_MISMATCH)

                # Enum retrieval for candidate pool (a_hash32 = zero32).
                C_enum = retrieve_det_v1(runtime, state_hash32, z_t_hash32, a_hash32_enum, int(parent.ladder_level_u32))

                # Candidate actions: NOOP + up to Ka-1 USE_CONCEPT.
                actions: list[dict[str, Any]] = [make_noop_action_v1(runtime.dc1_id, runtime.opset_id)]
                limit = max(0, int(Ka_u32) - 1)
                for i, it in enumerate(list(C_enum.items)):
                    if i >= limit:
                        break
                    actions.append(make_use_concept_action_v1(runtime.dc1_id, runtime.opset_id, i, str(it.concept_shard_id), int(parent.ladder_level_u32)))

                # Deterministic action ordering by aHash asc; take first Ka.
                actions_h: list[tuple[str, bytes, dict[str, Any]]] = []
                for a in actions:
                    a_hash_id, a_hash32 = hash_action_record_v1(a)
                    actions_h.append((str(a_hash_id), bytes(a_hash32), dict(a)))
                actions_h.sort(key=lambda row: str(row[0]))
                if int(Ka_u32) >= 0:
                    actions_h = actions_h[: int(Ka_u32)]

                for a_hash_id, a_hash32, action_obj in actions_h:
                    if int(counters.nodes_u32) == int(Nmax_u32):
                        break

                    # Per-EXPAND opcount starts after enum retrieval + action enumeration.
                    ops_before_expand = int(counters.ops_u64)

                    # Store action record as an artifact.
                    action_record_id = _writer_write_json(artifact_writer, "dmpl_action_v1", action_obj)
                    if str(action_record_id).strip() != str(a_hash_id).strip():
                        raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "action id mismatch"})

                    # ActEncDet: u in Q32^p.
                    u_t = actenc_det_v1(a_hash32, int(runtime.dims.p_u32))

                    # Action-specific retrieval/gate/transition/value.
                    retrieved = retrieve_det_v1(runtime, state_hash32, z_t_hash32, a_hash32, int(parent.ladder_level_u32))
                    gate = gate_det_v1(runtime, z_t, retrieved)
                    z_tp1 = z_transition_det_v1(runtime, z_t, u_t, gate, int(parent.ladder_level_u32), _concept_loader)
                    r_hat_q32, _ufc_terms = ufc_proxy_v1(runtime, state_hash32, z_t, a_hash32, z_tp1)
                    v_tp1_q32 = value_det_v1(runtime, z_tp1, gate, int(parent.ladder_level_u32), _concept_loader)

                    d_parent = int(parent.depth_u32)
                    prefix_child = _add_sat_count(int(parent.prefix_score_q32), _mul_q32_count(int(gamma_pow[d_parent]), int(r_hat_q32)))
                    bound_child = _add_sat_count(int(prefix_child), _mul_q32_count(int(gamma_pow[d_parent + 1]), int(v_tp1_q32)))

                    z_tp1_hash_id, _z_tp1_hash32 = _z_hash_id_and_digest32(z_tp1)

                    child_depth = int(parent.depth_u32) + 1
                    node_id = _node_id_from_fields(
                        parent_id=str(parent.node_id),
                        depth_u32=int(child_depth),
                        ladder_level_u32=int(parent.ladder_level_u32),
                        s_hash_id=str(s_hash_id),
                        z_hash_id=str(z_tp1_hash_id),
                        action_hash_id=str(a_hash_id),
                        retrieval_result_digest=str(retrieved.retrieval_result_digest),
                        gate_digest=str(gate.gate_digest),
                        subplan_id="",
                    )

                    # Build EXPAND record (cap counters filled via fixed-point).
                    record_base: dict[str, Any] = {
                        "record_kind": "EXPAND",
                        "node_id": str(node_id),
                        "parent_id": str(parent.node_id),
                        "depth_u32": int(child_depth) & 0xFFFFFFFF,
                        "ladder_level_u32": int(parent.ladder_level_u32) & 0xFFFFFFFF,
                        "z_t_hash": str(parent.z_hash_id),
                        "action_hash": str(a_hash_id),
                        "action_record_id": str(action_record_id),
                        "retrieval_query_digest": str(retrieved.retrieval_query_digest),
                        "retrieval_result_digest": str(retrieved.retrieval_result_digest),
                        "retrieval_trace_root": str(retrieved.retrieval_trace_root_id),
                        "gate_digest": str(gate.gate_digest),
                        "gate_active": [{"concept_shard_id": str(g.concept_shard_id), "w_q32": {"q": int(g.w_q32)}} for g in gate.gate_active],
                        "z_tp1_hash": str(z_tp1_hash_id),
                        "r_hat_q32": {"q": int(r_hat_q32)},
                        "v_tp1_q32": {"q": int(v_tp1_q32)},
                        "prefix_score_q32": {"q": int(prefix_child)},
                        "bound_score_q32": {"q": int(bound_child)},
                        # cap_counters inserted below
                        "rev_err_q32": {"q": 0},
                        "subplan_id": "",
                    }

                    nodes_next = int(counters.nodes_u32) + 1

                    # Cap counters: TraceWriter.append_record adds 2 sha ops, plus 1 more if it must flush
                    # a non-empty chunk before appending this record. Because flush depends on the encoded
                    # record length (which depends on cap counters), resolve this deterministically by
                    # trying both deltas and selecting the one consistent with TraceWriter's preview.
                    ops_base = int(counters.ops_u64)
                    record_obj: dict[str, Any] | None = None
                    for op_delta in (2, 3):
                        ops_next = ops_base + int(op_delta)
                        candidate = _finalize_expand_record_with_counters(
                            record_base=record_base,
                            counters=counters,
                            ops_next_u64=int(ops_next),
                            nodes_next_u32=int(nodes_next),
                            caps=caps,
                            ops_before_expand_u64=int(ops_before_expand),
                        )
                        if int(trace.preview_append_op_delta_v1(candidate)) == int(op_delta):
                            record_obj = candidate
                            break
                    if record_obj is None:
                        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "trace op delta mismatch"})

                    # Append to trace (bumps ops by the previewed delta).
                    trace.append_record(record_obj)

                    # Update cumulative counters (nodes/bytes; ops updated via context wrapper).
                    counters.nodes_u32 = int(nodes_next)
                    counters.bytes_u64 = int(record_obj["cap_counters"]["bytes_u64"])

                    # Record child node.
                    child = _Node(
                        node_id=str(node_id),
                        parent_id=str(parent.node_id),
                        depth_u32=int(child_depth),
                        ladder_level_u32=int(parent.ladder_level_u32),
                        z_vec=z_tp1,
                        z_hash_id=str(z_tp1_hash_id),
                        action_hash_id=str(a_hash_id),
                        action_record_id=str(action_record_id),
                        retrieval_result_digest=str(retrieved.retrieval_result_digest),
                        gate_digest=str(gate.gate_digest),
                        subplan_id="",
                        prefix_score_q32=int(prefix_child),
                        bound_score_q32=int(bound_child),
                    )
                    nodes_by_id[str(child.node_id)] = child
                    open_list.append(child)

            # Beam prune after layer expansion.
            if int(beam_width_u32) > 0 and len(open_list) > int(beam_width_u32):
                open_list.sort(key=_record_order_key)
                open_list = open_list[: int(beam_width_u32)]

        # Final selection: best node by ordering (or root if open empty).
        chosen_node = root
        if open_list:
            open_list.sort(key=_record_order_key)
            chosen_node = open_list[0]

        # Reconstruct action sequence (node->root via parent pointers).
        action_path: list[tuple[str, str, bytes]] = []  # (action_record_id, action_hash_id, action_hash32)
        cur = chosen_node
        while int(cur.depth_u32) > 0 and str(cur.parent_id):
            action_record_id = str(cur.action_record_id)
            action_hash_id = str(cur.action_hash_id)
            action_hash32 = _sha256_id_to_digest32(action_hash_id, reason=DMPL_E_HASH_MISMATCH)
            action_path.append((action_record_id, action_hash_id, bytes(action_hash32)))
            cur = nodes_by_id.get(str(cur.parent_id), root)
            if cur.node_id == root.node_id:
                break
        action_path.reverse()

        if action_path:
            chosen_action_record_id, chosen_action_hash_id, chosen_action_hash32 = action_path[0]
        else:
            noop = make_noop_action_v1(runtime.dc1_id, runtime.opset_id)
            noop_hash_id, noop_hash32 = hash_action_record_v1(noop)
            chosen_action_record_id = _writer_write_json(artifact_writer, "dmpl_action_v1", noop)
            if str(chosen_action_record_id).strip() != str(noop_hash_id).strip():
                raise DMPLError(reason_code=DMPL_E_HASH_MISMATCH, details={"hint": "noop action id mismatch"})
            chosen_action_hash_id = str(noop_hash_id)
            chosen_action_hash32 = bytes(noop_hash32)

        # Finalize trace artifacts under mroot.
        rollout_trace_id, _chunks_root_id = trace.finalize(
            lambda artifact_type, raw: _writer_write_bin(artifact_writer, artifact_type, raw),
            lambda artifact_type, obj: _writer_write_json(artifact_writer, artifact_type, obj),
        )

        # Emit ActionReceipt (budget summary snapshot).
        budget_summary = {"nodes_u32": int(counters.nodes_u32), "ops_u64": int(counters.ops_u64), "bytes_u64": int(counters.bytes_u64)}
        status_obj = {"ok_b": True, "reason_code": str(DMPL_OK)}
        action_receipt_id = emit_action_receipt_v1(
            runtime,
            plan_query_id=str(plan_query_id),
            rollout_trace_id=str(rollout_trace_id),
            chosen_action_record_id=str(chosen_action_record_id),
            chosen_action_hash_id=str(chosen_action_hash_id),
            chosen_node_id=str(chosen_node.node_id),
            chosen_bound_score_q32=int(chosen_node.bound_score_q32),
            chosen_depth_u32=int(chosen_node.depth_u32),
            budget_summary=budget_summary,
            status_obj=status_obj,
        )

        return PlanResultV1(
            chosen_action_record_id=str(chosen_action_record_id),
            chosen_action_hash_id=str(chosen_action_hash_id),
            chosen_action_hash32=bytes(chosen_action_hash32),
            chosen_node_id=str(chosen_node.node_id),
            rollout_trace_id=str(rollout_trace_id),
            action_receipt_id=str(action_receipt_id),
        )

    except DMPLError as exc:
        # Caps enforcement: still emit an ActionReceipt (Phase 2 DoD), except for DMPL_E_DISABLED.
        if str(exc.reason_code) == str(DMPL_E_DISABLED):
            raise

        # Best-effort minimal receipt with deterministic placeholders.
        try:
            noop = make_noop_action_v1(runtime.dc1_id, runtime.opset_id)
            noop_hash_id, noop_hash32 = hash_action_record_v1(noop)
            noop_record_id = _writer_write_json(artifact_writer, "dmpl_action_v1", noop)
        except Exception:
            noop_hash_id = _SHA256_ZERO_ID
            noop_hash32 = b"\x00" * 32
            noop_record_id = _SHA256_ZERO_ID

        budget_summary = {"nodes_u32": int(counters.nodes_u32), "ops_u64": int(counters.ops_u64), "bytes_u64": int(counters.bytes_u64)}
        status_obj = {"ok_b": False, "reason_code": str(exc.reason_code)}
        try:
            _ = emit_action_receipt_v1(
                runtime,
                plan_query_id=str(_sha256_id_from_hex_digest32(_sha25632_count(gcj1_canon_bytes(plan_query_obj)))),
                rollout_trace_id=_SHA256_ZERO_ID,
                chosen_action_record_id=str(noop_record_id),
                chosen_action_hash_id=str(noop_hash_id),
                chosen_node_id=_SHA256_ZERO_ID,
                chosen_bound_score_q32=0,
                chosen_depth_u32=0,
                budget_summary=budget_summary,
                status_obj=status_obj,
            )
        except Exception:
            pass
        raise

    finally:
        _reset_active_artifact_writer(tok_wr)
        _reset_active_resolver(tok_res)
        _reset_active_op_counter(tok_ops)


__all__ = [
    "PlanResultV1",
    "plan_call_v1",
]
