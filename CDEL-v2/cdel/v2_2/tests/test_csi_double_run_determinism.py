from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v2_2.verify_rsi_demon_v8 import verify as verify_attempt


def test_csi_double_run_determinism(csi_run_dir: Path, tmp_path: Path) -> None:
    run_copy = tmp_path / "run_copy"
    shutil.copytree(csi_run_dir, run_copy)

    attempt_dir = run_copy / "attempts" / "attempt_0001"
    candidate_tree = attempt_dir / "candidate_tree"

    bench_api = candidate_tree / "Extension-1" / "agi-orchestrator" / "orchestrator" / "csi" / "bench_api_v1.py"
    text = bench_api.read_text(encoding="utf-8")
    if "import random" not in text:
        if "from typing import Any, Callable\n" in text:
            text = text.replace("from typing import Any, Callable\n", "from typing import Any, Callable\nimport random\n", 1)
        else:
            text = "import random\n" + text
    if "marker" not in text:
        text = text.replace(
            "    return outputs\n",
            "    for case_id in outputs:\n        outputs[case_id][\"marker\"] = random.randint(0, 1000000)\n\n    return outputs\n",
        )
    bench_api.write_text(text, encoding="utf-8")

    with pytest.raises(CanonError) as excinfo:
        verify_attempt(attempt_dir)
    assert "NONDETERMINISM" in str(excinfo.value)
