"""Persistent observer artifact index for omega daemon v18.0."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .omega_common_v1 import repo_root, require_relpath

_INDEX_SCHEMA_VERSION = "omega_observer_index_v1"
_INDEX_PATH_REL = ".omega_cache/omega_observer_index_v1.json"

_KEY_TO_GLOBS: dict[str, list[str]] = {
    "metasearch_compute_report_v1": [
        "daemon/rsi_sas_metasearch_v16_1/state/reports/*.metasearch_compute_report_v1.json",
    ],
    "kernel_hotloop_report_v1": [
        "daemon/rsi_sas_val_v17_0/state/hotloop/*.kernel_hotloop_report_v1.json",
    ],
    "sas_system_perf_report_v1": [
        "daemon/rsi_sas_system_v14_0/state/artifacts/*.sas_system_perf_report_v1.json",
    ],
    "sas_science_promotion_bundle_v1": [
        "daemon/rsi_sas_science_v13_0/state/promotion/*.sas_science_promotion_bundle_v1.json",
    ],
}

_CAMPAIGN_TO_KEYS: dict[str, tuple[str, ...]] = {
    "rsi_sas_metasearch_v16_1": ("metasearch_compute_report_v1",),
    "rsi_sas_val_v17_0": ("kernel_hotloop_report_v1",),
    "rsi_sas_system_v14_0": ("sas_system_perf_report_v1",),
    "rsi_sas_science_v13_0": ("sas_science_promotion_bundle_v1",),
}


def _index_path(root: Path) -> Path:
    return root / _INDEX_PATH_REL


def _default_index() -> dict[str, Any]:
    return {
        "schema_version": _INDEX_SCHEMA_VERSION,
        "entries": {},
    }


def _normalize_path_rel(value: Any) -> str:
    path_rel = require_relpath(value)
    if not path_rel.startswith("runs/"):
        raise ValueError("path_rel must start with runs/")
    return path_rel


def _sanitize_entry(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    path_rel_raw = value.get("path_rel")
    try:
        path_rel = _normalize_path_rel(path_rel_raw)
    except Exception:
        return None
    return {"path_rel": path_rel}


def _sanitize_index(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _default_index()
    entries_raw = raw.get("entries")
    if not isinstance(entries_raw, dict):
        entries_raw = {}
    entries: dict[str, dict[str, str]] = {}
    for key, value in sorted(entries_raw.items(), key=lambda row: str(row[0])):
        if not isinstance(key, str) or not key:
            continue
        entry = _sanitize_entry(value)
        if entry is None:
            continue
        entries[key] = entry
    return {
        "schema_version": _INDEX_SCHEMA_VERSION,
        "entries": entries,
    }


def load_index(root: Path) -> dict[str, Any]:
    path = _index_path(root)
    if not path.exists() or not path.is_file():
        return _default_index()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_index()
    return _sanitize_index(raw)


def store_index(root: Path, index: dict[str, Any]) -> None:
    payload = _sanitize_index(index)
    path = _index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    text = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def maybe_update_entry(index: dict[str, Any], key: str, candidate_path_rel: str) -> bool:
    if not isinstance(key, str) or not key:
        return False
    candidate = _normalize_path_rel(candidate_path_rel)
    entries = index.get("entries")
    if not isinstance(entries, dict):
        entries = {}
        index["entries"] = entries
    current = entries.get(key)
    current_path = ""
    if isinstance(current, dict):
        try:
            current_path = _normalize_path_rel(current.get("path_rel"))
        except Exception:
            current_path = ""
    if current_path and candidate <= current_path:
        return False
    entries[key] = {"path_rel": candidate}
    return True


def _abs_to_rel(root: Path, abs_path: Path) -> str | None:
    try:
        rel = abs_path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return None
    try:
        return _normalize_path_rel(rel)
    except Exception:
        return None


def update_index_from_subrun_best_effort(*, campaign_id: str, subrun_root_abs: Path) -> None:
    keys = _CAMPAIGN_TO_KEYS.get(str(campaign_id))
    if not keys:
        return
    try:
        root = repo_root()
        index = load_index(root)
        changed = False
        for key in keys:
            rows: list[Path] = []
            for rel_glob in _KEY_TO_GLOBS.get(key, []):
                rows.extend(sorted(subrun_root_abs.glob(rel_glob)))
            if not rows:
                continue
            candidate = rows[-1]
            candidate_rel = _abs_to_rel(root, candidate)
            if candidate_rel is None:
                continue
            if maybe_update_entry(index, key, candidate_rel):
                changed = True
        if changed:
            store_index(root, index)
    except Exception:
        # Optional cache update; never fail tick execution.
        return


__all__ = [
    "load_index",
    "maybe_update_entry",
    "store_index",
    "update_index_from_subrun_best_effort",
]
