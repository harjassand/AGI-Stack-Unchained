"""DMPL Merkle helpers (v1).

Phase 2 contract:
  - Params bundle merkle root: commits to (tensor_name, tensor_bin_id_digest32) pairs.
  - Trace chunk merkle root: commits to (chunk_index_str, chunk_bin_id_digest32) pairs.

Algorithm (matches Phase 1 verifier implementation in this repo):
  leaf = sha256(b"DMPL/MERKLE/LEAF/v1\\x00" + name_utf8 + b"\\x00" + digest32)
  node = sha256(b"DMPL/MERKLE/NODE/v1\\x00" + left32 + right32)
  If odd count at a level, duplicate the last leaf/node.
"""

from __future__ import annotations

from typing import Any

from .dmpl_types_v1 import (
    DMPLError,
    DMPL_E_OPSET_MISMATCH,
    DMPL_E_REDUCTION_ORDER_VIOLATION,
    _sha25632_count,
    _sha256_id_from_hex_digest32,
    _sha256_id_to_digest32,
)

_LEAF_PREFIX = b"DMPL/MERKLE/LEAF/v1\x00"
_NODE_PREFIX = b"DMPL/MERKLE/NODE/v1\x00"


def _name_order_key(name: str) -> tuple[int, int | str]:
    # Deterministic order:
    # - If name is decimal digits only, compare numerically (chunk indices).
    # - Otherwise compare lexicographically (tensor names).
    if name.isdigit():
        return (0, int(name))
    return (1, name)


def merkle_root_named_digests_v1(items: list[tuple[str, bytes]]) -> bytes:
    if not isinstance(items, list) or not items:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "empty merkle items"})

    leaf_hashes: list[bytes] = []
    prev_key: tuple[int, int | str] | None = None
    for name, digest32 in items:
        if not isinstance(name, str) or not name:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bad name"})
        if "\x00" in name:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "NUL in name"})
        if not isinstance(digest32, (bytes, bytearray, memoryview)):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bad digest32 type"})
        d = bytes(digest32)
        if len(d) != 32:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bad digest32 len"})

        key = _name_order_key(name)
        if prev_key is not None and key <= prev_key:
            raise DMPLError(reason_code=DMPL_E_REDUCTION_ORDER_VIOLATION, details={"name": name})
        prev_key = key

        name_bytes = name.encode("utf-8", errors="strict")
        leaf_hashes.append(_sha25632_count(_LEAF_PREFIX + name_bytes + b"\x00" + d))

    level = list(leaf_hashes)
    while len(level) > 1:
        if (len(level) & 1) == 1:
            level = level + [level[-1]]
        nxt: list[bytes] = []
        for i in range(0, len(level), 2):
            nxt.append(_sha25632_count(_NODE_PREFIX + level[i] + level[i + 1]))
        level = nxt
    return bytes(level[0])


def compute_params_bundle_merkle_root_v1(bundle_obj: dict, resolver) -> str:
    # Resolver is unused in v1; IDs already commit to bytes. (Bins are verified elsewhere.)
    if not isinstance(bundle_obj, dict):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bundle_obj type"})
    tensors = bundle_obj.get("tensors")
    if not isinstance(tensors, list) or not tensors:
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "bundle tensors"})

    items: list[tuple[str, bytes]] = []
    for row in tensors:
        if not isinstance(row, dict):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "tensor row type"})
        name = row.get("name")
        tensor_bin_id = row.get("tensor_bin_id")
        if not isinstance(name, str) or not isinstance(tensor_bin_id, str):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "tensor row keys"})
        items.append((str(name), _sha256_id_to_digest32(str(tensor_bin_id), reason=DMPL_E_OPSET_MISMATCH)))

    root32 = merkle_root_named_digests_v1(items)
    return _sha256_id_from_hex_digest32(root32)


def compute_chunk_merkle_root_v1(chunk_hashes: list[bytes]) -> bytes:
    if not isinstance(chunk_hashes, list):
        raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "chunk_hashes type"})
    items: list[tuple[str, bytes]] = []
    for idx, h in enumerate(chunk_hashes):
        if not isinstance(h, (bytes, bytearray, memoryview)):
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "chunk hash type"})
        hb = bytes(h)
        if len(hb) != 32:
            raise DMPLError(reason_code=DMPL_E_OPSET_MISMATCH, details={"hint": "chunk hash len"})
        items.append((str(int(idx)), hb))
    return merkle_root_named_digests_v1(items)


__all__ = [
    "merkle_root_named_digests_v1",
    "compute_params_bundle_merkle_root_v1",
    "compute_chunk_merkle_root_v1",
]

