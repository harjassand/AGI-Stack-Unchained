"""Deterministic candidate tar writing for CAOE v1 proposer."""

from __future__ import annotations

import io
import tarfile
import sys
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[1]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from api_v1 import canonical_json_bytes  # noqa: E402

DETERMINISTIC_MTIME = 0
DETERMINISTIC_UID = 0
DETERMINISTIC_GID = 0
DETERMINISTIC_UNAME = "root"
DETERMINISTIC_GNAME = "root"
FILE_MODE = 0o644
DIR_MODE = 0o755


class TarBuildError(ValueError):
    pass


def _iter_dirs_for_paths(paths: list[str]) -> set[str]:
    dirs: set[str] = set()
    for path in paths:
        p = Path(path)
        for parent in p.parents:
            if parent == Path("."):
                continue
            dirs.add(parent.as_posix())
    return dirs


def _tarinfo_for_dir(name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    info.type = tarfile.DIRTYPE
    info.mode = DIR_MODE
    info.uid = DETERMINISTIC_UID
    info.gid = DETERMINISTIC_GID
    info.uname = DETERMINISTIC_UNAME
    info.gname = DETERMINISTIC_GNAME
    info.mtime = DETERMINISTIC_MTIME
    info.size = 0
    return info


def _tarinfo_for_file(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    info.type = tarfile.REGTYPE
    info.mode = FILE_MODE
    info.uid = DETERMINISTIC_UID
    info.gid = DETERMINISTIC_GID
    info.uname = DETERMINISTIC_UNAME
    info.gname = DETERMINISTIC_GNAME
    info.mtime = DETERMINISTIC_MTIME
    info.size = size
    return info


def build_deterministic_tar_bytes(files: dict[str, bytes]) -> bytes:
    all_dirs = _iter_dirs_for_paths(sorted(files.keys()))
    entries = sorted(set(files.keys()) | all_dirs)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tf:
        for name in entries:
            if name in all_dirs:
                tf.addfile(_tarinfo_for_dir(name))
                continue
            data = files[name]
            tf.addfile(_tarinfo_for_file(name, len(data)), io.BytesIO(data))
    return buffer.getvalue()


def build_candidate_tar_bytes(
    manifest: dict[str, Any],
    ontology_patch: dict[str, Any],
    mechanism_diff: dict[str, Any] | None,
    programs_by_path: dict[str, bytes],
) -> bytes:
    if mechanism_diff is None:
        mechanism_diff = {}
    files: dict[str, bytes] = {
        "manifest.json": canonical_json_bytes(manifest),
        "ontology_patch.json": canonical_json_bytes(ontology_patch),
        "mechanism_registry_diff.json": canonical_json_bytes(mechanism_diff),
    }
    for path, data in programs_by_path.items():
        files[path] = data
    return build_deterministic_tar_bytes(files)


def write_candidate_tar(
    path: str | Path,
    manifest: dict[str, Any],
    ontology_patch: dict[str, Any],
    mechanism_diff: dict[str, Any] | None,
    programs_by_path: dict[str, bytes],
) -> bytes:
    data = build_candidate_tar_bytes(manifest, ontology_patch, mechanism_diff, programs_by_path)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(data)
    return data
