from __future__ import annotations

from cdel.v17_0.runtime.val_patch_store_v1 import decode_code_bytes
from cdel.v17_0.tests_sas_val.utils import load_template_patch_manifest
from cdel.v17_0.val.val_decode_aarch64_v1 import decode_trace_py, decode_trace_rs, decoded_trace_hash


def test_val_dual_decoder_parity() -> None:
    manifest = load_template_patch_manifest()
    code = decode_code_bytes(manifest)
    py_hash = decoded_trace_hash(decode_trace_py(code))
    rs_hash = decoded_trace_hash(decode_trace_rs(code))
    assert py_hash == rs_hash
