"""Proposal inbox paths for v1.5r campaigns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..canon import CanonError, hash_json, load_canon_json

INBOX_FAMILY_DIR = "current/inbox/family_proposals_v1"
INBOX_MACRO_DIR = "current/inbox/macro_proposals_v1"
INBOX_MECH_PATCH_DIR = "current/inbox/mech_patch_proposals_v1"
INBOX_META_PATCH_DIR = "current/inbox/meta_patch_proposals_v1"


def _load_inbox_dir(root: Path, schema: str) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    proposals: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        payload = load_canon_json(path)
        expected = hash_json(payload).split(":", 1)[1]
        if path.stem != expected:
            raise CanonError(f"inbox hash mismatch: {path.name}")
        if payload.get("schema") != schema:
            raise CanonError(f"inbox schema mismatch: {path.name}")
        proposals.append(payload)
    return proposals


def load_family_proposals(state_dir: Path) -> list[dict[str, Any]]:
    return _load_inbox_dir(state_dir / INBOX_FAMILY_DIR, "family_dsl_v1")


def load_macro_proposals(state_dir: Path) -> list[dict[str, Any]]:
    return _load_inbox_dir(state_dir / INBOX_MACRO_DIR, "macro_def_v1")


def load_mech_patch_proposals(state_dir: Path) -> list[dict[str, Any]]:
    return _load_inbox_dir(state_dir / INBOX_MECH_PATCH_DIR, "mech_patch_v1")


def load_meta_patch_proposals(state_dir: Path) -> list[dict[str, Any]]:
    return _load_inbox_dir(state_dir / INBOX_META_PATCH_DIR, "meta_patch_proposal_v1")
