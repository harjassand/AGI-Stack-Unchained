from __future__ import annotations

from pathlib import Path

from cdel.v17_0.runtime.val_runner_sealed_v1 import has_exec_end, run_runner_batch


def test_guard_pages_catch_oob_crash(tmp_path: Path) -> None:
    # add x3, x1, #4, lsl #12 ; strb w0, [x3] ; mov x0,#0 ; ret
    crash_patch = bytes.fromhex("e30301aa6310409160000039000080d2c0035fd6")
    runner = Path("CDEL-v2/cdel/v17_0/rust/val_runner_rs_v1/target/release/val_runner_rs_v1")
    if not runner.exists():
        import subprocess

        subprocess.run(
            ["cargo", "build", "--release", "--manifest-path", "CDEL-v2/cdel/v17_0/rust/val_runner_rs_v1/Cargo.toml"],
            check=True,
        )

    trace_path = tmp_path / "trace.jsonl"
    receipt_path = tmp_path / "receipt.json"
    result = run_runner_batch(
        runner_bin=runner,
        mode="patch_native",
        messages=[b"a" * 16],
        patch_bytes=crash_patch,
        trace_path=trace_path,
        receipt_path=receipt_path,
        max_len_bytes=4096,
        step_bytes=1,
        safety_status="SAFE",
        runner_bin_hash="sha256:" + "0" * 64,
        code_bytes_hash="sha256:" + "1" * 64,
    )
    assert int(result["returncode"]) != 0
    assert has_exec_end(trace_path) is False
