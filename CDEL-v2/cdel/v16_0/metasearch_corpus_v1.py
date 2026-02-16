"""Trace corpus helpers for SAS-Metasearch v16.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed, write_canon_json


class MetaSearchCorpusError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise MetaSearchCorpusError(reason)


def build_case_id(*, source_run_rel: str, best_theory_id_dev: str, dev_eval_count: int) -> str:
    payload = {
        "source_run_rel": str(source_run_rel),
        "best_theory_id_dev": str(best_theory_id_dev),
        "dev_eval_count": int(dev_eval_count),
    }
    return sha256_prefixed(canon_bytes(payload))


def _require_sha(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        _fail("INVALID:SCHEMA_FAIL")
    return value


def validate_suitepack(obj: dict[str, Any], *, min_cases: int = 1) -> dict[str, Any]:
    if obj.get("schema_version") != "metasearch_trace_corpus_suitepack_v1":
        _fail("INVALID:SCHEMA_FAIL")
    if not isinstance(obj.get("suite_id"), str) or not obj["suite_id"]:
        _fail("INVALID:SCHEMA_FAIL")

    theory_index = obj.get("theory_index")
    if not isinstance(theory_index, list) or len(theory_index) < 1:
        _fail("INVALID:SCHEMA_FAIL")
    theory_map: dict[str, tuple[str, int]] = {}
    for row in theory_index:
        if not isinstance(row, dict):
            _fail("INVALID:SCHEMA_FAIL")
        if set(row.keys()) != {"theory_id", "theory_kind", "norm_pow_p"}:
            _fail("INVALID:SCHEMA_FAIL")
        theory_id = _require_sha(row.get("theory_id"))
        theory_kind = row.get("theory_kind")
        p = int(row.get("norm_pow_p", 0))
        if theory_kind not in ("CANDIDATE_CENTRAL_POWERLAW_V1", "CANDIDATE_NBODY_POWERLAW_V1"):
            _fail("INVALID:SCHEMA_FAIL")
        if p not in (1, 2, 3, 4):
            _fail("INVALID:SCHEMA_FAIL")
        theory_map[theory_id] = (str(theory_kind), p)

    cases = obj.get("cases")
    if not isinstance(cases, list) or len(cases) < int(min_cases):
        _fail("INVALID:CASECOUNT_LT_MIN")
    for case in cases:
        if not isinstance(case, dict):
            _fail("INVALID:SCHEMA_FAIL")
        required = {
            "case_id",
            "source_run_rel",
            "best_theory_id_dev",
            "best_theory_kind",
            "best_norm_pow_p",
            "dev_evals",
        }
        if set(case.keys()) != required:
            _fail("INVALID:SCHEMA_FAIL")
        _require_sha(case.get("case_id"))
        if not isinstance(case.get("source_run_rel"), str) or not case["source_run_rel"]:
            _fail("INVALID:SCHEMA_FAIL")
        best_theory_id = _require_sha(case.get("best_theory_id_dev"))
        best_kind = case.get("best_theory_kind")
        best_p = int(case.get("best_norm_pow_p", 0))
        if (best_kind, best_p) != theory_map.get(best_theory_id):
            _fail("INVALID:SCHEMA_FAIL")

        dev_evals = case.get("dev_evals")
        if not isinstance(dev_evals, list) or not dev_evals:
            _fail("INVALID:SCHEMA_FAIL")
        for row in dev_evals:
            if not isinstance(row, dict):
                _fail("INVALID:SCHEMA_FAIL")
            if set(row.keys()) != {"theory_id", "rmse_pos1_q32", "work_cost_total"}:
                _fail("INVALID:SCHEMA_FAIL")
            tid = _require_sha(row.get("theory_id"))
            if tid not in theory_map:
                _fail("INVALID:SCHEMA_FAIL")
            q32 = row.get("rmse_pos1_q32")
            if not isinstance(q32, dict) or q32.get("schema_version") != "q32_v1" or q32.get("shift") != 32:
                _fail("INVALID:SCHEMA_FAIL")
            if not isinstance(q32.get("q"), str):
                _fail("INVALID:SCHEMA_FAIL")
            work = row.get("work_cost_total")
            if not isinstance(work, int) or work < 0:
                _fail("INVALID:SCHEMA_FAIL")

    encoded = canon_bytes(obj)
    if b"HELDOUT" in encoded:
        _fail("INVALID:TRACE_LEAK")
    return obj


def load_suitepack(path: Path, *, min_cases: int = 1) -> dict[str, Any]:
    try:
        obj = load_canon_json(path)
    except CanonError:
        _fail("INVALID:SCHEMA_FAIL")
    if not isinstance(obj, dict):
        _fail("INVALID:SCHEMA_FAIL")
    return validate_suitepack(obj, min_cases=min_cases)


def write_suitepack(path: Path, payload: dict[str, Any]) -> None:
    validate_suitepack(payload, min_cases=1)
    write_canon_json(path, payload)


__all__ = [
    "MetaSearchCorpusError",
    "build_case_id",
    "validate_suitepack",
    "load_suitepack",
    "write_suitepack",
]
