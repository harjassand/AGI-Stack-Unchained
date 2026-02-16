"""Restricted-scope Python GIR extraction for v0.2."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from .gir_canon_v1 import canonicalize_gir_program


_SCOPE_PATTERNS = [
    "orchestrator/omega_v18_0/*.py",
    "tools/omega/*.py",
]


def is_gir_scope_path(module_relpath: str) -> bool:
    rel = str(module_relpath).strip().replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        return False
    probe = Path(rel)
    return any(probe.match(pattern) for pattern in _SCOPE_PATTERNS)


class _StmtSummary(ast.NodeVisitor):
    def __init__(self) -> None:
        self.uses: set[str] = set()
        self.defs: set[str] = set()

    def visit_Name(self, node: ast.Name) -> Any:  # noqa: N802
        if isinstance(node.ctx, ast.Load):
            self.uses.add(str(node.id))
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            self.defs.add(str(node.id))
        return self.generic_visit(node)


def _op_from_stmt(stmt: ast.stmt, idx: int) -> dict[str, Any]:
    visitor = _StmtSummary()
    visitor.visit(stmt)
    opcode = type(stmt).__name__.lower()
    attrs = {"stmt_kind": type(stmt).__name__}
    metadata = {
        "line": int(getattr(stmt, "lineno", 0) or 0),
        "col": int(getattr(stmt, "col_offset", 0) or 0),
    }
    return {
        "op_id": f"raw_op_{idx:04d}",
        "opcode": opcode,
        "defs": sorted(visitor.defs),
        "uses": sorted(visitor.uses),
        "attrs": attrs,
        "metadata": metadata,
    }


def extract_gir_from_tree(*, tree_root: Path, module_relpath: str) -> dict[str, Any]:
    rel = str(module_relpath).strip().replace("\\", "/")
    if not is_gir_scope_path(rel):
        raise RuntimeError("INVALID:PAYLOAD_KIND_UNSUPPORTED")
    path = (tree_root / rel).resolve()
    if not path.exists() or not path.is_file():
        raise RuntimeError("INVALID:SITE_NOT_FOUND")
    src = path.read_text(encoding="utf-8")
    mod = ast.parse(src, filename=rel, type_comments=True)

    functions: list[dict[str, Any]] = []
    for node in mod.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = [str(row.arg) for row in node.args.args]
        ops = [_op_from_stmt(stmt, idx) for idx, stmt in enumerate(node.body)]
        functions.append(
            {
                "function_name": str(node.name),
                "args": args,
                "entry_block_id": "b_raw_0000",
                "blocks": [
                    {
                        "block_id": "b_raw_0000",
                        "successors": [],
                        "ops": ops,
                    }
                ],
            }
        )

    program = {
        "schema_version": "gir_program_v1",
        "modules": [
            {
                "module_relpath": rel,
                "functions": functions,
            }
        ],
    }
    return canonicalize_gir_program(program)


__all__ = ["extract_gir_from_tree", "is_gir_scope_path"]

