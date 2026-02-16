#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"
DEV_HASH="51eed9de39888ab6ec84c5c0e73f79f1c62b62ef8dfc532497d1f63b4b149900"

cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python3
fi

cdel_cmd() {
  "$PYTHON_BIN" -m cdel.cli "$@"
}

mkdir -p "$WORKDIR/sealed_suites"
cp "$ROOT_DIR/sealed_suites/${DEV_HASH}.jsonl" "$WORKDIR/sealed_suites/${DEV_HASH}.jsonl"

cdel_cmd --root "$WORKDIR" init --budget 1000000
cdel_cmd --root "$WORKDIR" sealed keygen --out "$WORKDIR/sealed_keypair.json"

python3 - <<PY
from pathlib import Path
import json
from cdel.config import load_config_from_path, write_config_path

root = Path("$WORKDIR")
template = Path("$ROOT_DIR/configs/sealed_suite_dev.toml")
cfg = load_config_from_path(root, template)
data = cfg.data
keypair = json.loads((root / "sealed_keypair.json").read_text(encoding="utf-8"))
sealed = dict(data.get("sealed") or {})
episodes = sealed.get("episodes")
sealed["public_key"] = keypair["public_key"]
sealed["key_id"] = keypair["key_id"]
sealed.setdefault("public_keys", [])
sealed.setdefault("prev_public_keys", [])
data["sealed"] = sealed
out_path = root / "sealed_suite_dev.toml"
write_config_path(out_path, data)
if isinstance(episodes, int):
    lines = out_path.read_text(encoding="utf-8").splitlines()
    out_lines = []
    inserted = False
    for line in lines:
        out_lines.append(line)
        if line.startswith("eval_suite_hash"):
            out_lines.append(f"episodes = {episodes}")
            inserted = True
    if not inserted:
        raise RuntimeError("failed to inject episodes into config")
    out_path.write_text("\n".join(out_lines).strip() + "\n", encoding="utf-8")
PY

python3 - <<PY
from pathlib import Path
import json

root = Path("$WORKDIR")
base = {
    "schema_version": 1,
    "dsl_version": 1,
    "parent": "GENESIS",
    "payload": {
        "new_symbols": ["inc"],
        "definitions": [{
            "name": "inc",
            "params": [{"name": "n", "type": {"tag": "int"}}],
            "ret_type": {"tag": "int"},
            "body": {"tag": "prim", "op": "add", "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": 1}]},
            "termination": {"kind": "structural", "decreases_param": None},
        }],
        "declared_deps": [],
        "specs": [],
        "concepts": [],
    },
}
(root / "module_base.json").write_text(json.dumps(base, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/sealed_suite_dev.toml" commit "$WORKDIR/module_base.json"

python3 - <<PY
from pathlib import Path
import json

root = Path("$WORKDIR")
candidate = {
    "new_symbols": ["inc_v2"],
    "definitions": [{
        "name": "inc_v2",
        "params": [{"name": "n", "type": {"tag": "int"}}],
        "ret_type": {"tag": "int"},
        "body": {"tag": "prim", "op": "add", "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": 1}]},
        "termination": {"kind": "structural", "decreases_param": None},
    }],
    "declared_deps": ["inc"],
    "specs": [],
    "concepts": [{"concept": "increment", "symbol": "inc_v2"}],
}
(root / "candidate_defs.json").write_text(json.dumps(candidate, sort_keys=True) + "\n", encoding="utf-8")

spec = {
    "kind": "stat_cert",
    "concept": "increment",
    "metric": "accuracy",
    "null": "no_improvement",
    "baseline_symbol": "inc",
    "candidate_symbol": "inc_v2",
    "eval": {"episodes": 32, "max_steps": 50, "paired_seeds": True, "oracle_symbol": "inc"},
    "risk": {"evalue_threshold": "1e-6"},
}
(root / "stat_cert_request.json").write_text(json.dumps(spec, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/sealed_suite_dev.toml" sealed worker \
  --request "$WORKDIR/stat_cert_request.json" \
  --out "$WORKDIR/stat_cert_signed.json" \
  --private-key "$(python3 - <<PY
import json
from pathlib import Path
print(json.loads(Path("$WORKDIR/sealed_keypair.json").read_text(encoding="utf-8"))["private_key"])
PY
)" \
  --seed-key "sealed-seed" \
  --candidate-module "$WORKDIR/candidate_defs.json"

python3 - <<PY
from pathlib import Path
import json

root = Path("$WORKDIR")
spec = json.loads((root / "stat_cert_signed.json").read_text(encoding="utf-8"))
candidate = json.loads((root / "candidate_defs.json").read_text(encoding="utf-8"))
module = {
    "schema_version": 1,
    "dsl_version": 1,
    "parent": (root / "ledger" / "head").read_text(encoding="utf-8").strip(),
    "payload": {
        **candidate,
        "specs": [spec],
    },
}
(root / "module_candidate.json").write_text(json.dumps(module, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/sealed_suite_dev.toml" commit "$WORKDIR/module_candidate.json"

python3 - <<PY
from pathlib import Path
import json

root = Path("$WORKDIR")
spec = json.loads((root / "stat_cert_signed.json").read_text(encoding="utf-8"))
adoption = {
    "schema_version": 1,
    "parent": (root / "adoption" / "head").read_text(encoding="utf-8").strip(),
    "payload": {
        "concept": "increment",
        "chosen_symbol": "inc_v2",
        "baseline_symbol": None,
        "certificate": spec,
        "constraints": {},
    },
}
(root / "adoption.json").write_text(json.dumps(adoption, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/sealed_suite_dev.toml" adopt "$WORKDIR/adoption.json"
cdel_cmd --root "$WORKDIR" --config "$WORKDIR/sealed_suite_dev.toml" resolve --concept increment >/dev/null

echo "$WORKDIR"
