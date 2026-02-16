"""Common deterministic helpers for continuity/core verification in v19.0."""

from __future__ import annotations

import copy
import dataclasses
import json
import os
import re
from pathlib import Path
from typing import Any

from ...v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed, write_canon_json

try:
    from jsonschema import Draft202012Validator
    from jsonschema import RefResolver
except Exception:  # pragma: no cover
    Draft202012Validator = None
    RefResolver = None


SCHEMA_STORE_CACHE: dict[str, dict[str, Any]] = {}
VALIDATOR_CACHE: dict[tuple[str, str], Any] = {}
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ContinuityV19Error(CanonError):
    """Fail-closed runtime error for continuity checks."""


def fail(reason: str, *, safe_halt: bool = False) -> None:
    token = str(reason or "UNKNOWN").strip() or "UNKNOWN"
    if token.startswith("SAFE_HALT:") or token.startswith("REJECT:") or token.startswith("INVALID:"):
        raise ContinuityV19Error(token)
    if safe_halt:
        raise ContinuityV19Error(f"SAFE_HALT:{token}")
    raise ContinuityV19Error(f"INVALID:{token}")


def repo_root() -> Path:
    override = str(os.environ.get("OMEGA_REPO_ROOT", "")).strip()
    if override:
        path = Path(override).resolve()
        if not path.exists() or not path.is_dir():
            fail("MISSING_STATE_INPUT", safe_halt=True)
        return path
    return Path(__file__).resolve().parents[4]


def schema_dir() -> Path:
    return repo_root() / "Genesis" / "schema" / "v19_0"


def canon_hash_obj(obj: Any) -> str:
    return sha256_prefixed(canon_bytes(obj))


def ensure_sha256(value: Any, *, reason: str = "SCHEMA_ERROR") -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        fail(reason, safe_halt=True)
    return value


def require_relpath(path_value: Any, *, reason: str = "SCHEMA_ERROR") -> str:
    if not isinstance(path_value, str) or not path_value:
        fail(reason, safe_halt=True)
    p = Path(path_value)
    if p.is_absolute() or ".." in p.parts or "\\" in path_value:
        fail(reason, safe_halt=True)
    return path_value


def load_canon_dict(path: Path, *, reason: str = "SCHEMA_ERROR") -> dict[str, Any]:
    try:
        obj = load_canon_json(path)
    except Exception:
        fail(reason, safe_halt=True)
    if not isinstance(obj, dict):
        fail(reason, safe_halt=True)
    return obj


def validate_schema(obj: dict[str, Any], schema_name: str) -> None:
    if Draft202012Validator is None:
        return
    schema_root = schema_dir().resolve()
    schema_root_key = str(schema_root)
    schema_path = schema_root / f"{schema_name}.jsonschema"
    if not schema_path.exists() or not schema_path.is_file():
        fail("SCHEMA_ERROR", safe_halt=True)

    store = SCHEMA_STORE_CACHE.get(schema_root_key)
    if store is None:
        store = {}
        for path in sorted(schema_root.glob("*.json*"), key=lambda row: row.as_posix()):
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            schema_id = payload.get("$id")
            if isinstance(schema_id, str):
                store[schema_id] = payload
                if not schema_id.endswith(".jsonschema"):
                    store[f"{schema_id}.jsonschema"] = payload
            store[path.name] = payload
            store[path.resolve().as_uri()] = payload
        SCHEMA_STORE_CACHE[schema_root_key] = store

    validator_key = (schema_root_key, schema_name)
    validator = VALIDATOR_CACHE.get(validator_key)
    if validator is None:
        schema_uri = schema_path.resolve().as_uri()
        schema_payload = store.get(schema_uri)
        if not isinstance(schema_payload, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        schema = dict(schema_payload)
        schema["$id"] = schema_uri
        if RefResolver is not None:
            resolver = RefResolver.from_schema(schema, store=store)
            validator = Draft202012Validator(schema, resolver=resolver)
        else:
            validator = Draft202012Validator(schema)
        VALIDATOR_CACHE[validator_key] = validator

    try:
        validator.validate(obj)
    except Exception:
        fail("SCHEMA_ERROR", safe_halt=True)


def verify_declared_id(obj: dict[str, Any], id_field: str) -> str:
    declared = ensure_sha256(obj.get(id_field), reason="ID_MISMATCH")
    no_id = dict(obj)
    if id_field in no_id:
        del no_id[id_field]
    computed = canon_hash_obj(no_id)
    if computed != declared:
        fail("ID_MISMATCH", safe_halt=True)
    return declared


def validate_budget_spec(budget: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(budget, dict):
        fail("MISSING_BUDGET", safe_halt=True)
    validate_schema(budget, "budget_spec_v1")
    return budget


@dataclasses.dataclass
class BudgetTracker:
    """Typed deterministic budget tracker used by all v19 continuity checks."""

    spec: dict[str, Any]
    steps_used: int = 0
    items_used: int = 0
    bytes_read: int = 0
    bytes_write: int = 0

    @property
    def policy(self) -> str:
        return str(self.spec.get("policy", "SAFE_HALT"))

    def _exhaust(self, reason: str) -> None:
        if self.policy == "HARD_FAIL":
            fail(reason, safe_halt=False)
        if self.policy == "SAFE_SPLIT":
            fail("SAFE_SPLIT:BUDGET_EXHAUSTED", safe_halt=False)
        fail(reason, safe_halt=True)

    def consume_steps(self, count: int = 1) -> None:
        self.steps_used += max(0, int(count))
        if self.steps_used > int(self.spec.get("max_steps", 0)):
            self._exhaust("BUDGET_EXHAUSTED")

    def consume_items(self, count: int = 1) -> None:
        self.items_used += max(0, int(count))
        if self.items_used > int(self.spec.get("max_items", 0)):
            self._exhaust("BUDGET_EXHAUSTED")

    def consume_bytes_read(self, count: int) -> None:
        self.bytes_read += max(0, int(count))
        if self.bytes_read > int(self.spec.get("max_bytes_read", 0)):
            self._exhaust("BUDGET_EXHAUSTED")

    def consume_bytes_write(self, count: int) -> None:
        self.bytes_write += max(0, int(count))
        if self.bytes_write > int(self.spec.get("max_bytes_write", 0)):
            self._exhaust("BUDGET_EXHAUSTED")


def make_budget_tracker(budget: dict[str, Any]) -> BudgetTracker:
    return BudgetTracker(spec=validate_budget_spec(budget))


def sorted_by_canon(items: list[Any]) -> list[Any]:
    pairs = [(canon_bytes(item), item) for item in items]
    pairs.sort(key=lambda row: row[0])
    return [row[1] for row in pairs]


def deep_clone(value: Any) -> Any:
    return copy.deepcopy(value)


def canonical_json_size(value: Any) -> int:
    return len(canon_bytes(value))


def write_canonical(path: Path, payload: dict[str, Any]) -> None:
    write_canon_json(path, payload)


__all__ = [
    "BudgetTracker",
    "ContinuityV19Error",
    "canon_hash_obj",
    "canonical_json_size",
    "deep_clone",
    "ensure_sha256",
    "fail",
    "load_canon_dict",
    "make_budget_tracker",
    "repo_root",
    "require_relpath",
    "schema_dir",
    "sorted_by_canon",
    "validate_budget_spec",
    "validate_schema",
    "verify_declared_id",
    "write_canonical",
]
