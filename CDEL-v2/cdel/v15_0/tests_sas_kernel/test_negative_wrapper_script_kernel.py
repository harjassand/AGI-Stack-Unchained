from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v15_0.kernel_pinning_v1 import KernelPinningError, ensure_native_kernel_binary


def test_negative_wrapper_script_kernel(tmp_path: Path) -> None:
    script = tmp_path / "agi_kernel_v15"
    script.write_text("#!/bin/sh\necho wrapped\n", encoding="utf-8")
    with pytest.raises(KernelPinningError):
        ensure_native_kernel_binary(script)
