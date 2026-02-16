#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json

files = [
  "schema/capsule.schema.json",
  "examples/algorithm.capsule.json",
  "examples/world_model.capsule.json",
  "examples/causal_model.capsule.json",
  "examples/policy.capsule.json",
]

ok = 0
for f in files:
  with open(f, "r", encoding="utf-8") as fp:
    json.load(fp)
  ok += 1

print(f"parsed all JSON files; {ok} OK")
PY

python3 - <<'PY'
import json

try:
  import jsonschema
except Exception:
  print("jsonschema not available; skipping schema validation")
  raise SystemExit(0)

with open("schema/capsule.schema.json", "r", encoding="utf-8") as fp:
  schema = json.load(fp)

capsules = [
  "examples/algorithm.capsule.json",
  "examples/world_model.capsule.json",
  "examples/causal_model.capsule.json",
  "examples/policy.capsule.json",
]

for f in capsules:
  with open(f, "r", encoding="utf-8") as fp:
    capsule = json.load(fp)
  jsonschema.validate(capsule, schema)

print("schema validation OK")
PY
