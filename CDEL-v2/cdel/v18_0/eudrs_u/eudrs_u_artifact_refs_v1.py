"""EUDRS-U ArtifactRef contract (v1).

ArtifactRefV1 is the mandatory contract for content-addressed artifacts.

Canonical JSON hashing rule:
  artifact_id == sha256(canon_bytes(obj))
Binary hashing rule:
  artifact_id == sha256(file_bytes)

All path validation is fail-closed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..omega_common_v1 import ensure_sha256, fail, require_no_absolute_paths
from .eudrs_u_hash_v1 import gcj1_loads_and_verify_canonical, sha256_file_stream, sha256_prefixed

_DRIVE_LETTER_RE = re.compile(r"^[A-Za-z]:[\\/]")


def require_safe_relpath_v1(path_value: Any, *, reason: str = "SCHEMA_FAIL") -> str:
    """Require a safe repo-relative POSIX path.

    Constraints (v1):
      - not absolute
      - no '..' segments
      - no backslashes
      - no NUL
      - must not start with '/'
      - must not be a Windows drive absolute path

    Note: This does not assert existence.
    """

    if not isinstance(path_value, str) or not path_value:
        fail(reason)
    if "\x00" in path_value:
        fail(reason)
    if "\\" in path_value:
        fail(reason)
    if path_value.startswith("/"):
        fail(reason)
    if _DRIVE_LETTER_RE.match(path_value) is not None:
        fail(reason)

    p = Path(path_value)
    if p.is_absolute() or ".." in p.parts:
        fail(reason)
    return path_value


def require_artifact_ref_v1(value: Any, *, reason: str = "SCHEMA_FAIL") -> dict[str, str]:
    if not isinstance(value, dict) or set(value.keys()) != {"artifact_id", "artifact_relpath"}:
        fail(reason)
    artifact_id = ensure_sha256(value.get("artifact_id"), reason=reason)
    artifact_relpath = require_safe_relpath_v1(value.get("artifact_relpath"), reason=reason)
    return {"artifact_id": artifact_id, "artifact_relpath": artifact_relpath}


def _resolve_under(base_dir: Path, relpath: str) -> Path:
    base_abs = base_dir.resolve()
    candidate = (base_abs / relpath).resolve()
    try:
        candidate.relative_to(base_abs)
    except Exception:
        fail("SCHEMA_FAIL")
    return candidate


def _require_hashed_filename_matches(*, path: Path, expected_sha256: str) -> None:
    if not expected_sha256.startswith("sha256:"):
        fail("SCHEMA_FAIL")
    expected_hex = expected_sha256.split(":", 1)[1]
    if len(expected_hex) != 64:
        fail("SCHEMA_FAIL")

    name = path.name
    # Spec requires: sha256_<64hex>.<artifact_type>.(json|bin)
    if not name.startswith("sha256_"):
        fail("SCHEMA_FAIL")
    parts = name.split(".")
    if len(parts) < 3:
        fail("SCHEMA_FAIL")
    if parts[0] != f"sha256_{expected_hex}":
        fail("NONDETERMINISTIC")
    if parts[-1] not in {"json", "bin"}:
        fail("SCHEMA_FAIL")
    if any(not segment for segment in parts[1:]):
        fail("SCHEMA_FAIL")


def verify_artifact_ref_v1(
    *,
    artifact_ref: dict[str, Any],
    base_dir: Path,
    expected_relpath_prefix: str | None = None,
) -> Path:
    """Verify ArtifactRefV1 and return the resolved artifact path.

    - Validates safe relpath
    - Validates filename matches claimed sha256 hex
    - Validates content hash matches claimed artifact_id
    - For JSON: enforces GCJ-1 canonical JSON on disk
    """

    if not isinstance(base_dir, Path):
        base_dir = Path(base_dir)
    if not base_dir.exists() or not base_dir.is_dir():
        fail("MISSING_STATE_INPUT")

    ref = require_artifact_ref_v1(artifact_ref)
    artifact_id = ref["artifact_id"]
    relpath = ref["artifact_relpath"]

    if expected_relpath_prefix is not None and not relpath.startswith(str(expected_relpath_prefix)):
        fail("SCHEMA_FAIL")

    path = _resolve_under(base_dir, relpath)
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")

    _require_hashed_filename_matches(path=path, expected_sha256=artifact_id)

    if relpath.endswith(".json"):
        raw = path.read_bytes()
        payload = gcj1_loads_and_verify_canonical(raw)
        require_no_absolute_paths(payload)
        digest = sha256_prefixed(raw)
        if digest != artifact_id:
            fail("NONDETERMINISTIC")
        return path

    if relpath.endswith(".bin"):
        digest = sha256_file_stream(path)
        if digest != artifact_id:
            fail("NONDETERMINISTIC")
        return path

    fail("SCHEMA_FAIL")
    return path


__all__ = [
    "require_artifact_ref_v1",
    "require_safe_relpath_v1",
    "verify_artifact_ref_v1",
]
