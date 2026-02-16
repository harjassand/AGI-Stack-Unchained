from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
# Ensure the submodule `CDEL-v2` wins over any accidental `cdel/` namespace
# package in the repo root (untracked overlays can silently shadow RE2 code).
_ordered_paths = [str(REPO_ROOT / "CDEL-v2"), str(REPO_ROOT)]
for _path_str in _ordered_paths:
    while _path_str in sys.path:
        sys.path.remove(_path_str)
for _path_str in reversed(_ordered_paths):
    sys.path.insert(0, _path_str)

_pinned_pythonpath = ":".join(_ordered_paths)
_existing_pythonpath = str(os.environ.get("PYTHONPATH", "")).strip()
if _existing_pythonpath:
    os.environ["PYTHONPATH"] = f"{_pinned_pythonpath}:{_existing_pythonpath}"
else:
    os.environ["PYTHONPATH"] = _pinned_pythonpath

_orchestrator = sys.modules.get("orchestrator")
if _orchestrator is not None:
    _module_file = Path(str(getattr(_orchestrator, "__file__", ""))).resolve()
    _expected_root = (REPO_ROOT / "orchestrator").resolve()
    if not str(_module_file).startswith(str(_expected_root)):
        for _name in [row for row in list(sys.modules.keys()) if row == "orchestrator" or row.startswith("orchestrator.")]:
            sys.modules.pop(_name, None)

_orchestrator_package_dir = (REPO_ROOT / "orchestrator").resolve()
_orchestrator_init = _orchestrator_package_dir / "__init__.py"
_orchestrator_spec = importlib.util.spec_from_file_location(
    "orchestrator",
    _orchestrator_init,
    submodule_search_locations=[str(_orchestrator_package_dir)],
)
if _orchestrator_spec is not None and _orchestrator_spec.loader is not None:
    _orchestrator_module = importlib.util.module_from_spec(_orchestrator_spec)
    sys.modules["orchestrator"] = _orchestrator_module
    _orchestrator_spec.loader.exec_module(_orchestrator_module)


def _xdist_available() -> bool:
    return importlib.util.find_spec("xdist") is not None


def _has_numprocess_flag(args: list[str]) -> bool:
    for value in args:
        if value == "-n" or value.startswith("-n="):
            return True
        if value.startswith("--numprocesses"):
            return True
    return False


def pytest_cmdline_preparse(config, args) -> None:  # type: ignore[no-untyped-def]
    if not _xdist_available() or _has_numprocess_flag(args):
        return
    args[:0] = ["-n", "auto"]
