from __future__ import annotations

import hashlib

from cdel.v18_0.eudrs_u.eudrs_u_merkle_v1 import merkle_fanout_v1


def test_merkle_fanout_v1_empty_is_zero() -> None:
    assert merkle_fanout_v1(leaf_hash32=[], fanout_u32=4) == (b"\x00" * 32)


def test_merkle_fanout_v1_golden_vectors_f4() -> None:
    # Golden vectors from Phase 1 directive.
    leaves = [hashlib.sha256(f"leaf{i}".encode("ascii")).digest() for i in range(5)]
    assert leaves[0].hex() == "4d5a9584d985e8fb44015a8affa9b76f1ff16f65e61df7156d8e8159e1448978"
    assert leaves[1].hex() == "d103cfb5e499c566904787533afbdec56f95492d67fc00e2c0d0161ba99653f1"
    assert leaves[2].hex() == "5038da95330ba16edb486954197e37eb777c3047327ca54df4199c35c5edc17a"
    assert leaves[3].hex() == "f2764fd79fdab5132fc349ba555c9c56ff0c935c889c17ebe3d61315d780934e"
    assert leaves[4].hex() == "565fb0e0cefe32cf4000e4a67ddec8820111a733aa8ba010d242a5fe477e04c4"

    root_3 = merkle_fanout_v1(leaf_hash32=leaves[:3], fanout_u32=4)
    assert root_3.hex() == "7faf73cb68384ca08b9d4c478a0a27d58f42b87671deac834a5afa0fe3a64ecf"

    root_5 = merkle_fanout_v1(leaf_hash32=leaves[:5], fanout_u32=4)
    assert root_5.hex() == "767456e4c587d44f9665406eb42d4740e0979fe8db2d8f581289f4b49cf717f9"

