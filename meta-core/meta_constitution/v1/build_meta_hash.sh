#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 - <<'PY' > META_HASH
import hashlib
import os

root = os.getcwd()

def sha256_file(path: str) -> bytes:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.digest()

parts = [b"META_V1\0"]

spec_files = [
    "metaconst.json",
    "policy.json",
    "costvec.json",
    "ir_limits.json",
    "statement_set.json",
]

for name in spec_files:
    parts.append(sha256_file(os.path.join(root, "spec", name)))

schema_files = []
for dirpath, _, filenames in os.walk(os.path.join(root, "schemas")):
    for fn in filenames:
        if fn.endswith(".json"):
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            schema_files.append(rel)

schema_files.sort()
for rel in schema_files:
    parts.append(sha256_file(os.path.join(root, rel)))

h = hashlib.sha256()
for p in parts:
    h.update(p)

print(h.hexdigest())
PY
