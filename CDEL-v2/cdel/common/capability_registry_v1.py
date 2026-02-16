"""Capability registry loader (v1)."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, load_canon_json

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message="jsonschema.RefResolver is deprecated.*",
)

try:
    from jsonschema import Draft202012Validator
    from jsonschema import RefResolver
except Exception:  # pragma: no cover
    Draft202012Validator = None
    RefResolver = None


class CapabilityRegistryError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise CapabilityRegistryError(reason)


def _schema_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "Genesis" / "schema" / "v14_0"


def _validate_jsonschema(obj: dict[str, Any], schema_name: str, schema_dir: Path) -> None:
    if Draft202012Validator is None:
        return
    schema_path = schema_dir / f"{schema_name}.jsonschema"
    if not schema_path.exists():
        _fail("INVALID:SCHEMA_FAIL")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema = dict(schema)
    schema["$id"] = schema_path.resolve().as_uri()
    store: dict[str, Any] = {}
    for path in schema_dir.glob("*.jsonschema"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            schema_id = payload.get("$id")
            if isinstance(schema_id, str):
                store[schema_id] = payload
                if not schema_id.endswith(".jsonschema"):
                    store[f"{schema_id}.jsonschema"] = payload
            store[path.name] = payload
            store[path.resolve().as_uri()] = payload
    if RefResolver is not None:
        resolver = RefResolver.from_schema(schema, store=store)
        Draft202012Validator(schema, resolver=resolver).validate(obj)
    else:
        Draft202012Validator(schema).validate(obj)


def load_registry(path: Path) -> dict[str, Any]:
    try:
        registry = load_canon_json(path)
    except CanonError:
        _fail("INVALID:SCHEMA_FAIL")
    if not isinstance(registry, dict) or registry.get("schema") != "capability_registry_v1":
        _fail("INVALID:SCHEMA_FAIL")
    _validate_jsonschema(registry, "capability_registry_v1", _schema_dir())
    return registry


def resolve_capability(registry: dict[str, Any], capability_id: str) -> dict[str, Any]:
    caps = registry.get("capabilities")
    if not isinstance(caps, list):
        _fail("INVALID:SCHEMA_FAIL")
    for entry in caps:
        if isinstance(entry, dict) and entry.get("capability_id") == capability_id:
            return entry
    _fail("INVALID:CAPABILITY_NOT_FOUND")
    return {}


__all__ = ["load_registry", "resolve_capability", "CapabilityRegistryError"]
