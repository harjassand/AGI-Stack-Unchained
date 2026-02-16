"""Runtime dispatch for SAS-System v14.0 workmeter backend."""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from ...v1_7r.canon import CanonError, canon_bytes, load_canon_json, loads
from ...v13_0 import sas_science_workmeter_v1 as ref_workmeter


class SASSystemDispatchError(CanonError):
    pass


_MODULE_CACHE: dict[str, Any] = {}


def _fail(reason: str) -> None:
    raise SASSystemDispatchError(reason)


def _load_registry(path: Path) -> dict[str, Any]:
    registry = load_canon_json(path)
    if not isinstance(registry, dict) or registry.get("schema") != "sas_system_component_registry_v1":
        _fail("INVALID:REGISTRY_SCHEMA_FAIL")
    return registry


def dispatch_compute(job: dict[str, Any], registry_path: Path) -> dict[str, Any]:
    registry = _load_registry(registry_path)
    comp = registry.get("components", {}).get("SAS_SCIENCE_WORKMETER_V1")
    if not isinstance(comp, dict):
        _fail("INVALID:REGISTRY_UNKNOWN_COMPONENT")
    backend = comp.get("active_backend")
    if backend == "PY_REF_V1":
        return ref_workmeter.compute_workmeter_v1(job)
    if backend == "RUST_EXT_V1":
        rust_ext = comp.get("rust_ext")
        if not isinstance(rust_ext, dict) or not isinstance(rust_ext.get("module"), str):
            _fail("INVALID:RUST_BACKEND_LOAD_FAIL")
        module_name = rust_ext["module"]
        if os.path.sep in module_name or module_name.endswith(".so") or module_name.endswith(".dylib"):
            module_path = Path(module_name)
            if not module_path.exists():
                _fail("INVALID:RUST_BACKEND_LOAD_FAIL")
            key = f"file:{module_path.resolve()}"
            if key in _MODULE_CACHE:
                mod = _MODULE_CACHE[key]
            else:
                spec = importlib.util.spec_from_file_location("cdel_workmeter_rs_v1", module_path)
                if spec is None or spec.loader is None:
                    _fail("INVALID:RUST_BACKEND_LOAD_FAIL")
                mod = importlib.util.module_from_spec(spec)
                sys.modules["cdel_workmeter_rs_v1"] = mod
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
        out_bytes = compute(canon_bytes(job))
        if isinstance(out_bytes, str):
            out_bytes = out_bytes.encode("utf-8")
        if not isinstance(out_bytes, (bytes, bytearray)):
            _fail("INVALID:RUST_BACKEND_LOAD_FAIL")
        return loads(bytes(out_bytes))
    _fail("INVALID:RUST_BACKEND_LOAD_FAIL")
    return {}


__all__ = ["dispatch_compute", "SASSystemDispatchError"]
