from __future__ import annotations

from fractions import Fraction

from cdel.v1_7r.science.eval_v1 import action_is_valid, decode_rational, encode_rational


def test_encode_decode_int() -> None:
    assert encode_rational(0) == "0"
    assert encode_rational(7) == "7"
    assert encode_rational(-3) == "-3"
    assert decode_rational("0") == 0
    assert decode_rational("7") == 7
    assert decode_rational("-3") == -3


def test_encode_decode_fraction() -> None:
    assert encode_rational(Fraction(63, 64)) == "63/64"
    out = decode_rational("63/64")
    assert isinstance(out, Fraction)
    assert out == Fraction(63, 64)


def test_decode_rejects_unreduced() -> None:
    try:
        decode_rational("2/4")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_decode_rejects_bad_denominator() -> None:
    for s in ["1/0", "1/-2"]:
        try:
            decode_rational(s)
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_decode_rejects_noncanonical_ints() -> None:
    for s in ["01", "-0", "+1", " 1", "1 "]:
        try:
            decode_rational(s)
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_action_is_valid_strict() -> None:
    assert action_is_valid({"name": "EVAL", "args": {}}) is True
    assert action_is_valid({"name": "NEXT_PARAM", "args": {}}) is True

    # Missing keys / extra keys
    assert action_is_valid({"name": "EVAL"}) is False
    assert action_is_valid({"name": "EVAL", "args": {}, "x": 1}) is False

    # Bad args
    assert action_is_valid({"name": "EVAL", "args": {"k": 1}}) is False
    assert action_is_valid({"name": "EVAL", "args": []}) is False

    # Bad name
    assert action_is_valid({"name": "LEFT", "args": {}}) is False
