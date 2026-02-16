#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"

cd "$ROOT_DIR"

cdel --root "$WORKDIR" init --budget 1000000
cdel --root "$WORKDIR" run-tasks "$ROOT_DIR/tasks/stream_min.jsonl" --generator enum --out "$WORKDIR/runs/min"
cdel --root "$WORKDIR" check-invariants
cdel --root "$WORKDIR" eval --expr '{"tag":"app","fn":{"tag":"sym","name":"inc"},"args":[{"tag":"int","value":1}]}' >/dev/null

cdel --root "$WORKDIR" sealed keygen --out "$WORKDIR/sealed_keypair.json"

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

cdel --root "$WORKDIR" sealed worker \
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

cdel --root "$WORKDIR" commit "$WORKDIR/module_candidate.json"

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

cdel --root "$WORKDIR" adopt "$WORKDIR/adoption.json"
cdel --root "$WORKDIR" resolve --concept increment >/dev/null

echo "$WORKDIR"
