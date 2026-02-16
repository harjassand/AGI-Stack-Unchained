"""Deterministic ACTIONSEQ payload application (restricted v0.2 scope)."""

from __future__ import annotations

import ast
import difflib
from pathlib import Path
from typing import Any

from ...v1_7r.canon import canon_bytes
from ..gir.gir_canon_v1 import canon_gir_id
from ..gir.gir_extract_from_tree_v1 import extract_gir_from_tree, is_gir_scope_path
from ..op.obligations_v1 import apply_obligation_bundle, assert_no_blocking_obligations, make_obligation_state
from ..omega_common_v1 import load_canon_dict, validate_schema


_TEST_ALLOWLIST_PREFIXES = (
    "CDEL-v2/cdel/v18_0/tests_fast/",
    "CDEL-v2/cdel/v18_0/tests_omega_daemon/",
    "CDEL-v2/cdel/v18_0/tests_integration/",
)


def _normalize_relpath(path_value: str) -> str:
    rel = str(path_value).strip().replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        raise RuntimeError("INVALID:SITE_NOT_FOUND")
    return rel


def _load_active_op_pool_ids(repo_root: Path) -> set[str]:
    path = repo_root / "authority" / "operator_pools" / "op_active_set_v1.json"
    if not path.exists() or not path.is_file():
        return set()
    payload = load_canon_dict(path)
    if payload.get("schema_version") != "op_active_set_v1":
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    rows = payload.get("active_op_pool_ids", [])
    if not isinstance(rows, list):
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    return {str(row) for row in rows}


def _load_operator_pool(repo_root: Path, op_pool_id: str) -> dict[str, Any]:
    pools_dir = repo_root / "authority" / "operator_pools"
    for path in sorted(pools_dir.glob("*.json"), key=lambda row: row.as_posix()):
        try:
            payload = load_canon_dict(path)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict) or payload.get("schema_version") != "operator_pool_v1":
            continue
        validate_schema(payload, "operator_pool_v1")
        if str(payload.get("op_pool_id", "")) == op_pool_id:
            operators = payload.get("operators")
            if not isinstance(operators, list):
                raise RuntimeError("INVALID:SCHEMA_FAIL")
            return payload
    raise RuntimeError("INVALID:ILLEGAL_OPERATOR")


def _find_operator(pool: dict[str, Any], op_id: str) -> dict[str, Any]:
    for row in pool.get("operators", []):
        if isinstance(row, dict) and str(row.get("op_id", "")) == op_id:
            if not bool(row.get("enabled", False)):
                raise RuntimeError("INVALID:ILLEGAL_OPERATOR")
            return row
    raise RuntimeError("INVALID:ILLEGAL_OPERATOR")


def _parse_site(site: str) -> tuple[str, str | None]:
    raw = str(site).strip()
    if not raw:
        raise RuntimeError("INVALID:SITE_NOT_FOUND")
    parts = raw.split("::")
    relpath = _normalize_relpath(parts[0])
    fn_name = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    return relpath, fn_name


class _RenameLocal(ast.NodeTransformer):
    def __init__(self, *, from_name: str, to_name: str, function_name: str | None) -> None:
        self.from_name = from_name
        self.to_name = to_name
        self.function_name = function_name
        self._inside_target = function_name is None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:  # noqa: N802
        prior = self._inside_target
        self._inside_target = prior or (self.function_name == node.name)
        self.generic_visit(node)
        self._inside_target = prior
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:  # noqa: N802
        prior = self._inside_target
        self._inside_target = prior or (self.function_name == node.name)
        self.generic_visit(node)
        self._inside_target = prior
        return node

    def visit_Name(self, node: ast.Name) -> Any:  # noqa: N802
        if self._inside_target and node.id == self.from_name:
            return ast.copy_location(ast.Name(id=self.to_name, ctx=node.ctx), node)
        return node


class _InlineConst(ast.NodeTransformer):
    def __init__(self, *, const_name: str, value: Any, function_name: str | None) -> None:
        self.const_name = const_name
        self.value = value
        self.function_name = function_name
        self._inside_target = function_name is None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:  # noqa: N802
        prior = self._inside_target
        self._inside_target = prior or (self.function_name == node.name)
        self.generic_visit(node)
        self._inside_target = prior
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:  # noqa: N802
        prior = self._inside_target
        self._inside_target = prior or (self.function_name == node.name)
        self.generic_visit(node)
        self._inside_target = prior
        return node

    def visit_Name(self, node: ast.Name) -> Any:  # noqa: N802
        if self._inside_target and isinstance(node.ctx, ast.Load) and node.id == self.const_name:
            return ast.copy_location(ast.Constant(value=self.value), node)
        return node


def _insert_guard(tree: ast.AST, *, function_name: str | None, predicate_expr: str) -> ast.AST:
    pred = str(predicate_expr).strip()
    if pred not in {"True", "False"}:
        raise RuntimeError("INVALID:TYPE_MISMATCH")
    pred_node = ast.parse(pred, mode="eval").body

    class _InsertGuard(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:  # noqa: N802
            if function_name is None or node.name == function_name:
                guard = ast.If(test=pred_node, body=[ast.Return(value=None)], orelse=[])
                node.body = [guard, *node.body]
            return self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:  # noqa: N802
            if function_name is None or node.name == function_name:
                guard = ast.If(test=pred_node, body=[ast.Return(value=None)], orelse=[])
                node.body = [guard, *node.body]
            return self.generic_visit(node)

    return _InsertGuard().visit(tree)


def _apply_operator_to_source(
    *,
    source: str,
    op_id: str,
    args: dict[str, Any],
    function_name: str | None,
) -> str:
    tree = ast.parse(source, type_comments=True)
    if op_id == "OP_RENAME_LOCAL":
        from_name = str(args.get("from_name", "")).strip()
        to_name = str(args.get("to_name", "")).strip()
        if not from_name or not to_name:
            raise RuntimeError("INVALID:TYPE_MISMATCH")
        tree = _RenameLocal(from_name=from_name, to_name=to_name, function_name=function_name).visit(tree)
    elif op_id == "OP_INLINE_CONST":
        const_name = str(args.get("const_name", "")).strip()
        if not const_name:
            raise RuntimeError("INVALID:TYPE_MISMATCH")
        tree = _InlineConst(const_name=const_name, value=args.get("value"), function_name=function_name).visit(tree)
    elif op_id == "OP_INSERT_GUARD":
        tree = _insert_guard(
            tree,
            function_name=function_name,
            predicate_expr=str(args.get("predicate_expr", "False")),
        )
    else:
        raise RuntimeError("INVALID:ILLEGAL_OPERATOR")
    ast.fix_missing_locations(tree)
    text = ast.unparse(tree)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _patch_for_file(relpath: str, before: str | None, after: str | None) -> str:
    before_lines = [] if before is None else before.splitlines(keepends=True)
    after_lines = [] if after is None else after.splitlines(keepends=True)
    diff = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"a/{relpath}",
        tofile=f"b/{relpath}",
        lineterm="",
    )
    rows = list(diff)
    if not rows:
        return ""
    return "\n".join(rows) + "\n"


def build_patch_from_actionseq(
    *,
    repo_root: Path,
    subrun_root: Path,
    ccap_id: str,
    ccap: dict[str, Any],
) -> bytes:
    del subrun_root, ccap_id
    meta = ccap.get("meta")
    payload = ccap.get("payload")
    if not isinstance(meta, dict) or not isinstance(payload, dict):
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    if str(payload.get("kind", "")) != "ACTIONSEQ":
        raise RuntimeError("INVALID:PAYLOAD_KIND_UNSUPPORTED")
    action_seq = payload.get("action_seq")
    if not isinstance(action_seq, dict):
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    steps = action_seq.get("steps")
    if not isinstance(steps, list):
        raise RuntimeError("INVALID:SCHEMA_FAIL")

    op_pool_id = str(meta.get("op_pool_id", "")).strip()
    active_ids = _load_active_op_pool_ids(repo_root)
    if op_pool_id not in active_ids:
        # Layer-3 remains implemented but disabled by default via active set.
        raise RuntimeError("INVALID:ILLEGAL_OPERATOR")
    pool = _load_operator_pool(repo_root, op_pool_id)

    obligations = make_obligation_state()
    modified_sources: dict[str, str] = {}
    created_test_files: dict[str, str] = {}

    for step in steps:
        if not isinstance(step, dict):
            raise RuntimeError("INVALID:SCHEMA_FAIL")
        op_id = str(step.get("op_id", "")).strip()
        operator = _find_operator(pool, op_id)
        bundle = operator.get("obligation_bundle", {})
        if isinstance(bundle, dict):
            apply_obligation_bundle(obligations, bundle)

        args = step.get("args", {})
        if not isinstance(args, dict):
            raise RuntimeError("INVALID:TYPE_MISMATCH")

        if op_id == "OP_ADD_TEST_FILE":
            relpath = _normalize_relpath(str(args.get("relpath", "")).strip())
            if not any(relpath.startswith(prefix) for prefix in _TEST_ALLOWLIST_PREFIXES):
                raise RuntimeError("INVALID:SITE_NOT_FOUND")
            content = str(args.get("content", "def test_generated_actionseq_v1():\n    assert True\n"))
            if not content.endswith("\n"):
                content += "\n"
            created_test_files[relpath] = content
            continue

        site = str(step.get("site", "")).strip()
        relpath, function_name = _parse_site(site)
        if not is_gir_scope_path(relpath):
            raise RuntimeError("INVALID:PAYLOAD_KIND_UNSUPPORTED")
        path = (repo_root / relpath).resolve()
        if not path.exists() or not path.is_file():
            raise RuntimeError("INVALID:SITE_NOT_FOUND")

        baseline = modified_sources.get(relpath, path.read_text(encoding="utf-8"))
        _ = canon_gir_id(extract_gir_from_tree(tree_root=repo_root, module_relpath=relpath))
        updated = _apply_operator_to_source(
            source=baseline,
            op_id=op_id,
            args=args,
            function_name=function_name,
        )
        modified_sources[relpath] = updated

    assert_no_blocking_obligations(obligations)

    patch_chunks: list[str] = []
    for relpath in sorted(modified_sources):
        before = (repo_root / relpath).read_text(encoding="utf-8")
        after = modified_sources[relpath]
        _ = canon_gir_id(extract_gir_from_tree(tree_root=repo_root, module_relpath=relpath))
        patch = _patch_for_file(relpath, before, after)
        if patch:
            patch_chunks.append(patch)
    for relpath in sorted(created_test_files):
        patch = _patch_for_file(relpath, None, created_test_files[relpath])
        if patch:
            patch_chunks.append(patch)

    patch_text = "".join(patch_chunks)
    if not patch_text:
        raise RuntimeError("INVALID:SITE_NOT_FOUND")
    return patch_text.encode("utf-8")


__all__ = ["build_patch_from_actionseq"]
