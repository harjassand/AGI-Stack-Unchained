from __future__ import annotations

import json

from decimal import Decimal

from cdel.sealed.evalue import EVALUE_SIG_DIGITS, encode_evalue, parse_evalue


def _mantissa_digits(value: str) -> int:
    return len(value.replace(".", ""))


def test_evalue_extreme_magnitude_is_deterministic_and_compact() -> None:
    huge = Decimal("1.234567890123456789012345") * Decimal(1).scaleb(500)
    encoded = encode_evalue(huge).to_dict()
    encoded_repeat = encode_evalue(huge).to_dict()
    assert encoded == encoded_repeat
    assert _mantissa_digits(encoded["mantissa"]) == EVALUE_SIG_DIGITS
    assert len(json.dumps(encoded, sort_keys=True)) < 120
    parse_evalue(encoded, "test evalue")

    tiny = Decimal("1.000000000000000000000000") * Decimal(1).scaleb(-200)
    encoded_tiny = encode_evalue(tiny).to_dict()
    assert _mantissa_digits(encoded_tiny["mantissa"]) == EVALUE_SIG_DIGITS
    parse_evalue(encoded_tiny, "test evalue")
