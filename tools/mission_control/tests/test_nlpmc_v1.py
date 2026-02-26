"""Tests for NLPMC mission compiler parsing helpers."""

from __future__ import annotations

import pytest

from tools.mission_control import nlpmc_v1


def test_strict_json_object_accepts_markdown_fenced_json() -> None:
    raw = """```json
{
  "schema_name": "mission_request_v1",
  "schema_version": "v19_0"
}
```"""

    parsed = nlpmc_v1._strict_json_object(raw)
    assert parsed["schema_name"] == "mission_request_v1"
    assert parsed["schema_version"] == "v19_0"


def test_strict_json_object_accepts_embedded_json_with_wrapper_text() -> None:
    raw = """model_output:

```json
{
  "schema_name": "mission_request_v1",
  "schema_version": "v19_0",
  "notes": "hello"
}
```
"""

    parsed = nlpmc_v1._strict_json_object(raw)
    assert parsed["notes"] == "hello"


def test_strict_json_object_rejects_non_json_text() -> None:
    with pytest.raises(RuntimeError, match="NLPMC_JSON_PARSE_FAILED"):
        nlpmc_v1._strict_json_object("no json object present")
