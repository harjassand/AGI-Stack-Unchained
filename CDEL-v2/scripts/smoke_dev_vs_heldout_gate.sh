#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"
DEV_HASH="51eed9de39888ab6ec84c5c0e73f79f1c62b62ef8dfc532497d1f63b4b149900"
HELDOUT_HASH="26eefc93c8e0ef98923f3f0525fc7fbd422abe0089caf8e88aec158138cb50b7"

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

HELDOUT_DIR="$(mktemp -d)"
export CDEL_SUITES_DIR="$HELDOUT_DIR"

python3 - <<PY
import json
from pathlib import Path

path = Path("$HELDOUT_DIR") / "${HELDOUT_HASH}.jsonl"
rows = []
for value in range(256):
    rows.append({"args": [{"tag": "int", "value": value}]})
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
from pathlib import Path
import json
from cdel.config import load_config_from_path, write_config_path

root = Path("$WORKDIR")
keypair = json.loads((root / "sealed_keypair.json").read_text(encoding="utf-8"))

def materialize(template: str, out_name: str) -> None:
    cfg = load_config_from_path(root, Path(template))
    sealed = dict(cfg.data.get("sealed") or {})
    episodes = sealed.get("episodes")
    sealed["public_key"] = keypair["public_key"]
    sealed["key_id"] = keypair["key_id"]
    sealed.setdefault("public_keys", [])
    sealed.setdefault("prev_public_keys", [])
    cfg.data["sealed"] = sealed
    out_path = root / out_name
    write_config_path(out_path, cfg.data)
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

materialize("$ROOT_DIR/configs/sealed_suite_dev.toml", "dev_config.toml")
materialize("$ROOT_DIR/configs/sealed_suite_heldout.toml", "heldout_config.toml")
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
                            "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": 2}],
                        },
                        {"tag": "int", "value": 0},
                    ],
                },
                "termination": {"kind": "structural", "decreases_param": None},
            },
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [],
    },
}
(root / "module_base.json").write_text(json.dumps(base, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/heldout_config.toml" commit "$WORKDIR/module_base.json"

python3 - <<PY
from pathlib import Path
import json

root = Path("$WORKDIR")
overfit = {
    "new_symbols": ["overfit"],
    "definitions": [{
        "name": "overfit",
        "params": [{"name": "n", "type": {"tag": "int"}}],
        "ret_type": {"tag": "bool"},
        "body": {
            "tag": "if",
            "cond": {"tag": "prim", "op": "le_int", "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": 2}]},
            "then": {"tag": "app", "fn": {"tag": "sym", "name": "is_even_oracle"}, "args": [{"tag": "var", "name": "n"}]},
            "else": {"tag": "bool", "value": False},
        },
        "termination": {"kind": "structural", "decreases_param": None},
    }],
    "declared_deps": ["is_even_oracle"],
    "specs": [],
    "concepts": [{"concept": "parity", "symbol": "overfit"}],
}
(root / "candidate_overfit.json").write_text(json.dumps(overfit, sort_keys=True) + "\n", encoding="utf-8")

good = {
    "new_symbols": ["good"],
    "definitions": [{
        "name": "good",
        "params": [{"name": "n", "type": {"tag": "int"}}],
        "ret_type": {"tag": "bool"},
        "body": {"tag": "app", "fn": {"tag": "sym", "name": "is_even_oracle"}, "args": [{"tag": "var", "name": "n"}]},
        "termination": {"kind": "structural", "decreases_param": None},
    }],
    "declared_deps": ["is_even_oracle"],
    "specs": [],
    "concepts": [{"concept": "parity", "symbol": "good"}],
}
(root / "candidate_good.json").write_text(json.dumps(good, sort_keys=True) + "\n", encoding="utf-8")
PY

if python3 scripts/promote_candidate_dev_vs_heldout.py \
  --concept parity \
  --baseline baseline_bad \
  --candidate overfit \
  --oracle is_even_oracle \
  --dev-config "$WORKDIR/dev_config.toml" \
  --heldout-config "$WORKDIR/heldout_config.toml" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 5 \
  --request-out "$WORKDIR/request_overfit.json" \
  --signed-cert-out "$WORKDIR/signed_overfit.json" \
  --module-out "$WORKDIR/module_overfit.json" \
  --candidate-module "$WORKDIR/candidate_overfit.json" \
  --heldout-suites-dir "$HELDOUT_DIR" \
  --root "$WORKDIR"; then
  echo "ERROR: expected heldout issuance to fail for overfit candidate"
  exit 1
fi

python3 scripts/promote_candidate_dev_vs_heldout.py \
  --concept parity \
  --baseline baseline_bad \
  --candidate good \
  --oracle is_even_oracle \
  --dev-config "$WORKDIR/dev_config.toml" \
  --heldout-config "$WORKDIR/heldout_config.toml" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 5 \
  --request-out "$WORKDIR/request_good.json" \
  --signed-cert-out "$WORKDIR/signed_good.json" \
  --module-out "$WORKDIR/module_good.json" \
  --candidate-module "$WORKDIR/candidate_good.json" \
  --heldout-suites-dir "$HELDOUT_DIR" \
  --root "$WORKDIR"

echo "$WORKDIR"
