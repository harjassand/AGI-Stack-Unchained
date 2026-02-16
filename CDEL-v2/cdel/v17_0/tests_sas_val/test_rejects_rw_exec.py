from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json


def test_rejects_rw_exec(v17_state_dir: Path) -> None:
    sealed = load_canon_json(sorted((v17_state_dir / "candidate" / "exec").glob("sha256_*.sealed_run_receipt_v1.json"))[0])
    assert int(sealed["spawn_count"]) >= 1
    for row in sealed["invocations"]:
        if row.get("exec_backend") == "RUST_NATIVE_AARCH64_MMAP_RX_V1":
            assert row["code_region_prot"] == "RX"
            assert row["rwx_mapping"] is False
