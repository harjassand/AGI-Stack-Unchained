"""Deterministic patch templates (v1)."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Callable, Iterable, List, Optional

from ...ops.token_edit_v1 import read_text_normalized, write_text_lf
from ...patch.unified_diff_v1 import unified_diff


UnifiedDiffPatch = str


@dataclass(frozen=True)
class DevHint:
    implicated_paths: List[str]
    fail_signature: str
    normalized_error: str


@dataclass(frozen=True)
class Template:
    template_id: str
    apply: Callable[[str, DevHint, "RNG"], Optional[UnifiedDiffPatch]]


class RNG:
    def randbelow(self, n: int) -> int:  # pragma: no cover - protocol
        raise NotImplementedError

    def choice(self, items: List[str]) -> str:  # pragma: no cover - protocol
        raise NotImplementedError


def _is_text_file(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
        if b"\x00" in chunk:
            return False
    except OSError:
        return False
    return True


def _list_repo_files(repo_dir: str) -> List[str]:
    out: List[str] = []
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in {".git", "__pycache__", "node_modules", "dist", "build", ".venv", "venv", "runs"}
        )
        for name in sorted(files):
            rel = os.path.relpath(os.path.join(root, name), repo_dir)
            out.append(rel)
    return out


def _select_target_file(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[str]:
    candidates: List[str] = []
    for rel in hint.implicated_paths or []:
        abs_path = os.path.join(repo_dir, rel)
        if os.path.isfile(abs_path) and _is_text_file(abs_path):
            candidates.append(rel)
    if not candidates:
        for rel in _list_repo_files(repo_dir):
            if rel.endswith(".py"):
                abs_path = os.path.join(repo_dir, rel)
                if _is_text_file(abs_path):
                    candidates.append(rel)
        if not candidates:
            for rel in _list_repo_files(repo_dir):
                abs_path = os.path.join(repo_dir, rel)
                if _is_text_file(abs_path):
                    candidates.append(rel)
    if not candidates:
        return None
    return rng.choice(sorted(candidates))


def _select_anchor_path(repo_dir: str, hint: DevHint) -> Optional[str]:
    candidates: List[str] = []
    for rel in sorted(set(hint.implicated_paths or [])):
        abs_path = os.path.join(repo_dir, rel)
        if os.path.isfile(abs_path) and _is_text_file(abs_path):
            candidates.append(rel)
    if not candidates:
        for rel in _list_repo_files(repo_dir):
            if rel.endswith(".py"):
                abs_path = os.path.join(repo_dir, rel)
                if _is_text_file(abs_path):
                    candidates.append(rel)
        if not candidates:
            for rel in _list_repo_files(repo_dir):
                abs_path = os.path.join(repo_dir, rel)
                if _is_text_file(abs_path):
                    candidates.append(rel)
    if not candidates:
        return None
    return sorted(candidates)[0]


def _apply_text_transform(repo_dir: str, relpath: str, transform: Callable[[str], str]) -> Optional[UnifiedDiffPatch]:
    abs_path = os.path.join(repo_dir, relpath)
    original = read_text_normalized(abs_path)
    updated = transform(original)
    if updated == original:
        return None
    write_text_lf(abs_path, updated)
    return unified_diff({relpath: (original, updated)})


def _strip_trailing_ws(text: str) -> str:
    lines = text.split("\n")
    return "\n".join(line.rstrip() for line in lines)


def _ensure_final_newline(text: str) -> str:
    if text.endswith("\n"):
        return text
    return text + "\n"


def _tabs_to_spaces(text: str) -> str:
    return text.replace("\t", "    ")


def _collapse_blank_lines(text: str) -> str:
    lines = text.split("\n")
    out: List[str] = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
        else:
            blank_count = 0
        if blank_count <= 2:
            out.append(line)
    return "\n".join(out)


def _strip_trailing_blank_lines(text: str) -> str:
    lines = text.split("\n")
    while lines and lines[-1].strip() == "":
        lines.pop()
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _sort_import_block(text: str) -> str:
    lines = text.split("\n")
    prefix: List[str] = []
    rest: List[str] = []
    idx = 0
    # Preserve shebang/encoding
    while idx < len(lines) and (lines[idx].startswith("#!") or "coding" in lines[idx]):
        prefix.append(lines[idx])
        idx += 1
    import_lines: List[str] = []
    while idx < len(lines) and (lines[idx].startswith("import ") or lines[idx].startswith("from ") or lines[idx] == ""):
        import_lines.append(lines[idx])
        idx += 1
    rest = lines[idx:]
    imports_only = [ln for ln in import_lines if ln.strip()]
    blank_lines = [ln for ln in import_lines if ln.strip() == ""]
    sorted_imports = sorted(imports_only)
    rebuilt = prefix + sorted_imports
    if blank_lines:
        rebuilt.append("")
    rebuilt += rest
    return "\n".join(rebuilt)


def _ensure_blank_after_imports(text: str) -> str:
    lines = text.split("\n")
    idx = 0
    while idx < len(lines) and (lines[idx].startswith("#!") or "coding" in lines[idx]):
        idx += 1
    while idx < len(lines) and (lines[idx].startswith("import ") or lines[idx].startswith("from ")):
        idx += 1
    if idx < len(lines) and lines[idx].strip() != "":
        lines.insert(idx, "")
    return "\n".join(lines)


def _append_footer_comment(text: str, comment: str) -> str:
    if comment in text:
        return text
    trimmed = text.rstrip("\n")
    return trimmed + "\n" + comment + "\n"


def _insert_header_comment(text: str, comment: str) -> str:
    if text.startswith(comment):
        return text
    return comment + "\n" + text


def _guard_keyerror(text: str, key: str) -> str:
    pattern = re.compile(r"\[['\"]" + re.escape(key) + r"['\"]\]")
    match = pattern.search(text)
    if not match:
        return text
    start = match.start()
    return text[:start] + ".get('" + key + "')" + text[match.end():]


def _guard_nonetype_attribute(text: str, attr: str) -> str:
    pattern = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*" + re.escape(attr))
    match = pattern.search(text)
    if not match:
        return text
    var = match.group(1)
    line_start = text.rfind("\n", 0, match.start()) + 1
    indent_match = re.match(r"\s*", text[line_start:match.start()])
    indent = indent_match.group(0) if indent_match else ""
    guard = indent + f"if {var} is None:\n" + indent + "    return None\n"
    return text[:line_start] + guard + text[line_start:]


def _insert_guard(lines: List[str], idx: int, guard_lines: List[str]) -> List[str]:
    return lines[:idx] + guard_lines + lines[idx:]


def _guard_indexerror(text: str) -> str:
    pattern = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*(\d+)\s*\]")
    match = pattern.search(text)
    if not match:
        return text
    var = match.group(1)
    idx_val = match.group(2)
    line_start = text.rfind("\n", 0, match.start()) + 1
    indent_match = re.match(r"\s*", text[line_start:match.start()])
    indent = indent_match.group(0) if indent_match else ""
    guard = [
        indent + f"if len({var}) <= {idx_val}:",
        indent + "    return None",
    ]
    lines = text.split("\n")
    line_idx = text[:match.start()].count("\n")
    updated = _insert_guard(lines, line_idx, guard)
    return "\n".join(updated)


def _add_missing_import(text: str, name: str) -> str:
    if re.search(rf"^import\s+{re.escape(name)}\b", text, re.M):
        return text
    if re.search(rf"^from\s+{re.escape(name)}\b", text, re.M):
        return text
    lines = text.split("\n")
    idx = 0
    while idx < len(lines) and (lines[idx].startswith("#!") or "coding" in lines[idx]):
        idx += 1
    while idx < len(lines) and (lines[idx].startswith("import ") or lines[idx].startswith("from ")):
        idx += 1
    lines.insert(idx, f"import {name}")
    return "\n".join(lines)


def _wrap_try_except(text: str) -> str:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("import ") or stripped.startswith("from "):
            continue
        if stripped.startswith("def ") or stripped.startswith("class "):
            continue
        indent = line[: len(line) - len(line.lstrip())]
        guarded = [
            indent + "try:",
            indent + "    " + stripped,
            indent + "except Exception:",
            indent + "    return None",
        ]
        lines = _insert_guard(lines, i, guarded)
        lines.pop(i + len(guarded))
        return "\n".join(lines)
    return text


def _initialize_none_default(text: str) -> str:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "==" in line:
            continue
        match = re.match(r"(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if not match:
            continue
        indent, var = match.group(1), match.group(2)
        guard_line = f"{indent}{var} = {var} if {var} is not None else 0"
        if guard_line in text:
            return text
        lines.insert(i + 1, guard_line)
        return "\n".join(lines)
    return text


def _fix_bool_condition(text: str) -> str:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("if ") and stripped.endswith(":"):
            cond = stripped[3:-1].strip()
            lines[i] = line[: len(line) - len(line.lstrip())] + f"if bool({cond}):"
            return "\n".join(lines)
        if stripped.startswith("while ") and stripped.endswith(":"):
            cond = stripped[6:-1].strip()
            lines[i] = line[: len(line) - len(line.lstrip())] + f"while bool({cond}):"
            return "\n".join(lines)
    return text


def _return_early_on_invalid(text: str) -> str:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("def "):
            continue
        match = re.match(r"def\s+\w+\(([^)]*)\)\s*:", stripped)
        if not match:
            continue
        args = [arg.strip() for arg in match.group(1).split(",") if arg.strip()]
        arg_name = ""
        for arg in args:
            name = arg.split("=")[0].strip()
            if name in {"self", "cls"}:
                continue
            arg_name = name
            break
        if not arg_name:
            return text
        indent = line[: len(line) - len(line.lstrip())] + "    "
        guard_line = f"{indent}if {arg_name} is None:"
        return_line = f"{indent}    return None"
        if guard_line in text:
            return text
        lines.insert(i + 1, guard_line)
        lines.insert(i + 2, return_line)
        return "\n".join(lines)
    return text


def _template_trim_trailing_ws(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    rel = _select_target_file(repo_dir, hint, rng)
    if not rel:
        return None
    return _apply_text_transform(repo_dir, rel, _strip_trailing_ws)


def _template_ensure_final_newline(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    rel = _select_target_file(repo_dir, hint, rng)
    if not rel:
        return None
    return _apply_text_transform(repo_dir, rel, _ensure_final_newline)


def _template_tabs_to_spaces(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    rel = _select_target_file(repo_dir, hint, rng)
    if not rel:
        return None
    return _apply_text_transform(repo_dir, rel, _tabs_to_spaces)


def _template_collapse_blank_lines(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    rel = _select_target_file(repo_dir, hint, rng)
    if not rel:
        return None
    return _apply_text_transform(repo_dir, rel, _collapse_blank_lines)


def _template_sort_imports(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    rel = _select_target_file(repo_dir, hint, rng)
    if not rel:
        return None
    return _apply_text_transform(repo_dir, rel, _sort_import_block)


def _template_strip_trailing_blank_lines(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    rel = _select_target_file(repo_dir, hint, rng)
    if not rel:
        return None
    return _apply_text_transform(repo_dir, rel, _strip_trailing_blank_lines)


def _template_blank_after_imports(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    rel = _select_target_file(repo_dir, hint, rng)
    if not rel:
        return None
    return _apply_text_transform(repo_dir, rel, _ensure_blank_after_imports)


def _template_append_footer(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    rel = _select_target_file(repo_dir, hint, rng)
    if not rel:
        return None
    comment = "# rsi: footer"
    return _apply_text_transform(repo_dir, rel, lambda text: _append_footer_comment(text, comment))


def _template_insert_header(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    rel = _select_target_file(repo_dir, hint, rng)
    if not rel:
        return None
    comment = "# rsi: header"
    return _apply_text_transform(repo_dir, rel, lambda text: _insert_header_comment(text, comment))


def _template_guard_keyerror(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    key_match = re.search(r"KeyError: ['\"]([^'\"]+)['\"]", hint.normalized_error)
    if not key_match:
        return None
    rel = _select_anchor_path(repo_dir, hint)
    if not rel:
        return None
    key = key_match.group(1)
    return _apply_text_transform(repo_dir, rel, lambda text: _guard_keyerror(text, key))


def _template_guard_nonetype(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    attr_match = re.search(r"NoneType' object has no attribute ['\"]([^'\"]+)['\"]", hint.normalized_error)
    if not attr_match:
        return None
    rel = _select_anchor_path(repo_dir, hint)
    if not rel:
        return None
    attr = attr_match.group(1)
    return _apply_text_transform(repo_dir, rel, lambda text: _guard_nonetype_attribute(text, attr))


def _template_guard_indexerror(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    if "IndexError" not in hint.normalized_error:
        return None
    rel = _select_anchor_path(repo_dir, hint)
    if not rel:
        return None
    return _apply_text_transform(repo_dir, rel, _guard_indexerror)


def _template_add_missing_import(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    name_match = re.search(r"NameError: name ['\"]([A-Za-z_][A-Za-z0-9_]*)['\"] is not defined", hint.normalized_error)
    if not name_match:
        return None
    rel = _select_anchor_path(repo_dir, hint)
    if not rel:
        return None
    name = name_match.group(1)
    return _apply_text_transform(repo_dir, rel, lambda text: _add_missing_import(text, name))


def _template_wrap_try_except_fallback(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    rel = _select_anchor_path(repo_dir, hint)
    if not rel:
        return None
    return _apply_text_transform(repo_dir, rel, _wrap_try_except)


def _template_initialize_none_default(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    rel = _select_anchor_path(repo_dir, hint)
    if not rel:
        return None
    return _apply_text_transform(repo_dir, rel, _initialize_none_default)


def _template_fix_bool_condition(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    rel = _select_anchor_path(repo_dir, hint)
    if not rel:
        return None
    return _apply_text_transform(repo_dir, rel, _fix_bool_condition)


def _template_return_early_on_invalid(repo_dir: str, hint: DevHint, rng: RNG) -> Optional[UnifiedDiffPatch]:
    rel = _select_anchor_path(repo_dir, hint)
    if not rel:
        return None
    return _apply_text_transform(repo_dir, rel, _return_early_on_invalid)


def list_templates() -> List[Template]:
    return [
        Template("guard_nonetype_attr_v2", _template_guard_nonetype),
        Template("guard_keyerror_v1", _template_guard_keyerror),
        Template("guard_indexerror_v1", _template_guard_indexerror),
        Template("add_missing_import_v1", _template_add_missing_import),
        Template("wrap_try_except_fallback_v1", _template_wrap_try_except_fallback),
        Template("initialize_none_default_v1", _template_initialize_none_default),
        Template("fix_bool_condition_v1", _template_fix_bool_condition),
        Template("return_early_on_invalid_v1", _template_return_early_on_invalid),
        Template("trim_trailing_whitespace_v1", _template_trim_trailing_ws),
        Template("ensure_final_newline_v1", _template_ensure_final_newline),
        Template("tabs_to_spaces_v1", _template_tabs_to_spaces),
        Template("collapse_blank_lines_v1", _template_collapse_blank_lines),
        Template("sort_import_block_v1", _template_sort_imports),
        Template("strip_trailing_blank_lines_v1", _template_strip_trailing_blank_lines),
        Template("blank_after_imports_v1", _template_blank_after_imports),
        Template("append_footer_comment_v1", _template_append_footer),
        Template("insert_header_comment_v1", _template_insert_header),
    ]


def template_ids() -> List[str]:
    return [t.template_id for t in list_templates()]


def get_template(template_id: str) -> Template:
    for t in list_templates():
        if t.template_id == template_id:
            return t
    raise KeyError(f"unknown template_id: {template_id}")


__all__ = [
    "DevHint",
    "UnifiedDiffPatch",
    "Template",
    "list_templates",
    "template_ids",
    "get_template",
]
