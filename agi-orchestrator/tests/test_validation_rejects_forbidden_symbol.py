from __future__ import annotations

import pytest

from orchestrator.validation import Limits, validate_candidate


def test_validation_rejects_forbidden_symbol() -> None:
    payload = {
        "new_symbols": ["f"],
        "definitions": [
            {
                "name": "f",
                "params": [{"name": "n", "type": {"tag": "int"}}],
                "ret_type": {"tag": "int"},
                "body": {"tag": "sym", "name": "forbidden_sym"},
                "termination": {"kind": "structural", "decreases_param": None},
            }
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [{"concept": "algo.sym", "symbol": "f"}],
    }

    limits = Limits(max_new_symbols=1, max_ast_nodes=10, max_ast_depth=10)
    with pytest.raises(ValueError, match="forbidden symbols"):
        validate_candidate(payload, limits=limits, allowlist={"allowed_sym"})
