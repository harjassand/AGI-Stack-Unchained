#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CDEL_ROOT="$(cd "$ROOT_DIR/../CDEL" && pwd)"
WORKDIR="${1:-$(mktemp -d)}"
DEV_HASH="51eed9de39888ab6ec84c5c0e73f79f1c62b62ef8dfc532497d1f63b4b149900"
HELDOUT_HASH="26eefc93c8e0ef98923f3f0525fc7fbd422abe0089caf8e88aec158138cb50b7"

export PYTHONPATH="$CDEL_ROOT:$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

cdel_cmd() {
  python3 -c 'from cdel.cli import main; main()' "$@"
}

mkdir -p "$WORKDIR/sealed_suites"
cp "$CDEL_ROOT/sealed_suites/${DEV_HASH}.jsonl" "$WORKDIR/sealed_suites/${DEV_HASH}.jsonl"

HELDOUT_DIR="$(mktemp -d)"
python3 - <<PY
import json
from pathlib import Path
path = Path("$HELDOUT_DIR") / "${HELDOUT_HASH}.jsonl"
rows = [{"args": [{"tag": "int", "value": v}]} for v in range(256)]
content = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
path.write_text(content, encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" init --budget 1000000
cdel_cmd --root "$WORKDIR" sealed keygen --out "$WORKDIR/sealed_keypair.json"

export CDEL_SEALED_PRIVKEY
CDEL_SEALED_PRIVKEY="$(python3 - <<PY
import json
from pathlib import Path
print(json.loads(Path("$WORKDIR/sealed_keypair.json").read_text(encoding="utf-8"))["private_key"])
PY
)"

python3 - <<PY
import json
from pathlib import Path
from cdel.config import load_config_from_path, write_config_path

root = Path("$WORKDIR")
keypair = json.loads((root / "sealed_keypair.json").read_text(encoding="utf-8"))

def materialize(template: str, out_name: str) -> None:
    cfg = load_config_from_path(root, Path(template))
    sealed = dict(cfg.data.get("sealed") or {})
    sealed["public_key"] = keypair["public_key"]
    sealed["key_id"] = keypair["key_id"]
    sealed.setdefault("public_keys", [])
    sealed.setdefault("prev_public_keys", [])
    cfg.data["sealed"] = sealed
    write_config_path(root / out_name, cfg.data)

materialize("$CDEL_ROOT/configs/sealed_suite_dev.toml", "dev_config.toml")
materialize("$CDEL_ROOT/configs/sealed_suite_heldout.toml", "heldout_config.toml")
PY

python3 - <<PY
import json
from pathlib import Path

root = Path("$WORKDIR")
base = {
    "schema_version": 1,
    "dsl_version": 1,
    "parent": "GENESIS",
    "payload": {
        "new_symbols": ["baseline_bad", "is_even_oracle"],
        "definitions": [
            {
                "name": "baseline_bad",
                "params": [{"name": "n", "type": {"tag": "int"}}],
                "ret_type": {"tag": "bool"},
                "body": {"tag": "bool", "value": False},
                "termination": {"kind": "structural", "decreases_param": None},
            },
            {
                "name": "is_even_oracle",
                "params": [{"name": "n", "type": {"tag": "int"}}],
                "ret_type": {"tag": "bool"},
                "body": {
                    "tag": "prim",
                    "op": "eq_int",
                    "args": [
                        {
                            "tag": "prim",
                            "op": "mod",
                            "args": [
                                {"tag": "var", "name": "n"},
                                {"tag": "int", "value": 2},
                            ],
                        },
                        {"tag": "int", "value": 0},
                    ],
                },
                "termination": {"kind": "structural", "decreases_param": None},
            },
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [{"concept": "parity", "symbol": "baseline_bad"}],
    },
}
(root / "module_base.json").write_text(json.dumps(base, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/heldout_config.toml" commit "$WORKDIR/module_base.json"

python3 "$ROOT_DIR/scripts/run_orchestrator.py" \
  --root "$WORKDIR" \
  --concept parity \
  --oracle is_even_oracle \
  --dev-config "$WORKDIR/dev_config.toml" \
  --heldout-config "$WORKDIR/heldout_config.toml" \
  --heldout-suites-dir "$HELDOUT_DIR" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 5 \
  --max-attempts 1 \
  --runs-dir "$WORKDIR/orchestrator_runs"

echo "$WORKDIR"
