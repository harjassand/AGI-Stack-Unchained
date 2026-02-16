"""Shared fail-closed helpers for v19.0 continuity/world/federation checks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed

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


SCHEMA_STORE_CACHE: dict[str, dict[str, Any]] = {}
VALIDATOR_CACHE: dict[tuple[str, str], Any] = {}

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ALLOWED_OUTCOMES = {"ACCEPT", "REJECT", "SAFE_HALT", "SAFE_SPLIT"}

_REPO_ROOT_OVERRIDE_ENV = "OMEGA_REPO_ROOT"


class OmegaV19Error(CanonError):
    """Fail-closed error for trusted v19.0 checks."""


class BudgetExhausted(RuntimeError):
    """Raised when deterministic budgets are exhausted."""

    def __init__(self, policy: str):
        self.policy = policy
        super().__init__(f"BUDGET_EXHAUSTED:{policy}")


def fail(reason: str) -> None:
    raise OmegaV19Error(reason)


def repo_root() -> Path:
    override = str(os.environ.get(_REPO_ROOT_OVERRIDE_ENV, "")).strip()
    if override:
        root = Path(override).resolve()
        if not root.exists() or not root.is_dir():
            fail("MISSING_INPUT")
        return root
    return Path(__file__).resolve().parents[3]


def schema_dir() -> Path:
    return repo_root() / "Genesis" / "schema" / "v19_0"


def canon_hash_obj(obj: Any) -> str:
    return sha256_prefixed(canon_bytes(obj))


def hash_bytes(data: bytes) -> str:
    return sha256_prefixed(data)


def load_canon_dict(path: Path, *, reason: str = "SCHEMA_FAIL") -> dict[str, Any]:
    try:
        payload = load_canon_json(path)
    except CanonError:
        fail(reason)
    if not isinstance(payload, dict):
        fail(reason)
    return payload


def load_json_dict(path: Path, *, reason: str = "SCHEMA_FAIL") -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        fail(reason)
    if not isinstance(payload, dict):
        fail(reason)
    return payload


def ensure_sha256(value: Any, *, reason: str = "SCHEMA_FAIL") -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        fail(reason)
    return value


def validate_schema(obj: dict[str, Any], schema_name: str) -> None:
    if Draft202012Validator is None:
        return
    schema_root = schema_dir().resolve()
    schema_root_key = str(schema_root)
    schema_path = schema_root / f"{schema_name}.jsonschema"
    if not schema_path.exists():
        alt = schema_root / f"{schema_name}.jsonl.schema"
        if alt.exists():
            schema_path = alt
        else:
            fail("SCHEMA_FAIL")

    store = SCHEMA_STORE_CACHE.get(schema_root_key)
    if store is None:
        store = {}
        for path in sorted(schema_root.glob("*.json*"), key=lambda p: p.name):
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
                if not schema_id.endswith(".jsonl.schema"):
                    store[f"{schema_id}.jsonl.schema"] = payload
            store[path.name] = payload
            store[path.resolve().as_uri()] = payload
        SCHEMA_STORE_CACHE[schema_root_key] = store

    validator_key = (schema_root_key, schema_name)
    validator = VALIDATOR_CACHE.get(validator_key)
    if validator is None:
        schema_uri = schema_path.resolve().as_uri()
        schema_payload = store.get(schema_uri)
        if not isinstance(schema_payload, dict):
            fail("SCHEMA_FAIL")
        schema = dict(schema_payload)
        schema["$id"] = schema_uri
        if RefResolver is not None:
            resolver = RefResolver.from_schema(schema, store=store)
            validator = Draft202012Validator(schema, resolver=resolver)
        else:
            validator = Draft202012Validator(schema)
        VALIDATOR_CACHE[validator_key] = validator

    validator.validate(obj)


def verify_object_id(obj: dict[str, Any], *, id_field: str, reason: str = "ID_MISMATCH") -> str:
    expected = ensure_sha256(obj.get(id_field), reason=reason)
    no_id = dict(obj)
    no_id.pop(id_field, None)
    observed = canon_hash_obj(no_id)
    if observed != expected:
        fail(reason)
    return expected


def new_object_with_id(obj: dict[str, Any], *, id_field: str) -> dict[str, Any]:
    out = dict(obj)
    out.pop(id_field, None)
    out[id_field] = canon_hash_obj(out)
    return out


def module_hash(module_relpath: str) -> str:
    if not module_relpath or module_relpath.startswith("/") or ".." in Path(module_relpath).parts:
        fail("SCHEMA_FAIL")
    path = repo_root() / module_relpath
    if not path.exists() or not path.is_file():
        fail("MISSING_INPUT")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def normalize_outcome(outcome: str) -> str:
    value = str(outcome).strip()
    if value not in _ALLOWED_OUTCOMES:
        fail("SCHEMA_FAIL")
    return value


def budget_outcome(policy: str, *, allow_safe_split: bool) -> str:
    if policy == "HARD_FAIL":
        return "REJECT"
    if policy == "SAFE_HALT":
        return "SAFE_HALT"
    if policy == "SAFE_SPLIT":
        return "SAFE_SPLIT" if allow_safe_split else "SAFE_HALT"
    fail("SCHEMA_FAIL")
    return "SAFE_HALT"


def require_budget_spec(spec: Any) -> dict[str, Any]:
    if not isinstance(spec, dict):
        fail("SAFE_HALT:BUDGET_MISSING")
    validate_schema(spec, "budget_spec_v1")
    if spec.get("schema_name") != "budget_spec_v1" or spec.get("schema_version") != "v19_0":
        fail("SCHEMA_FAIL")
    return dict(spec)


@dataclass
class BudgetMeter:
    """Deterministic budget counter used by all Team-2 checkers."""

    spec: dict[str, Any]
    steps_used: int = 0
    bytes_read_used: int = 0
    bytes_write_used: int = 0
    items_used: int = 0

    def __post_init__(self) -> None:
        self.spec = require_budget_spec(self.spec)

    @property
    def policy(self) -> str:
        return str(self.spec["policy"])

    def _check(self) -> None:
        if self.steps_used > int(self.spec["max_steps"]):
            raise BudgetExhausted(self.policy)
        if self.bytes_read_used > int(self.spec["max_bytes_read"]):
            raise BudgetExhausted(self.policy)
        if self.bytes_write_used > int(self.spec["max_bytes_write"]):
            raise BudgetExhausted(self.policy)
        if self.items_used > int(self.spec["max_items"]):
            raise BudgetExhausted(self.policy)

    def consume(
        self,
        *,
        steps: int = 0,
        bytes_read: int = 0,
        bytes_write: int = 0,
        items: int = 0,
    ) -> None:
        self.steps_used += max(0, int(steps))
        self.bytes_read_used += max(0, int(bytes_read))
        self.bytes_write_used += max(0, int(bytes_write))
        self.items_used += max(0, int(items))
        self._check()


__all__ = [
    "BudgetExhausted",
    "BudgetMeter",
    "OmegaV19Error",
    "budget_outcome",
    "canon_hash_obj",
    "ensure_sha256",
    "fail",
    "hash_bytes",
    "load_canon_dict",
    "load_json_dict",
    "module_hash",
    "new_object_with_id",
    "normalize_outcome",
    "repo_root",
    "require_budget_spec",
    "schema_dir",
    "validate_schema",
    "verify_object_id",
]
