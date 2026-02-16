from __future__ import annotations

import unicodedata

import pytest

from cdel.sealed.canon import canon_bytes
from cdel.sealed.crypto import generate_keypair, sign_bytes


def test_canon_unicode_normalization_differs() -> None:
    nfc = unicodedata.normalize("NFC", "e\u0301")
    nfd = unicodedata.normalize("NFD", "\u00e9")
    assert nfc != nfd

    payload_nfc = {"value": nfc}
    payload_nfd = {"value": nfd}
    bytes_nfc = canon_bytes(payload_nfc)
    bytes_nfd = canon_bytes(payload_nfd)
    assert bytes_nfc != bytes_nfd

    priv_key, _ = generate_keypair()
    sig_nfc = sign_bytes(priv_key, bytes_nfc)
    sig_nfd = sign_bytes(priv_key, bytes_nfd)
    assert sig_nfc != sig_nfd


def test_canon_rejects_non_finite_numbers() -> None:
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            canon_bytes({"value": value})


def test_canon_large_int_and_negative_zero() -> None:
    payload = {"big": 10**30, "zero": -0}
    data = canon_bytes(payload).decode("utf-8")
    assert '"big":1000000000000000000000000000000' in data
    assert '"zero":0' in data


def test_canon_decimal_strings_preserved() -> None:
    payload_a = {"value": "1.2300"}
    payload_b = {"value": "1.23"}
    assert canon_bytes(payload_a) != canon_bytes(payload_b)
