#!/usr/bin/env python3
import hashlib
import os
import sys

ENGINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "engine"))
sys.path.insert(0, ENGINE_DIR)

import gcj1_min  # noqa: E402


TOOLCHAIN_FILES = [
    "kernel/verifier/toolchain.lock",
    "kernel/verifier/Cargo.lock",
    "kernel/verifier/KERNEL_HASH",
    "kernel/verifier/build.sh",
    "meta_constitution/v1/META_HASH",
    "meta_constitution/v1/build_meta_hash.sh",
    "scripts/build.sh",
]


def sha256_file(path: str) -> tuple[str, int]:
    with open(path, "rb") as f:
        data = f.read()
    return hashlib.sha256(data).hexdigest(), len(data)


def main() -> int:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    files = []
    for rel in TOOLCHAIN_FILES:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"toolchain file missing: {rel}")
        digest, size = sha256_file(path)
        files.append({"path": rel, "sha256": digest, "bytes": size})

    files.sort(key=lambda item: item["path"])
    payload = {"version": 1, "files": files}
    root_hash = hashlib.sha256(gcj1_min.dumps_bytes(payload)).hexdigest()
    sys.stdout.write(root_hash + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
