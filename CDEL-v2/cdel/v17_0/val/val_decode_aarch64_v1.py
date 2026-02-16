"""Deterministic bytes-first decoder for VAL v17.0."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...v1_7r.canon import canon_bytes, sha256_prefixed


class ValDecodeError(ValueError):
    pass


@dataclass(frozen=True)
class DecodedInsn:
    pc_u32: int
    opcode_u32: int
    mnemonic: str
    operands_norm: tuple[str, ...]

    def as_obj(self) -> dict[str, Any]:
        return {
            "pc_u32": int(self.pc_u32),
            "opcode_u32": int(self.opcode_u32),
            "mnemonic": str(self.mnemonic),
            "operands_norm": list(self.operands_norm),
        }


# Python implementation table.
PY_DECODE_TABLE: dict[int, tuple[str, tuple[str, ...]]] = {
    0xD2800000: ("mov", ("x0", "#0")),
    0xD65F03C0: ("ret", ()),
    0x4CDF7000: ("ld1", ("{v0.16b}", "[x0],#16")),
    0x6E201C00: ("eor", ("v0.16b", "v0.16b", "v0.16b")),
    0x4C9F7020: ("st1", ("{v0.16b}", "[x1],#16")),
    0x10000000: ("ldr", ("w3", "[x0,#0]")),
    0x10000001: ("ld1", ("{v0.16b}", "[x1],#64")),
    0x10000002: ("sha256h", ("q0", "q1", "v2.4s")),
    0x10000003: ("str", ("w3", "[x0,#0]")),
    0x10000004: ("subs", ("x2", "x2", "#1")),
    0x10000005: ("b.ne", ("-8",)),
    0x10000006: ("ret", ()),
    0x10000007: ("sha256h2", ("q0", "q1", "v2.4s")),
    0x10000008: ("sha256su0", ("v3.4s", "v4.4s")),
    0x10000009: ("sha256su1", ("v3.4s", "v5.4s", "v6.4s")),
    0xF0000001: ("svc", ("#0",)),
    0xF0000002: ("br", ("x0",)),
    0xF0000003: ("blr", ("x1",)),
    0xF0000004: ("add", ("sp", "sp", "#16")),
    0xF0000005: ("str", ("w0", "[x0,#32]")),
    0xF0000006: ("ldr", ("w0", "[x1,#4096]")),
    0xF0000007: ("b.ne", ("-4",)),
    0xF0000008: ("mov", ("x16", "x0")),
    0xF0000009: ("str", ("w0", "[x4,#0]")),
}

# Rust-model implementation table represented independently as rows.
RS_DECODE_ROWS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (0xD2800000, "mov", ("x0", "#0")),
    (0xD65F03C0, "ret", ()),
    (0x4CDF7000, "ld1", ("{v0.16b}", "[x0],#16")),
    (0x6E201C00, "eor", ("v0.16b", "v0.16b", "v0.16b")),
    (0x4C9F7020, "st1", ("{v0.16b}", "[x1],#16")),
    (0x10000000, "ldr", ("w3", "[x0,#0]")),
    (0x10000001, "ld1", ("{v0.16b}", "[x1],#64")),
    (0x10000002, "sha256h", ("q0", "q1", "v2.4s")),
    (0x10000003, "str", ("w3", "[x0,#0]")),
    (0x10000004, "subs", ("x2", "x2", "#1")),
    (0x10000005, "b.ne", ("-8",)),
    (0x10000006, "ret", ()),
    (0x10000007, "sha256h2", ("q0", "q1", "v2.4s")),
    (0x10000008, "sha256su0", ("v3.4s", "v4.4s")),
    (0x10000009, "sha256su1", ("v3.4s", "v5.4s", "v6.4s")),
    (0xF0000001, "svc", ("#0",)),
    (0xF0000002, "br", ("x0",)),
    (0xF0000003, "blr", ("x1",)),
    (0xF0000004, "add", ("sp", "sp", "#16")),
    (0xF0000005, "str", ("w0", "[x0,#32]")),
    (0xF0000006, "ldr", ("w0", "[x1,#4096]")),
    (0xF0000007, "b.ne", ("-4",)),
    (0xF0000008, "mov", ("x16", "x0")),
    (0xF0000009, "str", ("w0", "[x4,#0]")),
)
RS_DECODE_TABLE: dict[int, tuple[str, tuple[str, ...]]] = {row[0]: (row[1], row[2]) for row in RS_DECODE_ROWS}


def _iter_words(code_bytes: bytes) -> list[int]:
    if not code_bytes or (len(code_bytes) % 4 != 0):
        raise ValDecodeError("INVALID:VAL_DECODE_UNSUPPORTED_OPCODE")
    return [int.from_bytes(code_bytes[i : i + 4], "little", signed=False) for i in range(0, len(code_bytes), 4)]


def _decode_with_table(code_bytes: bytes, table: dict[int, tuple[str, tuple[str, ...]]]) -> dict[str, Any]:
    insns: list[dict[str, Any]] = []
    for idx, word in enumerate(_iter_words(code_bytes)):
        row = table.get(word)
        if row is None:
            raise ValDecodeError("INVALID:VAL_DECODE_UNSUPPORTED_OPCODE")
        insn = DecodedInsn(
            pc_u32=idx * 4,
            opcode_u32=word,
            mnemonic=row[0],
            operands_norm=tuple(row[1]),
        )
        insns.append(insn.as_obj())
    return {
        "schema_version": "val_decoded_trace_v1",
        "instructions": insns,
    }


def decode_trace_py(code_bytes: bytes) -> dict[str, Any]:
    return _decode_with_table(code_bytes, PY_DECODE_TABLE)


def decode_trace_rs(code_bytes: bytes) -> dict[str, Any]:
    # Keep algorithm independent from the Python path: table built from tuple rows.
    return _decode_with_table(code_bytes, RS_DECODE_TABLE)


def decoded_trace_hash(decoded_trace: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(decoded_trace))


__all__ = [
    "ValDecodeError",
    "decode_trace_py",
    "decode_trace_rs",
    "decoded_trace_hash",
]
