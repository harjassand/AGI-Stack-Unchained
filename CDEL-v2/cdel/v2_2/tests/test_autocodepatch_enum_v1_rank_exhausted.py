from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v2_2.autocodepatch import autocodepatch_enum_v1


def test_autocodepatch_enum_v1_rank_exhausted(tmp_path) -> None:
    with pytest.raises(CanonError) as excinfo:
        autocodepatch_enum_v1(tmp_path, 1, {"concept_eval_output_int": 1}, tmp_path)
    assert "CSI_ENUM_EXHAUSTED" in str(excinfo.value)
