"""Types and validators for canonical GIR v1."""

from __future__ import annotations

from typing import Any


def _require_str(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    return value


def _require_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    out: list[str] = []
    for row in value:
        out.append(_require_str(row))
    return out


def normalize_gir_program(program: dict[str, Any]) -> dict[str, Any]:
    """Normalize GIR shape and fail closed for malformed input."""
    if not isinstance(program, dict):
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    schema_version = _require_str(program.get("schema_version"))
    if schema_version != "gir_program_v1":
        raise RuntimeError("INVALID:SCHEMA_FAIL")

    modules_raw = program.get("modules")
    if not isinstance(modules_raw, list):
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    modules: list[dict[str, Any]] = []
    for module in modules_raw:
        if not isinstance(module, dict):
            raise RuntimeError("INVALID:SCHEMA_FAIL")
        module_relpath = _require_str(module.get("module_relpath"))
        functions_raw = module.get("functions")
        if not isinstance(functions_raw, list):
            raise RuntimeError("INVALID:SCHEMA_FAIL")
        functions: list[dict[str, Any]] = []
        for fn in functions_raw:
            if not isinstance(fn, dict):
                raise RuntimeError("INVALID:SCHEMA_FAIL")
            fn_name = _require_str(fn.get("function_name"))
            entry_block_id = _require_str(fn.get("entry_block_id"))
            args = _require_str_list(fn.get("args"))
            blocks_raw = fn.get("blocks")
            if not isinstance(blocks_raw, list):
                raise RuntimeError("INVALID:SCHEMA_FAIL")
            blocks: list[dict[str, Any]] = []
            for block in blocks_raw:
                if not isinstance(block, dict):
                    raise RuntimeError("INVALID:SCHEMA_FAIL")
                block_id = _require_str(block.get("block_id"))
                successors = _require_str_list(block.get("successors"))
                ops_raw = block.get("ops")
                if not isinstance(ops_raw, list):
                    raise RuntimeError("INVALID:SCHEMA_FAIL")
                ops: list[dict[str, Any]] = []
                for op in ops_raw:
                    if not isinstance(op, dict):
                        raise RuntimeError("INVALID:SCHEMA_FAIL")
                    op_id = _require_str(op.get("op_id"))
                    opcode = _require_str(op.get("opcode"))
                    defs = _require_str_list(op.get("defs"))
                    uses = _require_str_list(op.get("uses"))
                    attrs_raw = op.get("attrs", {})
                    if not isinstance(attrs_raw, dict):
                        raise RuntimeError("INVALID:SCHEMA_FAIL")
                    metadata_raw = op.get("metadata", {})
                    if not isinstance(metadata_raw, dict):
                        raise RuntimeError("INVALID:SCHEMA_FAIL")
                    ops.append(
                        {
                            "op_id": op_id,
                            "opcode": opcode,
                            "defs": defs,
                            "uses": uses,
                            "attrs": dict(attrs_raw),
                            "metadata": dict(metadata_raw),
                        }
                    )
                blocks.append(
                    {
                        "block_id": block_id,
                        "successors": successors,
                        "ops": ops,
                    }
                )
            functions.append(
                {
                    "function_name": fn_name,
                    "args": args,
                    "entry_block_id": entry_block_id,
                    "blocks": blocks,
                }
            )
        modules.append(
            {
                "module_relpath": module_relpath,
                "functions": functions,
            }
        )
    return {
        "schema_version": "gir_program_v1",
        "modules": modules,
    }


__all__ = ["normalize_gir_program"]

