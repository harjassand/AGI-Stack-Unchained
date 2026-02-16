#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"

cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python3
fi

cdel_cmd() {
  "$PYTHON_BIN" -m cdel.cli "$@"
}

cdel_cmd --root "$WORKDIR" init --budget 1000000
cdel_cmd --root "$WORKDIR" sealed keygen --out "$WORKDIR/sealed_keypair.json"

python3 - <<PY
from pathlib import Path
import json
from cdel.config import load_config, write_config

root = Path("$WORKDIR")
cfg = load_config(root)
data = cfg.data
keypair = json.loads((root / "sealed_keypair.json").read_text(encoding="utf-8"))
data["sealed"] = {
    "public_key": keypair["public_key"],
    "key_id": keypair["key_id"],
    "public_keys": [],
    "prev_public_keys": [],
    "alpha_total": "1e-4",
    "alpha_schedule": {"name": "p_series", "exponent": 2, "coefficient": "0.60792710185402662866"},
    "eval_harness_id": "toy-harness-v1",
    "eval_harness_hash": "harness-hash",
    "eval_suite_hash": "suite-hash",
}
write_config(root, data)
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

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" commit "$WORKDIR/module_base.json"

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
    "eval": {"episodes": 4, "max_steps": 50, "paired_seeds": True, "oracle_symbol": "inc"},
    "risk": {"evalue_threshold": "1e-6"},
}
(root / "stat_cert_request.json").write_text(json.dumps(spec, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed worker \
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

python3 - <<PY
from pathlib import Path
import json
from cdel.config import load_config, write_config

root = Path("$WORKDIR")
cfg = load_config(root)
data = cfg.data
sealed = dict(data.get("sealed") or {})
sealed["eval_harness_hash"] = "mismatch-hash"
data["sealed"] = sealed
write_config(root, data)
PY

if cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" verify "$WORKDIR/module_candidate.json"; then
  echo "expected verify failure for mismatched harness hash"
  exit 1
fi

python3 - <<PY
from pathlib import Path
import json
from cdel.config import load_config, write_config

root = Path("$WORKDIR")
cfg = load_config(root)
data = cfg.data
keypair = json.loads((root / "sealed_keypair.json").read_text(encoding="utf-8"))
data["sealed"] = {
    "public_key": keypair["public_key"],
    "key_id": keypair["key_id"],
    "public_keys": [],
    "prev_public_keys": [],
    "alpha_total": "1e-4",
    "alpha_schedule": {"name": "p_series", "exponent": 2, "coefficient": "0.60792710185402662866"},
    "eval_harness_id": "toy-harness-v1",
    "eval_harness_hash": "harness-hash",
    "eval_suite_hash": "suite-hash",
}
write_config(root, data)
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" commit "$WORKDIR/module_candidate.json"

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

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" adopt "$WORKDIR/adoption.json"
cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" resolve --concept increment >/dev/null

echo "$WORKDIR"
