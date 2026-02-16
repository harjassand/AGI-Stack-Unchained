#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 - <<'PY' > META_HASH
import hashlib
import os
from pathlib import Path

root = Path(os.getcwd())

def sha256_file(path: Path) -> bytes:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.digest()

parts = [b"META_V1_5R\0"]

required = ["constants_v1.json", "pi0_programs_v1.json"]
for name in required:
    parts.append(sha256_file(root / name))

md_files = sorted(root.glob("*.md"))
for path in md_files:
    parts.append(sha256_file(path))

h = hashlib.sha256()
for p in parts:
    h.update(p)

print(h.hexdigest())
PY
