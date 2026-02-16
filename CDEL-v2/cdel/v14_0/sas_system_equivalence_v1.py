"""Equivalence checks for SAS-System v14.0."""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, loads
from ..v13_0 import sas_science_workmeter_v1 as ref_workmeter


class SASSystemEquivalenceError(CanonError):
    pass


_MODULE_CACHE: dict[str, Any] = {}


def _fail(reason: str) -> None:
    raise SASSystemEquivalenceError(reason)


def _canon_bytes(payload: Any) -> bytes:
    return canon_bytes(payload)


def _canon_load(raw: bytes) -> Any:
    return loads(raw)


def _rust_compute(module_name: str, job_bytes: bytes) -> bytes:
    mod = None
    if os.path.sep in module_name or module_name.endswith(".so") or module_name.endswith(".dylib"):
        module_path = Path(module_name)
        if not module_path.exists():
            _fail("INVALID:RUST_BACKEND_LOAD_FAIL")
        key = f"file:{module_path.resolve()}"
        if key in _MODULE_CACHE:
            mod = _MODULE_CACHE[key]
        else:
            py_mod_name = "cdel_workmeter_rs_v1"
            spec = importlib.util.spec_from_file_location(py_mod_name, module_path)
            if spec is None or spec.loader is None:
                _fail("INVALID:RUST_BACKEND_LOAD_FAIL")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[py_mod_name] = mod
            spec.loader.exec_module(mod)
            _MODULE_CACHE[key] = mod
    else:
        if module_name in _MODULE_CACHE:
            mod = _MODULE_CACHE[module_name]
        else:
            mod = importlib.import_module(module_name)
            _MODULE_CACHE[module_name] = mod
    compute = getattr(mod, "compute", None)
    if compute is None:
        _fail("INVALID:RUST_BACKEND_LOAD_FAIL")
    out_bytes = compute(job_bytes)
    if isinstance(out_bytes, str):
        out_bytes = out_bytes.encode("utf-8")
    if not isinstance(out_bytes, (bytes, bytearray)):
        _fail("INVALID:RUST_BACKEND_LOAD_FAIL")
    return bytes(out_bytes)


def run_equivalence(
    *,
    suitepack: dict[str, Any],
    rust_module: str,
    fail_fast: bool = True,
) -> list[dict[str, Any]]:
    cases = suitepack.get("cases")
    if not isinstance(cases, list):
        _fail("INVALID:SCHEMA_FAIL")
    results: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            _fail("INVALID:SCHEMA_FAIL")
        case_id = str(case.get("case_id"))
        job = case.get("job")
        if not isinstance(job, dict):
            _fail("INVALID:SCHEMA_FAIL")
        job_bytes = _canon_bytes(job)

        out_py = ref_workmeter.compute_workmeter_v1(job)
        out_py_bytes = _canon_bytes(out_py)

        out_rs_bytes = _rust_compute(rust_module, job_bytes)
        out_rs = _canon_load(out_rs_bytes)
        out_rs_bytes_canon = _canon_bytes(out_rs)

        if out_py_bytes != out_rs_bytes_canon:
            if fail_fast:
                _fail(f"INVALID:OUTPUT_MISMATCH:{case_id}")
            results.append({"case_id": case_id, "pass": False})
        else:
            results.append({"case_id": case_id, "pass": True})
    return results


__all__ = ["run_equivalence", "SASSystemEquivalenceError"]
