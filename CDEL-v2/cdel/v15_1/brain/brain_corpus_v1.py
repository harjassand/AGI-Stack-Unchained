from __future__ import annotations

from pathlib import Path
from typing import Any

from ...v1_7r.canon import load_canon_json


class BrainCorpusError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise BrainCorpusError(reason)


def load_suitepack(path: Path) -> dict[str, Any]:
    obj = load_canon_json(path)
    if not isinstance(obj, dict):
        _fail("INVALID:BRAIN_SUITEPACK")
    if set(obj.keys()) != {"schema_version", "cases"}:
        _fail("INVALID:BRAIN_SUITEPACK")
    if obj.get("schema_version") != "brain_corpus_suitepack_v1":
        _fail("INVALID:BRAIN_SUITEPACK")
    cases = obj.get("cases")
    if not isinstance(cases, list) or not cases:
        _fail("INVALID:BRAIN_SUITEPACK")
    for row in cases:
        if not isinstance(row, dict):
            _fail("INVALID:BRAIN_SUITEPACK")
        if set(row.keys()) != {"case_id", "context_rel", "decision_ref_rel"}:
            _fail("INVALID:BRAIN_SUITEPACK")
        for key in ["case_id", "context_rel", "decision_ref_rel"]:
            if not isinstance(row.get(key), str) or not row[key]:
                _fail("INVALID:BRAIN_SUITEPACK")
    return obj


__all__ = ["BrainCorpusError", "load_suitepack"]
