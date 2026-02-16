"""DMPL tensor binary parsing (Q32) (v1).

Phase 2 contract:
  - Load/validate `dmpl_tensor_q32_v1.bin` payloads.
  - Enforce exact shape and signed int64 payload elements.
  - No numpy; deterministic Python containers only.
"""

from __future__ import annotations

import struct
from typing import Any

from .dmpl_types_v1 import DMPLError, DMPL_E_DIM_MISMATCH, DMPL_E_OPSET_MISMATCH

_MAGIC = b"DMPLTQ32"  # 8 bytes
_HDR16 = struct.Struct("<8sII")  # magic[8], version_u32, ndim_u32


def parse_tensor_q32_v1(bin_bytes: bytes) -> tuple[list[int], list[int]]:
    if not isinstance(bin_bytes, (bytes, bytearray, memoryview)):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "bin_bytes type"})
    raw = bytes(bin_bytes)
    if len(raw) < _HDR16.size:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "short header"})
    magic, version_u32, ndim_u32 = _HDR16.unpack_from(raw, 0)
    if bytes(magic) != _MAGIC:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bad tensor magic"})
    if int(version_u32) != 1:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bad tensor version"})
    ndim = int(ndim_u32)
    if ndim < 0:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "negative ndim"})

    off = _HDR16.size
    dims: list[int] = []
    prod = 1
    for _i in range(ndim):
        if off + 4 > len(raw):
            raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "dims truncated"})
        (dim_u32,) = struct.unpack_from("<I", raw, off)
        off += 4
        dim = int(dim_u32)
        dims.append(dim)
        prod *= dim
        if prod < 0:
            raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "shape product overflow"})

    n = int(prod)
    if n < 0:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "negative element count"})
    expected = off + (n * 8)
    if expected != len(raw):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"expected": int(expected), "actual": int(len(raw))})

    values: list[int] = []
    for i in range(n):
        (v,) = struct.unpack_from("<q", raw, off + (i * 8))
        values.append(int(v))
    return [int(d) for d in dims], values


def require_shape(dims: list[int], expected: list[int]) -> None:
    if not isinstance(dims, list) or not isinstance(expected, list):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "dims type"})
    if [int(x) for x in dims] != [int(x) for x in expected]:
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"dims": [int(x) for x in dims], "expected": [int(x) for x in expected]})


def tensor_get(values: list[int], dims: list[int], idxs: list[int]) -> int:
    # Optional helper: deterministic row-major indexing.
    if not isinstance(values, list) or not isinstance(dims, list) or not isinstance(idxs, list):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "tensor_get types"})
    if len(dims) != len(idxs):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "rank mismatch"})
    stride = 1
    index = 0
    for dim, ix in zip(reversed(dims), reversed(idxs), strict=True):
        d = int(dim)
        i = int(ix)
        if d < 0 or i < 0 or i >= d:
            raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "index oob"})
        index += i * stride
        stride *= d
    if index < 0 or index >= len(values):
        raise DMPLError(reason_code=DMPL_E_DIM_MISMATCH, details={"hint": "flat index oob"})
    return int(values[int(index)])


__all__ = [
    "parse_tensor_q32_v1",
    "require_shape",
    "tensor_get",
]

