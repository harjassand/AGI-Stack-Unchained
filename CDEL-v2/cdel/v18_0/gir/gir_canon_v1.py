"""Canonicalization for GIR v1 (RPO + deterministic SSA renaming)."""

from __future__ import annotations

from typing import Any

from ...v1_7r.canon import canon_bytes, sha256_prefixed
from .gir_types_v1 import normalize_gir_program


_METADATA_ALLOWLIST = {"type", "dtype", "shape"}


def _rpo_order(entry: str, succ_map: dict[str, list[str]]) -> list[str]:
    visited: set[str] = set()
    post: list[str] = []

    def dfs(node: str) -> None:
        if node in visited:
            return
        visited.add(node)
        for nxt in sorted(succ_map.get(node, [])):
            dfs(nxt)
        post.append(node)

    dfs(entry)
    remaining = sorted(set(succ_map.keys()) - visited)
    for node in remaining:
        dfs(node)
    return list(reversed(post))


def _canon_function(fn: dict[str, Any]) -> dict[str, Any]:
    block_map = {str(row["block_id"]): row for row in fn["blocks"]}
    succ_map = {bid: sorted(set(str(x) for x in block.get("successors", []))) for bid, block in block_map.items()}
    order = _rpo_order(str(fn["entry_block_id"]), succ_map)

    # Deterministic SSA/alpha-normalization by RPO traversal.
    rename_map: dict[str, str] = {}
    next_def = 0
    next_ext = 0

    def rename_use(name: str) -> str:
        nonlocal next_ext
        if name in rename_map:
            return rename_map[name]
        fresh = f"e{next_ext}"
        next_ext += 1
        rename_map[name] = fresh
        return fresh

    def rename_def(name: str) -> str:
        nonlocal next_def
        fresh = f"v{next_def}"
        next_def += 1
        rename_map[name] = fresh
        return fresh

    canon_blocks: list[dict[str, Any]] = []
    for block_idx, block_id in enumerate(order):
        block = block_map[block_id]
        canon_ops: list[dict[str, Any]] = []
        for op_idx, op in enumerate(block["ops"]):
            uses = [rename_use(str(token)) for token in op.get("uses", [])]
            defs = [rename_def(str(token)) for token in op.get("defs", [])]
            attrs = op.get("attrs", {})
            metadata = op.get("metadata", {})
            canon_ops.append(
                {
                    "op_id": f"op_{block_idx:04d}_{op_idx:04d}",
                    "opcode": str(op["opcode"]),
                    "defs": defs,
                    "uses": uses,
                    "attrs": {str(k): attrs[k] for k in sorted(attrs)},
                    "metadata": {str(k): metadata[k] for k in sorted(metadata) if str(k) in _METADATA_ALLOWLIST},
                }
            )
        canon_blocks.append(
            {
                "block_id": f"b{block_idx:04d}",
                "successors": sorted(
                    {
                        f"b{order.index(str(nxt)):04d}"
                        for nxt in succ_map.get(block_id, [])
                        if str(nxt) in order
                    }
                ),
                "ops": canon_ops,
            }
        )

    return {
        "function_name": str(fn["function_name"]),
        "args": [rename_use(str(token)) for token in fn.get("args", [])],
        "entry_block_id": "b0000",
        "blocks": canon_blocks,
    }


def canonicalize_gir_program(program: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_gir_program(program)
    modules = sorted(normalized["modules"], key=lambda row: str(row["module_relpath"]))
    canon_modules: list[dict[str, Any]] = []
    for module in modules:
        functions = sorted(module["functions"], key=lambda row: str(row["function_name"]))
        canon_modules.append(
            {
                "module_relpath": str(module["module_relpath"]),
                "functions": [_canon_function(fn) for fn in functions],
            }
        )
    return {"schema_version": "gir_program_v1", "modules": canon_modules}


def canon_gir_bytes(program: dict[str, Any]) -> bytes:
    return canon_bytes(canonicalize_gir_program(program))


def canon_gir_id(program: dict[str, Any]) -> str:
    return sha256_prefixed(canon_gir_bytes(program))


__all__ = ["canon_gir_bytes", "canon_gir_id", "canonicalize_gir_program"]

