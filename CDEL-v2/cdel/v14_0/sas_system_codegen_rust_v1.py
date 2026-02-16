"""Deterministic Rust codegen for SAS-System v14.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class SASSystemCodegenError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise SASSystemCodegenError(reason)


def _rust_ident(name: str) -> str:
    if name == "_":
        return "_"
    safe = []
    for ch in name:
        if ch.isalnum() or ch == "_":
            safe.append(ch)
        else:
            safe.append("_")
    out = "".join(safe)
    if not out:
        return "_var"
    if out[0].isdigit():
        out = f"v_{out}"
    return out


def _expr(expr: dict[str, Any]) -> str:
    if "lit" in expr:
        return f"{int(expr['lit'])}i64"
    if "var" in expr:
        return _rust_ident(str(expr["var"]))
    if "get" in expr:
        key = str(expr["get"]).split(".", 1)[-1]
        return f"job.{_rust_ident(key)}"
    if "bin" in expr:
        op = expr["bin"]
        a = _expr(expr["a"])
        b = _expr(expr["b"])
        op_map = {"add": "+", "sub": "-", "mul": "*", "div": "/"}
        if op not in op_map:
            _fail("INVALID:IR_UNSUPPORTED_NODE")
        return f"({a} {op_map[op]} {b})"
    _fail("INVALID:IR_UNSUPPORTED_NODE")
    return "0i64"


def _cond(expr: dict[str, Any]) -> str:
    if "cmp" in expr:
        op = expr["cmp"]
        a = _expr(expr["a"])
        b = _expr(expr["b"])
        op_map = {"lt": "<", "le": "<=", "eq": "=="}
        if op not in op_map:
            _fail("INVALID:IR_UNSUPPORTED_NODE")
        return f"({a} {op_map[op]} {b})"
    if "bool" in expr:
        op = expr["bool"]
        a = _cond(expr["a"])
        b = _cond(expr["b"])
        op_map = {"and": "&&", "or": "||"}
        if op not in op_map:
            _fail("INVALID:IR_UNSUPPORTED_NODE")
        return f"({a} {op_map[op]} {b})"
    if "not" in expr:
        return f"(!{_cond(expr['not'])})"
    _fail("INVALID:IR_UNSUPPORTED_NODE")
    return "false"


def _stmt(stmt: dict[str, Any], indent: str) -> list[str]:
    op = stmt.get("op")
    lines: list[str] = []
    if op == "assign":
        lhs = _rust_ident(str(stmt["lhs"]))
        rhs = _expr(stmt["rhs"])
        lines.append(f"{indent}{lhs} = {rhs};")
        return lines
    if op == "add_assign":
        lhs = _rust_ident(str(stmt["lhs"]))
        rhs = _expr(stmt["rhs"])
        lines.append(f"{indent}{lhs} += {rhs};")
        return lines
    if op == "if":
        cond = _cond(stmt["cond"])
        lines.append(f"{indent}if {cond} {{")
        for inner in stmt.get("then", []):
            lines.extend(_stmt(inner, indent + "    "))
        lines.append(f"{indent}}} else {{")
        for inner in stmt.get("else", []):
            lines.extend(_stmt(inner, indent + "    "))
        lines.append(f"{indent}}}")
        return lines
    if op == "for_range":
        var = _rust_ident(str(stmt.get("var")))
        start = _expr(stmt["start"])
        end = _expr(stmt["end"])
        if var == "_":
            lines.append(f"{indent}for _ in {start}..{end} {{")
        else:
            lines.append(f"{indent}for {var} in {start}..{end} {{")
        for inner in stmt.get("body", []):
            lines.extend(_stmt(inner, indent + "    "))
        lines.append(f"{indent}}}")
        return lines
    _fail("INVALID:IR_UNSUPPORTED_NODE")
    return lines


def render_lib_rs(ir: dict[str, Any]) -> str:
    locals_list = [str(x) for x in ir.get("locals", []) if isinstance(x, str)]
    init_lines: list[str] = []
    for name in locals_list:
        if name == "_":
            continue
        ident = _rust_ident(name)
        init_lines.append(f"    let mut {ident}: i64 = 0;")

    body_lines: list[str] = []
    for stmt in ir.get("stmts", []):
        body_lines.extend(_stmt(stmt, "    "))

    ret = ir.get("return", {})
    def _ret_var(key: str) -> str:
        slot = ret.get(key) or {}
        var = slot.get("var", "")
        return _rust_ident(str(var))

    sqrt_var = _ret_var("sqrt_calls")
    div_var = _ret_var("div_calls")
    pair_var = _ret_var("pair_terms_evaluated")
    work_var = _ret_var("work_cost_total")

    # Canonical JSON with sorted keys.
    out_json = (
        'format!("{{\\\"div_calls\\\":{},\\\"pair_terms_evaluated\\\":{},'
        '\\\"schema\\\":\\\"sas_science_workmeter_out_v1\\\",'
        '\\\"spec_version\\\":\\\"v14_0\\\",'
        '\\\"sqrt_calls\\\":{},\\\"work_cost_total\\\":{}}}",' 
        f" {div_var}, {pair_var}, {sqrt_var}, {work_var})"
    )

    lib = [
        "#![forbid(unsafe_code)]",
        "use pyo3::prelude::*;",
        "use pyo3::types::PyBytes;",
        "use serde::Deserialize;",
        "",
        "#[derive(Deserialize)]",
        "struct Job {",
        "    schema: String,",
        "    spec_version: String,",
        "    dim: i64,",
        "    norm_pow: i64,",
        "    pair_terms: i64,",
        "    hooke_terms: i64,",
        "}",
        "",
        "#[pyfunction]",
        "pub fn compute(py: Python, job_json_bytes: &PyBytes) -> PyResult<Py<PyBytes>> {",
        "    let bytes = job_json_bytes.as_bytes();",
        "    let job: Job = serde_json::from_slice(bytes).map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;",
        "",
    ]
    lib.extend(init_lines)
    lib.append("")
    lib.extend(body_lines)
    lib.append("")
    lib.append(f"    let out_json = {out_json};")
    lib.extend(
        [
            "    let out_bytes = out_json.as_bytes();",
            "    Ok(PyBytes::new(py, out_bytes).into())",
            "}",
            "",
            "#[pymodule]",
            "fn cdel_workmeter_rs_v1(_py: Python, m: &PyModule) -> PyResult<()> {",
            "    m.add_function(wrap_pyfunction!(compute, m)?)?;",
            "    Ok(())",
            "}",
        ]
    )
    return "\n".join(lib) + "\n"


def render_cli_rs() -> str:
    return (
        "#![forbid(unsafe_code)]\n"
        "use std::io::{self, Read};\n"
        "use pyo3::prelude::*;\n"
        "use pyo3::types::PyBytes;\n"
        "use cdel_workmeter_rs_v1::compute;\n\n"
        "fn main() {\n"
        "    let mut input = String::new();\n"
        "    io::stdin().read_to_string(&mut input).unwrap();\n"
        "    Python::with_gil(|py| {\n"
        "        let bytes = PyBytes::new(py, input.as_bytes());\n"
        "        let out = compute(py, bytes).unwrap();\n"
        "        let out_bytes = out.as_ref(py).as_bytes();\n"
        "        println!(\"{}\", String::from_utf8_lossy(out_bytes));\n"
        "    });\n"
        "}\n"
    )


def write_rust_sources(ir: dict[str, Any], crate_dir: Path) -> dict[str, Path]:
    src_dir = crate_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    lib_path = src_dir / "lib.rs"
    lib_path.write_text(render_lib_rs(ir), encoding="utf-8")
    bin_dir = src_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    cli_path = bin_dir / "workmeter_cli.rs"
    cli_path.write_text(render_cli_rs(), encoding="utf-8")
    return {"lib": lib_path, "cli": cli_path}


__all__ = ["render_lib_rs", "write_rust_sources", "SASSystemCodegenError"]
