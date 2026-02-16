from __future__ import annotations

from cdel.v17_0.runtime.val_patch_store_v1 import decode_code_bytes
from cdel.v17_0.tests_sas_val.utils import load_template_patch_manifest
from cdel.v17_0.val.val_decode_aarch64_v1 import decode_trace_py
from cdel.v17_0.val.val_lift_ir_v1 import lift_ir_hash, lift_ir_py, lift_ir_rs


def test_val_dual_lifter_parity() -> None:
    manifest = load_template_patch_manifest()
    decoded = decode_trace_py(decode_code_bytes(manifest))
    assert lift_ir_hash(lift_ir_py(decoded)) == lift_ir_hash(lift_ir_rs(decoded))
