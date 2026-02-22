"""Deterministic nontriviality certificate helpers shared by SH-1 and promoter."""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed


_DIFF_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_CONTROL_FLOW_NODE_TYPES = (
    ast.If,
    ast.For,
    ast.While,
    ast.Try,
    ast.With,
    ast.Match,
    ast.AsyncFor,
    ast.AsyncWith,
)

NONTRIVIALITY_POLICY_ID = "nontriviality_policy_v2"
NONTRIVIALITY_THRESHOLD_PROFILE_ID = "nontriviality_policy_v2_thresholds_v1"
NONTRIVIALITY_DEFAULT_THRESHOLDS_V1 = {
    "wiring_ast_nodes_min_u32": 12,
}

FORCED_HEAVY_ARCHETYPE_CALL_EDGE = "WIRE_CALL_EDGE"
FORCED_HEAVY_ARCHETYPE_CONTROL_FLOW = "CONTROL_FLOW_REWRITE"
FORCED_HEAVY_ARCHETYPE_HELPER_REPLACE = "HELPER_REPLACE"
FORCED_HEAVY_ARCHETYPE_IDS = (
    FORCED_HEAVY_ARCHETYPE_CALL_EDGE,
    FORCED_HEAVY_ARCHETYPE_CONTROL_FLOW,
    FORCED_HEAVY_ARCHETYPE_HELPER_REPLACE,
)

THRESHOLD_FAIL_PATCH_PARSE_FAILED = "PATCH_PARSE_FAILED"
THRESHOLD_FAIL_AST_PARSE_FAILED = "AST_PARSE_FAILED"
THRESHOLD_FAIL_WIRING_CLASS_REQUIRED = "WIRING_CLASS_REQUIRED"
THRESHOLD_FAIL_CALL_EDGE_REQUIRED = "CALL_EDGE_REQUIRED"
THRESHOLD_FAIL_CONTROL_FLOW_REQUIRED = "CONTROL_FLOW_REQUIRED"
THRESHOLD_FAIL_AST_NODES_BELOW_MIN = "AST_NODES_BELOW_MIN"
THRESHOLD_FAIL_DATA_FLOW_REQUIRED = "DATA_FLOW_REQUIRED"


@dataclass(frozen=True)
class _PatchHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class _PatchFile:
    relpath: str
    hunks: tuple[_PatchHunk, ...]


def _normalize_relpath(path_value: str) -> str:
    rel = str(path_value).strip().replace("\\", "/").lstrip("./")
    path = Path(rel)
    if not rel or path.is_absolute() or ".." in path.parts:
        raise RuntimeError("SCHEMA_FAIL")
    return rel


def _parse_diff_relpath(raw: str) -> str:
    value = str(raw).strip()
    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        value = value[1:-1]
    return _normalize_relpath(value)


def _parse_unified_patch(patch_bytes: bytes) -> list[_PatchFile]:
    lines = patch_bytes.decode("utf-8", errors="replace").splitlines()
    rows: list[_PatchFile] = []
    current_relpath: str | None = None
    current_hunks: list[_PatchHunk] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if line.startswith("--- "):
            if idx + 1 >= len(lines) or not lines[idx + 1].startswith("+++ "):
                raise RuntimeError("PATCH_PARSE_FAILED")
            if current_relpath is not None:
                rows.append(_PatchFile(relpath=current_relpath, hunks=tuple(current_hunks)))
            current_hunks = []
            plus_line = lines[idx + 1][4:]
            if plus_line.strip() == "/dev/null":
                raise RuntimeError("PATCH_PARSE_FAILED")
            current_relpath = _parse_diff_relpath(plus_line)
            idx += 2
            continue
        if line.startswith("@@ "):
            if current_relpath is None:
                raise RuntimeError("PATCH_PARSE_FAILED")
            match = _DIFF_HUNK_RE.match(line)
            if match is None:
                raise RuntimeError("PATCH_PARSE_FAILED")
            old_start = int(match.group(1))
            old_count = int(match.group(2) or "1")
            new_start = int(match.group(3))
            new_count = int(match.group(4) or "1")
            hunk_lines: list[str] = []
            idx += 1
            while idx < len(lines):
                inner = lines[idx]
                if inner.startswith("@@ ") or inner.startswith("--- "):
                    break
                if inner.startswith("\\ No newline at end of file"):
                    idx += 1
                    continue
                if not inner or inner[0] not in {" ", "+", "-"}:
                    raise RuntimeError("PATCH_PARSE_FAILED")
                hunk_lines.append(inner)
                idx += 1
            current_hunks.append(
                _PatchHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=tuple(hunk_lines),
                )
            )
            continue
        idx += 1
    if current_relpath is not None:
        rows.append(_PatchFile(relpath=current_relpath, hunks=tuple(current_hunks)))
    if not rows:
        raise RuntimeError("PATCH_PARSE_FAILED")
    return rows


def _apply_patch_to_text(*, before_text: str, file_patch: _PatchFile) -> str:
    before_lines = before_text.splitlines(keepends=True)
    out: list[str] = []
    cursor = 0
    for hunk in file_patch.hunks:
        start_idx = max(0, int(hunk.old_start) - 1)
        if start_idx < cursor or start_idx > len(before_lines):
            raise RuntimeError("PATCH_APPLY_FAIL")
        out.extend(before_lines[cursor:start_idx])
        cursor = start_idx
        for raw in hunk.lines:
            prefix = raw[0]
            body = raw[1:]
            if prefix == " ":
                if cursor >= len(before_lines):
                    raise RuntimeError("PATCH_APPLY_FAIL")
                observed = before_lines[cursor].rstrip("\n")
                if observed != body:
                    raise RuntimeError("PATCH_APPLY_FAIL")
                out.append(before_lines[cursor])
                cursor += 1
            elif prefix == "-":
                if cursor >= len(before_lines):
                    raise RuntimeError("PATCH_APPLY_FAIL")
                observed = before_lines[cursor].rstrip("\n")
                if observed != body:
                    raise RuntimeError("PATCH_APPLY_FAIL")
                cursor += 1
            elif prefix == "+":
                out.append(body + "\n")
            else:
                raise RuntimeError("PATCH_PARSE_FAILED")
    out.extend(before_lines[cursor:])
    return "".join(out)


def _tree_node_counter(tree: ast.AST) -> Counter[str]:
    counter: Counter[str] = Counter()
    for node in ast.walk(tree):
        key = ast.dump(node, annotate_fields=True, include_attributes=False)
        counter[key] += 1
    return counter


def _counter_diff_u32(a: Counter[str], b: Counter[str]) -> int:
    keys = set(a.keys()) | set(b.keys())
    total = 0
    for key in keys:
        total += abs(int(a.get(key, 0)) - int(b.get(key, 0)))
    return int(max(0, total))


def _control_flow_counter(tree: ast.AST) -> Counter[str]:
    counter: Counter[str] = Counter()
    for node in ast.walk(tree):
        for node_type in _CONTROL_FLOW_NODE_TYPES:
            if isinstance(node, node_type):
                counter[node_type.__name__] += 1
                break
    return counter


def _callee_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return str(node.id)
    if isinstance(node, ast.Attribute):
        return str(node.attr)
    return None


class _CallEdgeCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self._scope: list[str] = []
        self.edges: set[tuple[str, str]] = set()

    def _caller(self) -> str:
        if not self._scope:
            return "<module>"
        return ".".join(self._scope)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:  # noqa: D401
        self._scope.append(str(node.name))
        self.generic_visit(node)
        self._scope.pop()
        return None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:  # noqa: D401
        self._scope.append(str(node.name))
        self.generic_visit(node)
        self._scope.pop()
        return None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:  # noqa: D401
        self._scope.append(str(node.name))
        self.generic_visit(node)
        self._scope.pop()
        return None

    def visit_Call(self, node: ast.Call) -> Any:  # noqa: D401
        callee = _callee_name(node.func)
        if callee:
            self.edges.add((self._caller(), callee))
        self.generic_visit(node)
        return None


def _call_edges(tree: ast.AST) -> set[tuple[str, str]]:
    collector = _CallEdgeCollector()
    collector.visit(tree)
    return set(collector.edges)


def _expr_dump(node: ast.AST | None) -> str:
    if node is None:
        return "None"
    return ast.dump(node, annotate_fields=True, include_attributes=False)


def _data_flow_counter(tree: ast.AST) -> Counter[str]:
    counter: Counter[str] = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            target_dump = "|".join(_expr_dump(target) for target in node.targets)
            counter[f"ASSIGN:{target_dump}:{_expr_dump(node.value)}"] += 1
        elif isinstance(node, ast.AnnAssign):
            counter[f"ANN_ASSIGN:{_expr_dump(node.target)}:{_expr_dump(node.value)}"] += 1
        elif isinstance(node, ast.AugAssign):
            counter[f"AUG_ASSIGN:{_expr_dump(node.target)}:{node.op.__class__.__name__}:{_expr_dump(node.value)}"] += 1
        elif isinstance(node, ast.Return):
            counter[f"RETURN:{_expr_dump(node.value)}"] += 1
    return counter


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = node.args
    payload = {
        "name": str(node.name),
        "posonly": [str(arg.arg) for arg in args.posonlyargs],
        "args": [str(arg.arg) for arg in args.args],
        "kwonly": [str(arg.arg) for arg in args.kwonlyargs],
        "vararg": (str(args.vararg.arg) if args.vararg is not None else None),
        "kwarg": (str(args.kwarg.arg) if args.kwarg is not None else None),
        "defaults_u32": int(len(args.defaults)),
        "kw_defaults_u32": int(len(args.kw_defaults)),
        "returns": _expr_dump(node.returns),
    }
    return sha256_prefixed(canon_bytes(payload))


def _public_api_signature(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if str(node.name).startswith("_"):
                continue
            out.add(f"FUNC:{node.name}:{_function_signature(node)}")
            continue
        if isinstance(node, ast.ClassDef):
            if str(node.name).startswith("_"):
                continue
            methods: list[str] = []
            for item in node.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if str(item.name).startswith("_"):
                    continue
                methods.append(f"{item.name}:{_function_signature(item)}")
            methods.sort()
            out.add(
                "CLASS:"
                + str(node.name)
                + ":"
                + sha256_prefixed(canon_bytes({"methods": methods}))
            )
    return out


def _normalize_thresholds(thresholds_v1: dict[str, Any] | None) -> dict[str, int]:
    payload = dict(NONTRIVIALITY_DEFAULT_THRESHOLDS_V1)
    if isinstance(thresholds_v1, dict):
        for key in payload:
            if key in thresholds_v1:
                payload[key] = int(max(0, int(thresholds_v1.get(key, payload[key]))))
    return payload


def evaluate_wiring_class(
    *,
    call_edges_changed_b: bool,
    control_flow_changed_b: bool,
    ast_nodes_changed_u32: int,
    touched_paths_u32: int,
    data_flow_changed_b: bool,
    public_api_changed_b: bool,
    patch_parse_ok_b: bool,
    ast_parse_ok_b: bool,
    thresholds_v1: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    thresholds = _normalize_thresholds(thresholds_v1)
    ast_min = int(max(0, int(thresholds["wiring_ast_nodes_min_u32"])))
    if not bool(patch_parse_ok_b):
        return False, THRESHOLD_FAIL_PATCH_PARSE_FAILED
    if not bool(ast_parse_ok_b):
        return False, THRESHOLD_FAIL_AST_PARSE_FAILED
    if bool(call_edges_changed_b) or bool(control_flow_changed_b):
        return True, None
    if int(ast_nodes_changed_u32) >= ast_min and bool(data_flow_changed_b):
        return True, None
    # Cross-file rewrites can carry wiring evidence via coordinated API/data flow
    # deltas even when no single-file call-edge/control-flow gate fires.
    if int(touched_paths_u32) >= 2 and int(ast_nodes_changed_u32) >= ast_min:
        if bool(public_api_changed_b) or bool(data_flow_changed_b):
            return True, None
    return False, THRESHOLD_FAIL_WIRING_CLASS_REQUIRED


def evaluate_forced_heavy_archetype(
    *,
    archetype_id: str,
    call_edges_changed_b: bool,
    control_flow_changed_b: bool,
    ast_nodes_changed_u32: int,
    data_flow_changed_b: bool,
    thresholds_v1: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    archetype = str(archetype_id).strip()
    thresholds = _normalize_thresholds(thresholds_v1)
    ast_min = int(max(0, int(thresholds["wiring_ast_nodes_min_u32"])))
    if archetype == FORCED_HEAVY_ARCHETYPE_CALL_EDGE:
        if bool(call_edges_changed_b):
            return True, None
        return False, THRESHOLD_FAIL_CALL_EDGE_REQUIRED
    if archetype == FORCED_HEAVY_ARCHETYPE_CONTROL_FLOW:
        if bool(control_flow_changed_b):
            return True, None
        return False, THRESHOLD_FAIL_CONTROL_FLOW_REQUIRED
    if archetype == FORCED_HEAVY_ARCHETYPE_HELPER_REPLACE:
        if int(ast_nodes_changed_u32) < ast_min:
            return False, THRESHOLD_FAIL_AST_NODES_BELOW_MIN
        if not bool(data_flow_changed_b):
            return False, THRESHOLD_FAIL_DATA_FLOW_REQUIRED
        return True, None
    raise RuntimeError("SCHEMA_FAIL")


def nontriviality_shape_id_from_cert(cert: dict[str, Any]) -> str:
    touched_relpaths: list[str] = []
    raw_touched_relpaths = cert.get("touched_relpaths_v1")
    if isinstance(raw_touched_relpaths, list):
        for row in raw_touched_relpaths:
            try:
                touched_relpaths.append(_normalize_relpath(str(row)))
            except Exception:
                continue
    touched_relpaths = sorted(set(touched_relpaths))
    touched_relpaths_hash = sha256_prefixed(canon_bytes({"touched_relpaths_v1": touched_relpaths}))
    payload = {
        "schema_name": "nontriviality_shape_v1",
        "touched_paths_u32": int(max(0, int(cert.get("touched_paths_u32", 0)))),
        "touched_relpaths_hash": touched_relpaths_hash,
        "ast_nodes_changed_u32": int(max(0, int(cert.get("ast_nodes_changed_u32", 0)))),
        "control_flow_changed_b": bool(cert.get("control_flow_changed_b", False)),
        "call_edges_changed_b": bool(cert.get("call_edges_changed_b", False)),
        "data_flow_changed_b": bool(cert.get("data_flow_changed_b", False)),
        "public_api_changed_b": bool(cert.get("public_api_changed_b", False)),
        "lines_added_u32": int(max(0, int(cert.get("lines_added_u32", 0)))),
        "lines_deleted_u32": int(max(0, int(cert.get("lines_deleted_u32", 0)))),
        "archetype_id": (str(cert.get("archetype_id", "")).strip() or None),
    }
    return sha256_prefixed(canon_bytes(payload))


def build_nontriviality_cert_v1(
    *,
    repo_root: Path,
    patch_bytes: bytes,
    archetype_id: str | None = None,
    thresholds_v1: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thresholds = _normalize_thresholds(thresholds_v1)
    patch_parse_ok_b = True
    ast_parse_ok_b = True
    try:
        file_patches = _parse_unified_patch(patch_bytes)
    except Exception:
        file_patches = []
        patch_parse_ok_b = False

    touched_paths: list[str] = []
    lines_added_u32 = 0
    lines_deleted_u32 = 0
    ast_nodes_changed_u32 = 0
    control_flow_changed_b = False
    call_edges_changed_b = False
    data_flow_changed_b = False
    public_api_changed_b = False

    for file_patch in file_patches:
        touched_paths.append(str(file_patch.relpath))
        for hunk in file_patch.hunks:
            for raw in hunk.lines:
                if raw.startswith("+"):
                    lines_added_u32 += 1
                elif raw.startswith("-"):
                    lines_deleted_u32 += 1
        if not str(file_patch.relpath).endswith(".py"):
            continue
        before_path = (Path(repo_root).resolve() / str(file_patch.relpath)).resolve()
        before_text = before_path.read_text(encoding="utf-8") if before_path.exists() and before_path.is_file() else ""
        try:
            after_text = _apply_patch_to_text(before_text=before_text, file_patch=file_patch)
            before_tree = ast.parse(before_text)
            after_tree = ast.parse(after_text)
        except Exception:
            ast_parse_ok_b = False
            continue
        before_nodes = _tree_node_counter(before_tree)
        after_nodes = _tree_node_counter(after_tree)
        ast_nodes_changed_u32 += _counter_diff_u32(before_nodes, after_nodes)
        if _counter_diff_u32(_control_flow_counter(before_tree), _control_flow_counter(after_tree)) > 0:
            control_flow_changed_b = True
        if _call_edges(before_tree) != _call_edges(after_tree):
            call_edges_changed_b = True
        if _counter_diff_u32(_data_flow_counter(before_tree), _data_flow_counter(after_tree)) > 0:
            data_flow_changed_b = True
        if _public_api_signature(before_tree) != _public_api_signature(after_tree):
            public_api_changed_b = True

    wiring_class_ok_b, failed_threshold_code = evaluate_wiring_class(
        call_edges_changed_b=bool(call_edges_changed_b),
        control_flow_changed_b=bool(control_flow_changed_b),
        ast_nodes_changed_u32=int(ast_nodes_changed_u32),
        touched_paths_u32=int(len(sorted(set(touched_paths)))),
        data_flow_changed_b=bool(data_flow_changed_b),
        public_api_changed_b=bool(public_api_changed_b),
        patch_parse_ok_b=bool(patch_parse_ok_b),
        ast_parse_ok_b=bool(ast_parse_ok_b),
        thresholds_v1=thresholds,
    )
    archetype_pass_b: bool | None = None
    archetype_value: str | None = None
    if isinstance(archetype_id, str) and archetype_id.strip():
        archetype_value = str(archetype_id).strip()
        archetype_pass_b, archetype_failed_threshold_code = evaluate_forced_heavy_archetype(
            archetype_id=archetype_value,
            call_edges_changed_b=bool(call_edges_changed_b),
            control_flow_changed_b=bool(control_flow_changed_b),
            ast_nodes_changed_u32=int(ast_nodes_changed_u32),
            data_flow_changed_b=bool(data_flow_changed_b),
            thresholds_v1=thresholds,
        )
        if not archetype_pass_b:
            failed_threshold_code = archetype_failed_threshold_code

    cert = {
        "schema_name": "nontriviality_cert_v1",
        "schema_version": "v1",
        "policy_id": NONTRIVIALITY_POLICY_ID,
        "threshold_profile_id": NONTRIVIALITY_THRESHOLD_PROFILE_ID,
        "thresholds_v1": dict(thresholds),
        "patch_parse_ok_b": bool(patch_parse_ok_b),
        "ast_parse_ok_b": bool(ast_parse_ok_b),
        "touched_paths_u32": int(len(sorted(set(touched_paths)))),
        "touched_relpaths_v1": sorted(set(str(row) for row in touched_paths)),
        "ast_nodes_changed_u32": int(max(0, int(ast_nodes_changed_u32))),
        "control_flow_changed_b": bool(control_flow_changed_b),
        "call_edges_changed_b": bool(call_edges_changed_b),
        "data_flow_changed_b": bool(data_flow_changed_b),
        "public_api_changed_b": bool(public_api_changed_b),
        "lines_added_u32": int(max(0, int(lines_added_u32))),
        "lines_deleted_u32": int(max(0, int(lines_deleted_u32))),
        "wiring_class_ok_b": bool(wiring_class_ok_b),
        "archetype_id": archetype_value,
        "archetype_pass_b": archetype_pass_b,
        "failed_threshold_code": (str(failed_threshold_code) if isinstance(failed_threshold_code, str) and failed_threshold_code else None),
    }
    cert["shape_id"] = nontriviality_shape_id_from_cert(cert)
    return cert


__all__ = [
    "FORCED_HEAVY_ARCHETYPE_CALL_EDGE",
    "FORCED_HEAVY_ARCHETYPE_CONTROL_FLOW",
    "FORCED_HEAVY_ARCHETYPE_HELPER_REPLACE",
    "FORCED_HEAVY_ARCHETYPE_IDS",
    "NONTRIVIALITY_DEFAULT_THRESHOLDS_V1",
    "NONTRIVIALITY_POLICY_ID",
    "NONTRIVIALITY_THRESHOLD_PROFILE_ID",
    "THRESHOLD_FAIL_AST_NODES_BELOW_MIN",
    "THRESHOLD_FAIL_AST_PARSE_FAILED",
    "THRESHOLD_FAIL_CALL_EDGE_REQUIRED",
    "THRESHOLD_FAIL_CONTROL_FLOW_REQUIRED",
    "THRESHOLD_FAIL_DATA_FLOW_REQUIRED",
    "THRESHOLD_FAIL_PATCH_PARSE_FAILED",
    "THRESHOLD_FAIL_WIRING_CLASS_REQUIRED",
    "build_nontriviality_cert_v1",
    "evaluate_forced_heavy_archetype",
    "evaluate_wiring_class",
    "nontriviality_shape_id_from_cert",
]
