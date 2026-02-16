"""Shared helpers for RSI Omega daemon v18.0."""

from __future__ import annotations

import hashlib
import json
import os
import re
import warnings
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed, write_canon_json, write_jsonl_line

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
Q32_ONE = 1 << 32
_DEV_BENCHMARK_MODE_ENV = "OMEGA_DEV_BENCHMARK_MODE"
_REPO_ROOT_OVERRIDE_ENV = "OMEGA_REPO_ROOT"


class OmegaV18Error(CanonError):
    """Error used for fail-closed Omega v18.0 runtime and verifier paths."""


def fail(reason: str) -> None:
    msg = reason
    if not msg.startswith("INVALID:") and not msg.startswith("SAFE_HALT:"):
        msg = f"INVALID:{msg}"
    raise OmegaV18Error(msg)


def repo_root() -> Path:
    override = str(os.environ.get(_REPO_ROOT_OVERRIDE_ENV, "")).strip()
    if override:
        if str(os.environ.get(_DEV_BENCHMARK_MODE_ENV, "0")).strip() != "1":
            fail("FORBIDDEN_REPO_ROOT_OVERRIDE")
        root = Path(override).resolve()
        if not root.exists() or not root.is_dir():
            fail("MISSING_STATE_INPUT")
        return root
    return Path(__file__).resolve().parents[3]


def schema_dir() -> Path:
    # In the full AGI-Stack superproject, Genesis is checked out at repo_root/Genesis.
    # For standalone CDEL-v2 usage (including its own CI), we vendor the needed
    # Genesis schemas under CDEL-v2/Genesis as a fallback.
    primary = repo_root() / "Genesis" / "schema" / "v18_0"
    if primary.is_dir():
        return primary
    secondary = Path(__file__).resolve().parents[2] / "Genesis" / "schema" / "v18_0"
    return secondary


def load_canon_dict(path: Path, *, reason: str = "SCHEMA_FAIL") -> dict[str, Any]:
    try:
        obj = load_canon_json(path)
    except CanonError:
        fail(reason)
    if not isinstance(obj, dict):
        fail(reason)
    return obj


def canon_hash_obj(obj: Any) -> str:
    return sha256_prefixed(canon_bytes(obj))


def hash_bytes(data: bytes) -> str:
    return sha256_prefixed(data)


def hash_file_stream(path: Path, *, chunk_size: int = 4 * 1024 * 1024) -> str:
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    file_digest_fn = getattr(hashlib, "file_digest", None)
    with path.open("rb") as handle:
        if callable(file_digest_fn):
            try:
                digest_obj = file_digest_fn(handle, "sha256")
            except Exception:
                handle.seek(0)
            else:
                return f"sha256:{digest_obj.hexdigest()}"
        hasher = hashlib.sha256()
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def hash_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    return hash_file_stream(path)


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
        for path in schema_root.glob("*.json*"):
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


def write_hashed_json(
    out_dir: Path,
    suffix: str,
    payload: dict[str, Any],
    *,
    id_field: str | None = None,
) -> tuple[Path, dict[str, Any], str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    obj = dict(payload)
    if id_field is not None:
        no_id = dict(obj)
        no_id.pop(id_field, None)
        obj[id_field] = canon_hash_obj(no_id)
    digest = canon_hash_obj(obj)
    name = f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    out_path = out_dir / name
    write_canon_json(out_path, obj)
    return out_path, obj, digest


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    write_jsonl_line(path, payload)


def ensure_sha256(value: Any, *, reason: str = "SCHEMA_FAIL") -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        fail(reason)
    return value


def require_relpath(path_value: Any, *, reason: str = "SCHEMA_FAIL") -> str:
    if not isinstance(path_value, str) or not path_value:
        fail(reason)
    p = Path(path_value)
    if p.is_absolute() or ".." in p.parts:
        fail(reason)
    if "\\" in path_value:
        fail(reason)
    return path_value


def q32_int(value: Any) -> int:
    if not isinstance(value, dict) or set(value.keys()) != {"q"}:
        fail("SCHEMA_FAIL")
    q = value.get("q")
    if not isinstance(q, int):
        fail("SCHEMA_FAIL")
    return q


def q32_obj(value: int) -> dict[str, int]:
    return {"q": int(value)}


def rat_q32(num_u64: int, den_u64: int) -> int:
    if den_u64 <= 0 or num_u64 < 0:
        fail("SCHEMA_FAIL")
    return (int(num_u64) * Q32_ONE) // int(den_u64)


def q32_mul(lhs_q: int, rhs_q: int) -> int:
    return (int(lhs_q) * int(rhs_q)) >> 32


def cmp_q32(lhs_q: int, comparator: str, rhs_q: int) -> bool:
    if comparator == "GT":
        return lhs_q > rhs_q
    if comparator == "GE":
        return lhs_q >= rhs_q
    if comparator == "LT":
        return lhs_q < rhs_q
    if comparator == "LE":
        return lhs_q <= rhs_q
    if comparator == "EQ":
        return lhs_q == rhs_q
    fail("SCHEMA_FAIL")
    return False


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            fail("SCHEMA_FAIL")
        if not isinstance(payload, dict):
            fail("SCHEMA_FAIL")
        rows.append(payload)
    return rows


def _iter_files_fast(root: Path) -> list[tuple[str, str]]:
    if root.is_symlink():
        fail("SCHEMA_FAIL")
    root_abs = root.resolve()
    files: list[tuple[str, str]] = []
    stack: list[tuple[str, Path]] = [("", root_abs)]
    while stack:
        rel_dir, abs_dir = stack.pop()
        try:
            with os.scandir(abs_dir) as iterator:
                entries = list(iterator)
        except OSError:
            fail("SCHEMA_FAIL")
        for entry in entries:
            if entry.is_symlink():
                fail("SCHEMA_FAIL")
            rel_posix = entry.name if not rel_dir else f"{rel_dir}/{entry.name}"
            try:
                if entry.is_file(follow_symlinks=False):
                    files.append((rel_posix, entry.path))
                elif entry.is_dir(follow_symlinks=False):
                    stack.append((rel_posix, Path(entry.path)))
            except OSError:
                fail("SCHEMA_FAIL")
    return files


def tree_hash(root: Path) -> str:
    if not root.exists() or not root.is_dir():
        fail("MISSING_STATE_INPUT")
    entries = _iter_files_fast(root)
    entries.sort(key=lambda row: row[0])
    files: list[dict[str, str]] = []
    for rel_posix, abs_path_str in entries:
        files.append({"path": rel_posix, "sha256": hash_file_stream(Path(abs_path_str))})
    return canon_hash_obj({"schema_version": "omega_tree_hash_v1", "files": files})


def collect_single(path: Path, pattern: str, *, reason: str = "SCHEMA_FAIL") -> Path:
    rows = sorted(path.glob(pattern))
    if len(rows) != 1:
        fail(reason)
    return rows[0]


def find_by_hash(path: Path, suffix: str, digest: str) -> Path:
    ensure_sha256(digest)
    candidate = path / f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    if not candidate.exists() or not candidate.is_file():
        fail("MISSING_STATE_INPUT")
    return candidate


def require_no_absolute_paths(value: Any) -> None:
    if isinstance(value, dict):
        for item in value.values():
            require_no_absolute_paths(item)
        return
    if isinstance(value, list):
        for item in value:
            require_no_absolute_paths(item)
        return
    if isinstance(value, str):
        p = Path(value)
        if p.is_absolute() or re.match(r"^[A-Za-z]:[\\/]", value):
            fail("ABSOLUTE_PATH_FORBIDDEN")


__all__ = [
    "OmegaV18Error",
    "Q32_ONE",
    "append_jsonl",
    "canon_hash_obj",
    "cmp_q32",
    "collect_single",
    "ensure_sha256",
    "fail",
    "find_by_hash",
    "hash_bytes",
    "hash_file",
    "hash_file_stream",
    "load_canon_dict",
    "load_jsonl",
    "q32_int",
    "q32_mul",
    "q32_obj",
    "rat_q32",
    "repo_root",
    "require_no_absolute_paths",
    "require_relpath",
    "schema_dir",
    "tree_hash",
    "validate_schema",
    "write_hashed_json",
]
