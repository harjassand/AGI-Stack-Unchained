#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"
DEV_HASH="e5318a63e31376643119a058b2149851132ce370faebbf02ebd103d24a89e848"
HELDOUT_HASH="ef9132f131cace2465a788ee27eb2122d2c02c9b528045643043166865b93003"

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
export HELDOUT_HASH
export HELDOUT_DIR

python3 - <<'PY'
import json
import os
from pathlib import Path

heldout_hash = os.environ["HELDOUT_HASH"]
heldout_dir = Path(os.environ["HELDOUT_DIR"])
path = heldout_dir / f"{heldout_hash}.jsonl"
rows = []
for i in range(32):
    text = f"hello_{i}"
    rows.append({
        "episode": i,
        "task_id": f"copy_text_{i}",
        "max_steps": 3,
        "allowed_tools": ["read_file", "write_file"],
        "initial_fs": [{"path": "input.txt", "contents": text}],
        "tool_calls": [
            {"tool": "read_file", "args": ["input.txt"]},
            {"tool": "write_file", "args": ["out.txt", "$LAST"]},
        ],
        "success": {"type": "file_equals", "path": "out.txt", "contents": text},
    })
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

export ROOT_DIR
export WORKDIR

python3 - <<'PY'
from pathlib import Path
import json
import os
from cdel.config import load_config_from_path, write_config_path

root = Path(os.environ["WORKDIR"])
root_dir = Path(os.environ["ROOT_DIR"])
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

materialize(str(root_dir / "configs" / "sealed_tooluse_dev.toml"), "dev_config.toml")
materialize(str(root_dir / "configs" / "sealed_tooluse_heldout.toml"), "heldout_config.toml")
PY

python3 - <<'PY'
from pathlib import Path
import json
import os

root = Path(os.environ["WORKDIR"])
base = {
    "schema_version": 1,
    "dsl_version": 1,
    "parent": "GENESIS",
    "payload": {
        "new_symbols": ["tool_base", "tool_oracle"],
        "definitions": [
            {
                "name": "tool_base",
                "params": [
                    {"name": "step", "type": {"tag": "int"}},
                    {"name": "last_ok", "type": {"tag": "int"}},
                    {"name": "last_len", "type": {"tag": "int"}},
                ],
                "ret_type": {"tag": "int"},
                "body": {"tag": "int", "value": -1},
                "termination": {"kind": "structural", "decreases_param": None},
            },
            {
                "name": "tool_oracle",
                "params": [
                    {"name": "step", "type": {"tag": "int"}},
                    {"name": "last_ok", "type": {"tag": "int"}},
                    {"name": "last_len", "type": {"tag": "int"}},
                ],
                "ret_type": {"tag": "int"},
                "body": {
                    "tag": "if",
                    "cond": {
                        "tag": "prim",
                        "op": "eq_int",
                        "args": [
                            {"tag": "var", "name": "step"},
                            {"tag": "int", "value": 0},
                        ],
                    },
                    "then": {"tag": "int", "value": 0},
                    "else": {
                        "tag": "if",
                        "cond": {
                            "tag": "prim",
                            "op": "eq_int",
                            "args": [
                                {"tag": "var", "name": "step"},
                                {"tag": "int", "value": 1},
                            ],
                        },
                        "then": {"tag": "int", "value": 1},
                        "else": {"tag": "int", "value": -1},
                    },
                },
                "termination": {"kind": "structural", "decreases_param": None},
            },
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [],
    },
}
path = root / "module_base.json"
path.write_text(json.dumps(base, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/heldout_config.toml" commit "$WORKDIR/module_base.json"

python3 - <<'PY'
from pathlib import Path
import json
import os

root = Path(os.environ["WORKDIR"])
overfit = {
    "new_symbols": ["tool_overfit"],
    "definitions": [
        {
            "name": "tool_overfit",
            "params": [
                {"name": "step", "type": {"tag": "int"}},
                {"name": "last_ok", "type": {"tag": "int"}},
                {"name": "last_len", "type": {"tag": "int"}},
            ],
            "ret_type": {"tag": "int"},
            "body": {
                "tag": "if",
                "cond": {
                    "tag": "prim",
                    "op": "eq_int",
                    "args": [
                        {"tag": "var", "name": "step"},
                        {"tag": "int", "value": 0},
                    ],
                },
                "then": {"tag": "int", "value": 1},
                "else": {"tag": "int", "value": -1},
            },
            "termination": {"kind": "structural", "decreases_param": None},
        }
    ],
    "declared_deps": [],
    "specs": [],
    "concepts": [{"concept": "tooluse.copy_file", "symbol": "tool_overfit"}],
}
(root / "candidate_overfit.json").write_text(json.dumps(overfit, sort_keys=True) + "\n", encoding="utf-8")

good = {
    "new_symbols": ["tool_good"],
    "definitions": [
        {
            "name": "tool_good",
            "params": [
                {"name": "step", "type": {"tag": "int"}},
                {"name": "last_ok", "type": {"tag": "int"}},
                {"name": "last_len", "type": {"tag": "int"}},
            ],
            "ret_type": {"tag": "int"},
            "body": {
                "tag": "if",
                "cond": {
                    "tag": "prim",
                    "op": "eq_int",
                    "args": [
                        {"tag": "var", "name": "step"},
                        {"tag": "int", "value": 0},
                    ],
                },
                "then": {"tag": "int", "value": 0},
                "else": {
                    "tag": "if",
                    "cond": {
                        "tag": "prim",
                        "op": "eq_int",
                        "args": [
                            {"tag": "var", "name": "step"},
                            {"tag": "int", "value": 1},
                        ],
                    },
                    "then": {"tag": "int", "value": 1},
                    "else": {"tag": "int", "value": -1},
                },
            },
            "termination": {"kind": "structural", "decreases_param": None},
        }
    ],
    "declared_deps": [],
    "specs": [],
    "concepts": [{"concept": "tooluse.copy_file", "symbol": "tool_good"}],
}
(root / "candidate_good.json").write_text(json.dumps(good, sort_keys=True) + "\n", encoding="utf-8")
PY

if python3 scripts/promote_candidate_dev_vs_heldout.py \
  --concept tooluse.copy_file \
  --baseline tool_base \
  --candidate tool_overfit \
  --oracle tool_oracle \
  --dev-config "$WORKDIR/dev_config.toml" \
  --heldout-config "$WORKDIR/heldout_config.toml" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 16 \
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
  --concept tooluse.copy_file \
  --baseline tool_base \
  --candidate tool_good \
  --oracle tool_oracle \
  --dev-config "$WORKDIR/dev_config.toml" \
  --heldout-config "$WORKDIR/heldout_config.toml" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 16 \
  --request-out "$WORKDIR/request_good.json" \
  --signed-cert-out "$WORKDIR/signed_good.json" \
  --module-out "$WORKDIR/module_good.json" \
  --candidate-module "$WORKDIR/candidate_good.json" \
  --heldout-suites-dir "$HELDOUT_DIR" \
  --root "$WORKDIR"

echo "$WORKDIR"
