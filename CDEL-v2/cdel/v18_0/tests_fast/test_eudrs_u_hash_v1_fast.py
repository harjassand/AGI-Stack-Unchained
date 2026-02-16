from __future__ import annotations

import pytest

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import (
    artifact_id_from_json_bytes,
    gcj1_canon_bytes,
    gcj1_loads_and_verify_canonical,
)
from cdel.v18_0.omega_common_v1 import OmegaV18Error


def test_gcj1_canon_bytes_and_hash_vector() -> None:
    obj = {"b": 1, "a": 2}
    raw = gcj1_canon_bytes(obj)
    assert raw == b'{"a":2,"b":1}\n'
    digest = artifact_id_from_json_bytes(raw)
    assert digest == "sha256:81103aa69250ea56e887eaab3cd9bf363d341563f05d0676be389c3e40a72871"


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1.0}\\n',
        b'{"a":1e3}\\n',
        b'{"a":-0.5}\\n',
    ],
)
def test_gcj1_loader_rejects_floats(raw: bytes) -> None:
    with pytest.raises(OmegaV18Error):
        gcj1_loads_and_verify_canonical(raw)


def test_gcj1_verify_canonical_requires_exact_bytes() -> None:
    # Missing newline is forbidden.
    with pytest.raises(OmegaV18Error):
        gcj1_loads_and_verify_canonical(b'{"a":2,"b":1}')

    # Whitespace / pretty-printing is forbidden.
    with pytest.raises(OmegaV18Error):
        gcj1_loads_and_verify_canonical(b'{\"a\":2, \"b\":1}\\n')
