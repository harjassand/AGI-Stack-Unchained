from __future__ import annotations

import pytest

from orchestrator.validation import Limits, validate_candidate


def test_validation_rejects_oversize_candidate() -> None:
    payload = {
        "new_symbols": ["f"],
        "definitions": [
            {
                "name": "f",
                "params": [{"name": "n", "type": {"tag": "int"}}],
                "ret_type": {"tag": "int"},
                "body": {
                    "tag": "prim",
                    "op": "add_int",
                    "args": [
                        {"tag": "int", "value": 1},
                        {"tag": "int", "value": 2},
                    ],
                },
                "termination": {"kind": "structural", "decreases_param": None},
            }
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [{"concept": "algo.add", "symbol": "f"}],
    }

    limits = Limits(max_new_symbols=1, max_ast_nodes=1, max_ast_depth=10)
    with pytest.raises(ValueError, match="max_ast_nodes"):
        validate_candidate(payload, limits=limits)
