"""URC Merkle memory v1 (deterministic, fail-closed).

Phase 7 directive (normative):
  - Deterministic page + page-table node binary formats (UPG1 / UPT1).
  - Page-table semantics: PT_DEPTH_U32=4 over page_id bytes [b3,b2,b1,b0].
  - Missing page reads return zeros; missing pages are created as all-zero on write.
  - All hashes are raw SHA256 digests (digest32 bytes).

This module is RE2: deterministic and fail-closed.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Any, Callable, Final

from ..omega_common_v1 import fail

PAGE_SHIFT_U32: Final[int] = 12
PAGE_SIZE_BYTES: Final[int] = 1 << PAGE_SHIFT_U32  # 4096
PT_FANOUT_U32: Final[int] = 256
PT_DEPTH_U32: Final[int] = 4

ZERO32: Final[bytes] = b"\x00" * 32

_UPG1_HDR = struct.Struct("<4s5I")  # magic, version, page_id, page_shift, data_len, reserved
_UPT1_HDR = struct.Struct("<4s5I")  # magic, version, level, fanout, count, reserved


def _sha25632(data: bytes) -> bytes:
    return hashlib.sha256(bytes(data)).digest()


def _require_bytes32(value: Any) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        fail("SCHEMA_FAIL")
    b = bytes(value)
    if len(b) != 32:
        fail("SCHEMA_FAIL")
    return b


def _require_u64(value: Any) -> int:
    if not isinstance(value, int) or value < 0 or value > 0xFFFFFFFFFFFFFFFF:
        fail("SCHEMA_FAIL")
    return int(value)


def _require_u32(value: Any) -> int:
    if not isinstance(value, int) or value < 0 or value > 0xFFFFFFFF:
        fail("SCHEMA_FAIL")
    return int(value)


def urc_derive_page_relpath_v1(page_hash32: bytes) -> str:
    h = _require_bytes32(page_hash32)
    hex64 = h.hex()
    return f"polymath/registry/eudrs_u/memory/urc_pages/sha256_{hex64}.urc_page_v1.bin"


def urc_derive_ptnode_relpath_v1(node_hash32: bytes) -> str:
    h = _require_bytes32(node_hash32)
    hex64 = h.hex()
    return f"polymath/registry/eudrs_u/memory/urc_pt/sha256_{hex64}.urc_page_table_node_v1.bin"


def urc_parse_page_v1(page_bytes: bytes) -> tuple[int, bytes]:
    """Returns (page_id_u32, page_data_4096). Validates format fail-closed."""

    if not isinstance(page_bytes, (bytes, bytearray, memoryview)):
        fail("SCHEMA_FAIL")
    mv = memoryview(bytes(page_bytes))
    # Spec fields sum to 4120 bytes (header 24 + 4096 data).
    if len(mv) != _UPG1_HDR.size + PAGE_SIZE_BYTES:
        fail("SCHEMA_FAIL")

    magic, ver_u32, page_id_u32, page_shift_u32, data_len_u32, reserved_u32 = _UPG1_HDR.unpack_from(mv, 0)
    if bytes(magic) != b"UPG1":
        fail("SCHEMA_FAIL")
    if int(ver_u32) != 1:
        fail("SCHEMA_FAIL")
    if int(page_shift_u32) != PAGE_SHIFT_U32:
        fail("SCHEMA_FAIL")
    if int(data_len_u32) != PAGE_SIZE_BYTES:
        fail("SCHEMA_FAIL")
    if int(reserved_u32) != 0:
        fail("SCHEMA_FAIL")

    page_id = _require_u32(int(page_id_u32))
    data = bytes(mv[_UPG1_HDR.size : _UPG1_HDR.size + PAGE_SIZE_BYTES])
    if len(data) != PAGE_SIZE_BYTES:
        fail("SCHEMA_FAIL")
    return page_id, data


def urc_parse_ptnode_v1(node_bytes: bytes) -> tuple[int, list[bytes]]:
    """Returns (level_u32, child_hash32[256]). Validates format fail-closed."""

    if not isinstance(node_bytes, (bytes, bytearray, memoryview)):
        fail("SCHEMA_FAIL")
    mv = memoryview(bytes(node_bytes))
    if len(mv) != _UPT1_HDR.size + (PT_FANOUT_U32 * 32):
        fail("SCHEMA_FAIL")

    magic, ver_u32, level_u32, fanout_u32, count_u32, reserved_u32 = _UPT1_HDR.unpack_from(mv, 0)
    if bytes(magic) != b"UPT1":
        fail("SCHEMA_FAIL")
    if int(ver_u32) != 1:
        fail("SCHEMA_FAIL")
    level = int(level_u32)
    if level not in (0, 1, 2, 3):
        fail("SCHEMA_FAIL")
    if int(fanout_u32) != PT_FANOUT_U32:
        fail("SCHEMA_FAIL")
    if int(reserved_u32) != 0:
        fail("SCHEMA_FAIL")

    children: list[bytes] = []
    nonzero = 0
    off = _UPT1_HDR.size
    for i in range(PT_FANOUT_U32):
        ch = bytes(mv[off + (i * 32) : off + ((i + 1) * 32)])
        if len(ch) != 32:
            fail("SCHEMA_FAIL")
        if ch != ZERO32:
            nonzero += 1
        children.append(ch)

    if int(count_u32) != int(nonzero):
        fail("SCHEMA_FAIL")
    return int(level), children


def urc_pt_lookup_page_hash_v1(
    *,
    pt_root_hash32: bytes,
    page_id_u32: int,
    load_bytes_by_hash32: Callable[[bytes, str], bytes],
) -> bytes:
    """Returns page_hash32 or ZERO32 if absent. Validates all loaded node hashes."""

    if not callable(load_bytes_by_hash32):
        fail("SCHEMA_FAIL")
    root = _require_bytes32(pt_root_hash32)
    page_id = _require_u32(page_id_u32)

    if root == ZERO32:
        return ZERO32

    b3 = (page_id >> 24) & 0xFF
    b2 = (page_id >> 16) & 0xFF
    b1 = (page_id >> 8) & 0xFF
    b0 = page_id & 0xFF
    idx_by_level = (b3, b2, b1, b0)

    cur_hash32 = root
    for expect_level in range(PT_DEPTH_U32):
        node_bytes = load_bytes_by_hash32(bytes(cur_hash32), "ptnode")
        if not isinstance(node_bytes, (bytes, bytearray, memoryview)):
            fail("SCHEMA_FAIL")
        node_raw = bytes(node_bytes)
        if _sha25632(node_raw) != bytes(cur_hash32):
            fail("NONDETERMINISTIC")

        level_u32, children = urc_parse_ptnode_v1(node_raw)
        if int(level_u32) != int(expect_level):
            fail("SCHEMA_FAIL")

        idx = int(idx_by_level[expect_level])
        nxt = children[idx]
        if nxt == ZERO32:
            return ZERO32
        if expect_level == PT_DEPTH_U32 - 1:
            return bytes(nxt)
        cur_hash32 = bytes(nxt)

    fail("SCHEMA_FAIL")
    return ZERO32


def urc_mem_read64_v1(
    *,
    pt_root_hash32: bytes,
    addr_u64: int,
    load_bytes_by_hash32: Callable[[bytes, str], bytes],
) -> int:
    """Returns u64. Absent page => 0. Requires 8-byte alignment."""

    root = _require_bytes32(pt_root_hash32)
    addr = _require_u64(addr_u64)
    if (addr & 7) != 0:
        fail("SCHEMA_FAIL")

    page_id = _require_u32((addr >> PAGE_SHIFT_U32) & 0xFFFFFFFF)
    off = int(addr & (PAGE_SIZE_BYTES - 1))
    if off < 0 or off > (PAGE_SIZE_BYTES - 8):
        fail("SCHEMA_FAIL")

    page_hash32 = urc_pt_lookup_page_hash_v1(pt_root_hash32=root, page_id_u32=page_id, load_bytes_by_hash32=load_bytes_by_hash32)
    if page_hash32 == ZERO32:
        return 0

    page_bytes = load_bytes_by_hash32(bytes(page_hash32), "page")
    if not isinstance(page_bytes, (bytes, bytearray, memoryview)):
        fail("SCHEMA_FAIL")
    raw = bytes(page_bytes)
    if _sha25632(raw) != bytes(page_hash32):
        fail("NONDETERMINISTIC")
    pid2, data = urc_parse_page_v1(raw)
    if int(pid2) != int(page_id):
        fail("SCHEMA_FAIL")

    return int(struct.unpack_from("<Q", data, off)[0])


def _encode_page_bytes(*, page_id_u32: int, data_4096: bytes) -> bytes:
    if not isinstance(data_4096, (bytes, bytearray, memoryview)):
        fail("SCHEMA_FAIL")
    data = bytes(data_4096)
    if len(data) != PAGE_SIZE_BYTES:
        fail("SCHEMA_FAIL")
    hdr = _UPG1_HDR.pack(
        b"UPG1",
        1,
        _require_u32(page_id_u32),
        PAGE_SHIFT_U32,
        PAGE_SIZE_BYTES,
        0,
    )
    out = hdr + data
    if len(out) != _UPG1_HDR.size + PAGE_SIZE_BYTES:
        fail("SCHEMA_FAIL")
    return out


def _encode_ptnode_bytes(*, level_u32: int, children_256: list[bytes]) -> bytes:
    level = int(level_u32)
    if level not in (0, 1, 2, 3):
        fail("SCHEMA_FAIL")
    if not isinstance(children_256, list) or len(children_256) != PT_FANOUT_U32:
        fail("SCHEMA_FAIL")
    nonzero = 0
    body = bytearray()
    for ch in children_256:
        b = _require_bytes32(ch)
        if b != ZERO32:
            nonzero += 1
        body += b
    hdr = _UPT1_HDR.pack(
        b"UPT1",
        1,
        level,
        PT_FANOUT_U32,
        int(nonzero),
        0,
    )
    out = bytes(hdr + body)
    if len(out) != _UPT1_HDR.size + (PT_FANOUT_U32 * 32):
        fail("SCHEMA_FAIL")
    return out


def urc_mem_write64_v1(
    *,
    pt_root_hash32: bytes,
    addr_u64: int,
    value_u64: int,
    load_bytes_by_hash32: Callable[[bytes, str], bytes],
) -> tuple[bytes, dict[bytes, bytes], dict[bytes, bytes]]:
    """
    Returns:
      (pt_root_after32,
       new_pages_by_hash32: {page_hash32: page_bytes},
       new_ptnodes_by_hash32: {node_hash32: node_bytes})
    Deterministically creates/updates exactly the path nodes and page.
    """

    if not callable(load_bytes_by_hash32):
        fail("SCHEMA_FAIL")
    root = _require_bytes32(pt_root_hash32)
    addr = _require_u64(addr_u64)
    val = _require_u64(value_u64)
    if (addr & 7) != 0:
        fail("SCHEMA_FAIL")

    page_id = _require_u32((addr >> PAGE_SHIFT_U32) & 0xFFFFFFFF)
    off = int(addr & (PAGE_SIZE_BYTES - 1))
    if off < 0 or off > (PAGE_SIZE_BYTES - 8):
        fail("SCHEMA_FAIL")

    # Load existing page data or synthesize zeros.
    page_hash_before32 = urc_pt_lookup_page_hash_v1(pt_root_hash32=root, page_id_u32=page_id, load_bytes_by_hash32=load_bytes_by_hash32)
    if page_hash_before32 == ZERO32:
        data_before = b"\x00" * PAGE_SIZE_BYTES
    else:
        raw_page = bytes(load_bytes_by_hash32(bytes(page_hash_before32), "page"))
        if _sha25632(raw_page) != bytes(page_hash_before32):
            fail("NONDETERMINISTIC")
        pid2, data2 = urc_parse_page_v1(raw_page)
        if int(pid2) != int(page_id):
            fail("SCHEMA_FAIL")
        data_before = bytes(data2)

    data_mut = bytearray(data_before)
    struct.pack_into("<Q", data_mut, off, int(val) & 0xFFFFFFFFFFFFFFFF)
    page_bytes_after = _encode_page_bytes(page_id_u32=page_id, data_4096=bytes(data_mut))
    page_hash_after32 = _sha25632(page_bytes_after)

    new_pages: dict[bytes, bytes] = {bytes(page_hash_after32): bytes(page_bytes_after)}

    # Path bytes.
    b3 = (page_id >> 24) & 0xFF
    b2 = (page_id >> 16) & 0xFF
    b1 = (page_id >> 8) & 0xFF
    b0 = page_id & 0xFF

    def _load_children(node_hash32: bytes, expect_level: int) -> list[bytes]:
        if node_hash32 == ZERO32:
            return [ZERO32] * PT_FANOUT_U32
        raw = bytes(load_bytes_by_hash32(bytes(node_hash32), "ptnode"))
        if _sha25632(raw) != bytes(node_hash32):
            fail("NONDETERMINISTIC")
        lvl, children = urc_parse_ptnode_v1(raw)
        if int(lvl) != int(expect_level):
            fail("SCHEMA_FAIL")
        return list(children)

    # Load existing children arrays (if present) to preserve siblings.
    root_children = _load_children(root, 0) if root != ZERO32 else [ZERO32] * PT_FANOUT_U32
    lvl1_hash_before = bytes(root_children[b3])
    lvl1_children = _load_children(lvl1_hash_before, 1)

    lvl2_hash_before = bytes(lvl1_children[b2])
    lvl2_children = _load_children(lvl2_hash_before, 2)

    lvl3_hash_before = bytes(lvl2_children[b1])
    lvl3_children = _load_children(lvl3_hash_before, 3)

    # Rebuild bottom-up.
    lvl3_children[b0] = bytes(page_hash_after32)
    lvl3_bytes = _encode_ptnode_bytes(level_u32=3, children_256=lvl3_children)
    lvl3_hash_after32 = _sha25632(lvl3_bytes)

    lvl2_children[b1] = bytes(lvl3_hash_after32)
    lvl2_bytes = _encode_ptnode_bytes(level_u32=2, children_256=lvl2_children)
    lvl2_hash_after32 = _sha25632(lvl2_bytes)

    lvl1_children[b2] = bytes(lvl2_hash_after32)
    lvl1_bytes = _encode_ptnode_bytes(level_u32=1, children_256=lvl1_children)
    lvl1_hash_after32 = _sha25632(lvl1_bytes)

    root_children[b3] = bytes(lvl1_hash_after32)
    root_bytes = _encode_ptnode_bytes(level_u32=0, children_256=root_children)
    root_hash_after32 = _sha25632(root_bytes)

    new_nodes: dict[bytes, bytes] = {
        bytes(lvl3_hash_after32): bytes(lvl3_bytes),
        bytes(lvl2_hash_after32): bytes(lvl2_bytes),
        bytes(lvl1_hash_after32): bytes(lvl1_bytes),
        bytes(root_hash_after32): bytes(root_bytes),
    }

    return bytes(root_hash_after32), new_pages, new_nodes


__all__ = [
    "PAGE_SHIFT_U32",
    "PAGE_SIZE_BYTES",
    "PT_DEPTH_U32",
    "PT_FANOUT_U32",
    "ZERO32",
    "urc_derive_page_relpath_v1",
    "urc_derive_ptnode_relpath_v1",
    "urc_mem_read64_v1",
    "urc_mem_write64_v1",
    "urc_parse_page_v1",
    "urc_parse_ptnode_v1",
    "urc_pt_lookup_page_hash_v1",
]

