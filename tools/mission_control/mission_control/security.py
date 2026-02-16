"""Fail-closed security module for Mission Control.

Implements path traversal protection and run_id validation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

# Run ID must match: alphanumeric, dots, underscores, hyphens, 1-128 chars
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def validate_run_id(run_id: str) -> str:
    """Validate run_id matches allowed pattern.
    
    Args:
        run_id: The run identifier to validate.
        
    Returns:
        The validated run_id if valid.
        
    Raises:
        HTTPException: 400 if run_id is invalid.
    """
    if not isinstance(run_id, str):
        raise HTTPException(status_code=400, detail="INVALID_RUN_ID")
    if not RUN_ID_PATTERN.match(run_id):
        raise HTTPException(status_code=400, detail="INVALID_RUN_ID")
    return run_id


def _is_path_safe(subpath: str) -> bool:
    """Check if a subpath is safe (no traversal attempts).
    
    Args:
        subpath: The relative path to check.
        
    Returns:
        True if safe, False otherwise.
    """
    if not isinstance(subpath, str):
        return False
    # Reject null bytes
    if "\x00" in subpath:
        return False
    # Reject backslashes (Windows-style paths)
    if "\\" in subpath:
        return False
    # Reject absolute paths
    if subpath.startswith("/"):
        return False
    # Reject parent directory traversal
    parts = subpath.replace("\\", "/").split("/")
    for part in parts:
        if part == "..":
            return False
    return True


def safe_resolve_path(
    runs_root: Path,
    run_id: str,
    subpath: str = "",
) -> Optional[Path]:
    """Safely resolve a path within the runs root.
    
    Args:
        runs_root: The canonical runs root directory.
        run_id: The run identifier (must be validated first).
        subpath: Optional relative subpath within the run directory.
        
    Returns:
        Resolved Path if safe and within runs_root, None otherwise.
        
    Raises:
        HTTPException: 400 if path validation fails.
    """
    # Validate run_id first
    validate_run_id(run_id)
    
    # Check subpath safety
    if subpath and not _is_path_safe(subpath):
        raise HTTPException(status_code=400, detail="INVALID_PATH")
    
    # Resolve runs_root to canonical form
    canonical_root = runs_root.resolve()
    
    # Build the target path
    if subpath:
        target = canonical_root / run_id / subpath
    else:
        target = canonical_root / run_id
    
    # Resolve to canonical form
    try:
        canonical_target = target.resolve()
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="INVALID_PATH")
    
    # Verify the resolved path is within runs_root
    try:
        canonical_target.relative_to(canonical_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="PATH_TRAVERSAL_DETECTED")
    
    return canonical_target


def safe_resolve_path_or_none(
    runs_root: Path,
    run_id: str,
    subpath: str = "",
) -> Optional[Path]:
    """Safely resolve a path, returning None on any error.
    
    Same as safe_resolve_path but returns None instead of raising.
    """
    try:
        return safe_resolve_path(runs_root, run_id, subpath)
    except HTTPException:
        return None


__all__ = [
    "RUN_ID_PATTERN",
    "validate_run_id",
    "safe_resolve_path",
    "safe_resolve_path_or_none",
]
