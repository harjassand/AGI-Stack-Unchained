from __future__ import annotations

import random

from cdel.v17_0.val.val_decode_aarch64_v1 import ValDecodeError, decode_trace_py


def test_val_decoder_fuzz() -> None:
    rng = random.Random(170001)
    accepted = 0
    for _ in range(50_000):
        word = rng.getrandbits(32)
        raw = word.to_bytes(4, "little", signed=False)
        try:
            trace = decode_trace_py(raw)
        except ValDecodeError as exc:
            assert str(exc) == "INVALID:VAL_DECODE_UNSUPPORTED_OPCODE"
            continue

        accepted += 1
        for row in trace["instructions"]:
            assert isinstance(row["mnemonic"], str)
            assert isinstance(row["operands_norm"], list)
    assert accepted >= 0
