"""FAL ladder normal-form validation (v1).

Normative rules: user spec §5.2.1 (Ladder Normal Form validation).

This module is RE2: deterministic, fail-closed.
"""

from __future__ import annotations

from typing import Final, TYPE_CHECKING, Any

from ..omega_common_v1 import fail
from .qxwmr_state_v1 import EDGE_TOK_ABSTRACTS_U32

_REASON_QXWMR_FAL_CONSTRAINT_FAIL: Final[str] = "EUDRSU_QXWMR_FAL_CONSTRAINT_FAIL"

if TYPE_CHECKING:  # pragma: no cover
    from .qxwmr_canon_wl_v1 import QXWMRCanonCapsContextV1
    from .qxwmr_state_v1 import QXWMRStatePackedV1


def validate_ladder_normal_form_v1(
    *,
    N_u32: int,
    src_u32: list[int],
    dst_u32: list[int],
    edge_tok_u32: list[int],
    node_level_u16: list[int],
    abstracts_out_cap_u32: int,
    abstracts_in_cap_u32: int,
) -> None:
    """Validate ladder constraints for ABSTRACTS edges.

    Fail-closed on any violation.
    """

    N = int(N_u32)
    if N < 0:
        fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)

    if not isinstance(src_u32, list) or not isinstance(dst_u32, list) or not isinstance(edge_tok_u32, list):
        fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)
    if not isinstance(node_level_u16, list) or len(node_level_u16) != N:
        fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)

    E = len(edge_tok_u32)
    if len(src_u32) != E or len(dst_u32) != E:
        fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)

    out_cap = int(abstracts_out_cap_u32)
    in_cap = int(abstracts_in_cap_u32)
    if out_cap < 0 or in_cap < 0:
        fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)

    # Collect ladder edges and validate local constraints.
    outgoing: list[list[int]] = [[] for _ in range(N)]
    out_deg = [0] * N
    in_deg = [0] * N

    ladder_edges: list[tuple[int, int]] = []

    for e in range(E):
        tok = int(edge_tok_u32[e])
        if tok != EDGE_TOK_ABSTRACTS_U32:
            continue
        # tok==EDGE_TOK_ABSTRACTS implies active edge because EDGE_TOK_ABSTRACTS!=0 in v1.
        child = int(src_u32[e])
        parent = int(dst_u32[e])
        if child < 0 or parent < 0:
            fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)
        if child >= N or parent >= N:
            fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)
        if child == parent:
            fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)

        out_deg[child] += 1
        in_deg[parent] += 1
        outgoing[child].append(parent)
        ladder_edges.append((child, parent))

    # Fan-in/out caps (mandatory in v1).
    for i in range(N):
        if out_deg[i] > out_cap:
            fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)
        if in_deg[i] > in_cap:
            fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)

    # No cycles: deterministic DFS in node index order.
    # Deterministic neighbor traversal: parents sorted ascending (stable).
    for i in range(N):
        outgoing[i].sort()

    UNVISITED: Final[int] = 0
    VISITING: Final[int] = 1
    DONE: Final[int] = 2
    color = [UNVISITED] * N

    for start in range(N):
        if color[start] != UNVISITED:
            continue
        # Iterative DFS to avoid recursion depth dependence.
        stack: list[tuple[int, int]] = [(start, 0)]
        color[start] = VISITING
        while stack:
            node, idx = stack[-1]
            nbrs = outgoing[node]
            if idx >= len(nbrs):
                color[node] = DONE
                stack.pop()
                continue
            nxt = int(nbrs[idx])
            stack[-1] = (node, idx + 1)
            if color[nxt] == VISITING:
                fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)
            if color[nxt] == UNVISITED:
                color[nxt] = VISITING
                stack.append((nxt, 0))

    # Monotone levels: level(child)+1 == level(parent)
    for child, parent in ladder_edges:
        if int(node_level_u16[child]) + 1 != int(node_level_u16[parent]):
            fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)


def validate_fal_constraints_for_qxwmr_state_v1(state: "QXWMRStatePackedV1", caps_ctx: "QXWMRCanonCapsContextV1") -> None:
    """Normative Phase 2 entrypoint: validate FAL constraints for a decoded QXWMR state."""

    if getattr(state, "fal_enabled", False) is not True:
        return None
    if not getattr(caps_ctx, "fal_enabled", False):
        fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)

    out_cap = getattr(caps_ctx, "abstracts_out_cap_u32", None)
    in_cap = getattr(caps_ctx, "abstracts_in_cap_u32", None)
    if not isinstance(out_cap, int) or not isinstance(in_cap, int):
        fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)

    levels = getattr(state, "node_level_u16", None)
    if not isinstance(levels, list):
        fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)

    validate_ladder_normal_form_v1(
        N_u32=int(getattr(state, "N_u32", 0)),
        src_u32=list(getattr(state, "src_u32", [])),
        dst_u32=list(getattr(state, "dst_u32", [])),
        edge_tok_u32=list(getattr(state, "edge_tok_u32", [])),
        node_level_u16=list(levels),
        abstracts_out_cap_u32=int(out_cap),
        abstracts_in_cap_u32=int(in_cap),
    )
    return None


def count_abstracts_out_in_v1(state: "QXWMRStatePackedV1", node_id_u32: int) -> tuple[int, int]:
    """Return (abstracts_out_count, abstracts_in_count) for node_id.

    Counts only active ABSTRACTS edges (edge_tok==EDGE_TOK_ABSTRACTS_U32).
    """

    if not hasattr(state, "N_u32") or not hasattr(state, "E_u32"):
        fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)
    N = int(getattr(state, "N_u32", 0))
    E = int(getattr(state, "E_u32", 0))
    node_id = int(node_id_u32)
    if node_id < 0 or node_id >= N:
        fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)

    src = getattr(state, "src_u32", None)
    dst = getattr(state, "dst_u32", None)
    tok = getattr(state, "edge_tok_u32", None)
    if not isinstance(src, list) or not isinstance(dst, list) or not isinstance(tok, list):
        fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)
    if len(src) != E or len(dst) != E or len(tok) != E:
        fail(_REASON_QXWMR_FAL_CONSTRAINT_FAIL)

    out_cnt = 0
    in_cnt = 0
    for e in range(E):
        if int(tok[e]) != EDGE_TOK_ABSTRACTS_U32:
            continue
        if int(src[e]) == node_id:
            out_cnt += 1
        if int(dst[e]) == node_id:
            in_cnt += 1
    return int(out_cnt), int(in_cnt)


__all__ = ["count_abstracts_out_in_v1", "validate_fal_constraints_for_qxwmr_state_v1", "validate_ladder_normal_form_v1"]
