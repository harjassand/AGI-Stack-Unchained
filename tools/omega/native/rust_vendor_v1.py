#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any


def _canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _hash_file(path: Path) -> str:
    return _sha256_prefixed(path.read_bytes())


def _tree_entries(root: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for cur_root, dirs, files in os.walk(root, topdown=True, followlinks=False):
        cur = Path(cur_root)
        rel_root = cur.relative_to(root)
        dirs[:] = sorted([d for d in dirs if d != "target" and d != ".git"])
        for name in sorted(files):
            p = cur / name
            if p.is_symlink():
                payload = ("SYMLINK->" + os.readlink(p)).encode("utf-8")
            else:
                payload = p.read_bytes()
            rel = (rel_root / name).as_posix() if str(rel_root) != "." else name
            entries.append({"path_rel": rel, "sha256": _sha256_prefixed(payload)})
    entries.sort(key=lambda row: row["path_rel"])
    return entries


def tree_hash(root: Path) -> str:
    payload = {"schema_version": "omega_native_tree_v1", "entries": _tree_entries(root)}
    return _sha256_prefixed(_canon_bytes(payload))


def vendor_crate(*, crate_dir: Path, cargo_exe: Path | None = None) -> dict[str, Any]:
    crate_dir = crate_dir.resolve()
    vendor_dir = crate_dir / "vendor"
    cargo_dir = crate_dir / ".cargo"
    cargo_dir.mkdir(parents=True, exist_ok=True)

    exe = str(cargo_exe) if cargo_exe is not None else "cargo"
    cmd = [exe, "vendor", "--frozen", "--offline", str(vendor_dir)]
    res = subprocess.run(cmd, cwd=crate_dir, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError("VENDOR_FAIL")
    vendor_dir.mkdir(parents=True, exist_ok=True)

    config_toml = "\n".join(
        [
            "[net]",
            "offline = true",
            "",
            "[source.crates-io]",
            "replace-with = \"vendored-sources\"",
            "",
            "[source.vendored-sources]",
            "directory = \"vendor\"",
            "",
        ]
    )
    config_path = cargo_dir / "config.toml"
    config_path.write_text(config_toml, encoding="utf-8")

    manifest_wo_id = {
        "schema_version": "omega_native_vendor_manifest_v1",
        "manifest_id": "sha256:" + ("0" * 64),
        "vendor_tree_hash": tree_hash(vendor_dir),
        "cargo_config_toml_sha256": _hash_file(config_path),
        "notes": "",
    }
    manifest = dict(manifest_wo_id)
    manifest["manifest_id"] = _sha256_prefixed(_canon_bytes({k: v for k, v in manifest.items() if k != "manifest_id"}))
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(prog="rust_vendor_v1")
    ap.add_argument("--crate_dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cargo_exe", default="")
    args = ap.parse_args()

    cargo_exe = Path(args.cargo_exe).resolve() if str(args.cargo_exe).strip() else None
    manifest = vendor_crate(crate_dir=Path(args.crate_dir), cargo_exe=cargo_exe)
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(_canon_bytes(manifest))
    print(json.dumps({"status": "OK", "vendor_manifest_id": manifest["manifest_id"]}, separators=(",", ":")))


if __name__ == "__main__":
    main()
