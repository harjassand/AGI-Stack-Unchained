"""Content-addressed ledger storage."""

from __future__ import annotations

import json
import os
from pathlib import Path

from cdel.config import Config

GENESIS_HASH = "GENESIS"

try:  # pragma: no cover - optional on non-posix platforms
    import fcntl
except Exception:  # pragma: no cover - fallback when fcntl is unavailable
    fcntl = None


def init_storage(cfg: Config) -> None:
    cfg.ledger_dir.mkdir(parents=True, exist_ok=True)
    cfg.objects_dir.mkdir(parents=True, exist_ok=True)
    cfg.meta_dir.mkdir(parents=True, exist_ok=True)
    cfg.index_dir.mkdir(parents=True, exist_ok=True)
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    cfg.tasks_dir.mkdir(parents=True, exist_ok=True)
    if not cfg.head_file.exists():
        cfg.head_file.write_text(GENESIS_HASH, encoding="utf-8")
    if not cfg.order_log.exists():
        cfg.order_log.write_text("", encoding="utf-8")


def object_path(cfg: Config, payload_hash: str) -> Path:
    prefix = payload_hash[:2]
    return cfg.objects_dir / prefix / f"{payload_hash}.blob"


def write_object(cfg: Config, payload_hash: str, payload_bytes: bytes) -> None:
    path = object_path(cfg, payload_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("wb") as fh:
        fh.write(payload_bytes)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


def append_order_log(cfg: Config, payload_hash: str) -> bool:
    cfg.order_log.parent.mkdir(parents=True, exist_ok=True)
    with cfg.order_log.open("a+", encoding="utf-8") as fh:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.seek(0)
            lines = fh.read().splitlines()
            last = lines[-1].strip() if lines else ""
            if last == payload_hash:
                return False
            fh.write(payload_hash + "\n")
            fh.flush()
            os.fsync(fh.fileno())
            return True
        finally:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def read_head(cfg: Config) -> str:
    order = iter_order_log(cfg)
    if order:
        return order[-1]
    if not cfg.head_file.exists():
        return GENESIS_HASH
    return cfg.head_file.read_text(encoding="utf-8").strip() or GENESIS_HASH


def write_head(cfg: Config, payload_hash: str) -> None:
    cfg.head_file.write_text(payload_hash, encoding="utf-8")


def read_object(cfg: Config, payload_hash: str) -> bytes:
    path = object_path(cfg, payload_hash)
    return path.read_bytes()


def meta_path(cfg: Config, payload_hash: str) -> Path:
    return cfg.meta_dir / f"{payload_hash}.json"


def write_meta(cfg: Config, payload_hash: str, meta: dict) -> None:
    path = meta_path(cfg, payload_hash)
    tmp_path = path.with_suffix(".tmp")
    data = json.dumps(meta, sort_keys=True, ensure_ascii=True)
    with tmp_path.open("w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


def read_meta(cfg: Config, payload_hash: str) -> dict | None:
    path = meta_path(cfg, payload_hash)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def iter_order_log(cfg: Config) -> list[str]:
    if not cfg.order_log.exists():
        return []
    lines = cfg.order_log.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]
