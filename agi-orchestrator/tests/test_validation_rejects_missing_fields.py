from __future__ import annotations

import pytest

from orchestrator.validation import Limits, validate_candidate


def test_validation_rejects_missing_fields() -> None:
    payload = {"new_symbols": ["x"]}
    with pytest.raises(ValueError, match="candidate missing required list"):
        validate_candidate(payload, limits=Limits(max_new_symbols=1, max_ast_nodes=10, max_ast_depth=5))
