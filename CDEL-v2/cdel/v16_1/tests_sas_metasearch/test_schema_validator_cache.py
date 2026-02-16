from __future__ import annotations

import json
from pathlib import Path

import pytest

from cdel.v16_1 import verify_rsi_sas_metasearch_v16_1 as verifier


def test_schema_validator_cache_reuses_schema_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if verifier.Draft202012Validator is None:
        pytest.skip("jsonschema unavailable")

    verifier.SCHEMA_STORE_CACHE.clear()
    verifier.VALIDATOR_CACHE.clear()

    schema_dir = tmp_path / "schema"
    schema_dir.mkdir(parents=True, exist_ok=True)
    (schema_dir / "cache_probe.jsonschema").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "local://cache_probe",
                "type": "object",
                "required": ["value"],
                "properties": {"value": {"type": "integer"}},
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )

    call_count = {"glob": 0}
    original_glob = Path.glob
    schema_dir_abs = schema_dir.resolve()

    def _counting_glob(self: Path, pattern: str):
        if self.resolve() == schema_dir_abs and pattern == "*.jsonschema":
            call_count["glob"] += 1
        return original_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", _counting_glob)

    verifier._validate_jsonschema({"value": 1}, "cache_probe", schema_dir)
    verifier._validate_jsonschema({"value": 2}, "cache_probe", schema_dir)

    assert call_count["glob"] == 1
