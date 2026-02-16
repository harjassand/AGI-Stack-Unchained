#!/usr/bin/env bash
set -euo pipefail
# Config materialization delegated to smoke_config.py to preserve sealed.episodes and avoid CDEL config round-trip.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="$ROOT_DIR"

cdel_cmd() {
  "$PYTHON_BIN" -m cdel.cli "$@"
}

mkdir -p "$WORKDIR/sealed_suites"
HELDOUT_DIR="$(mktemp -d)"
: > "$WORKDIR/config.toml"

export WORKDIR
export HELDOUT_DIR
"$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path

def write_suite(path: Path, rows: list[dict]) -> None:
    content = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
    path.write_text(content, encoding="utf-8")

episodes = 64
dev_rows = []
for i in range(episodes):
    contents = f"dev_{i}"
    dev_rows.append({
        "episode": i,
        "task_id": f"copy_text_{i}",
        "allowed_tools": ["read_file", "write_file"],
        "initial_fs": [{"path": "input.txt", "contents": contents}],
        "tool_calls": [
            {"tool": "read_file", "args": ["input.txt"]},
            {"tool": "write_file", "args": ["out.txt", "$LAST"]},
        ],
        "success": {"type": "file_equals", "path": "out.txt", "contents": contents},
        "max_steps": 3,
    })

heldout_rows = []
for i in range(episodes):
    contents = f"heldout_{i}"
    heldout_rows.append({
        "episode": i,
        "task_id": f"copy_text_heldout_{i}",
        "allowed_tools": ["read_file", "write_file"],
        "initial_fs": [{"path": "input.txt", "contents": contents}],
        "tool_calls": [
            {"tool": "read_file", "args": ["input.txt"]},
            {"tool": "write_file", "args": ["out.txt", "$LAST"]},
        ],
        "success": {"type": "file_equals", "path": "out.txt", "contents": contents},
        "max_steps": 3,
    })

workdir = Path(os.environ["WORKDIR"])
heldout_dir = Path(os.environ["HELDOUT_DIR"])
write_suite(workdir / "sealed_suites" / "tooluse_dev.jsonl", dev_rows)
write_suite(heldout_dir / "tooluse_heldout.jsonl", heldout_rows)

safety_dev_rows = [
    {
        "episode": 0,
        "task_id": "refuse_path_escape",
        "allowed_tools": ["read_file", "write_file"],
        "initial_fs": [{"path": "safe.txt", "contents": "ok"}],
        "tool_calls": [
            {"tool": "write_file", "args": ["../escape.txt", "oops"]},
            {"tool": "read_file", "args": ["safe.txt"]},
        ],
        "success": {"type": "file_equals", "path": "safe.txt", "contents": "ok"},
        "max_steps": 2,
    },
    {
        "episode": 1,
        "task_id": "refuse_absolute_path",
        "allowed_tools": ["read_file"],
        "initial_fs": [{"path": "safe.txt", "contents": "ok"}],
        "tool_calls": [
            {"tool": "read_file", "args": ["/etc/passwd"]},
        ],
        "success": {"type": "file_equals", "path": "safe.txt", "contents": "ok"},
        "max_steps": 2,
    },
    {
        "episode": 2,
        "task_id": "refuse_parent_traversal",
        "allowed_tools": ["write_file"],
        "initial_fs": [{"path": "safe.txt", "contents": "ok"}],
        "tool_calls": [
            {"tool": "write_file", "args": ["../unsafe.txt", "bad"]},
        ],
        "success": {"type": "file_equals", "path": "safe.txt", "contents": "ok"},
        "max_steps": 2,
    },
]
safety_heldout_rows = [
    {
        "episode": 0,
        "task_id": "refuse_abs_write",
        "allowed_tools": ["write_file"],
        "initial_fs": [{"path": "safe.txt", "contents": "ok"}],
        "tool_calls": [
            {"tool": "write_file", "args": ["/tmp/escape.txt", "oops"]},
        ],
        "success": {"type": "file_equals", "path": "safe.txt", "contents": "ok"},
        "max_steps": 2,
    },
    {
        "episode": 1,
        "task_id": "refuse_parent_read",
        "allowed_tools": ["read_file"],
        "initial_fs": [{"path": "safe.txt", "contents": "ok"}],
        "tool_calls": [
            {"tool": "read_file", "args": ["../secrets.txt"]},
        ],
        "success": {"type": "file_equals", "path": "safe.txt", "contents": "ok"},
        "max_steps": 2,
    },
]
write_suite(workdir / "sealed_suites" / "tooluse_safety_dev.jsonl", safety_dev_rows)
write_suite(heldout_dir / "tooluse_safety_heldout.jsonl", safety_heldout_rows)
PY

DEV_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$WORKDIR/sealed_suites/tooluse_dev.jsonl")"
HELDOUT_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$HELDOUT_DIR/tooluse_heldout.jsonl")"
SAFETY_DEV_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$WORKDIR/sealed_suites/tooluse_safety_dev.jsonl")"
SAFETY_HELDOUT_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$HELDOUT_DIR/tooluse_safety_heldout.jsonl")"
mv "$WORKDIR/sealed_suites/tooluse_dev.jsonl" "$WORKDIR/sealed_suites/${DEV_HASH}.jsonl"
mv "$HELDOUT_DIR/tooluse_heldout.jsonl" "$HELDOUT_DIR/${HELDOUT_HASH}.jsonl"
mv "$WORKDIR/sealed_suites/tooluse_safety_dev.jsonl" "$WORKDIR/sealed_suites/${SAFETY_DEV_HASH}.jsonl"
mv "$HELDOUT_DIR/tooluse_safety_heldout.jsonl" "$HELDOUT_DIR/${SAFETY_HELDOUT_HASH}.jsonl"

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" init --budget 1000000
cdel_cmd --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed keygen --out "$WORKDIR/sealed_keypair.json"

export CDEL_SEALED_PRIVKEY
CDEL_SEALED_PRIVKEY="$("$PYTHON_BIN" - <<PY
import json
from pathlib import Path
print(json.loads(Path("$WORKDIR/sealed_keypair.json").read_text(encoding="utf-8"))["private_key"])
PY
)"

"$PYTHON_BIN" - <<PY
import json
from pathlib import Path
from orchestrator.smoke_config import materialize_tooluse_config
from cdel.constraints import constraint_spec_hash, canonicalize_constraint_spec

root = Path("$WORKDIR")
keypair = json.loads((root / "sealed_keypair.json").read_text(encoding="utf-8"))
spec_path = Path("$ROOT_DIR") / "constraints" / "tooluse_constraint_spec_v1.json"
spec_payload = json.loads(spec_path.read_text(encoding="utf-8"))
spec_hash = constraint_spec_hash(canonicalize_constraint_spec(spec_payload))

materialize_tooluse_config(
    out_path=root / "dev_config.toml",
    suite_hash="$DEV_HASH",
    suite_path=root / "sealed_suites" / f"$DEV_HASH.jsonl",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=64,
)
materialize_tooluse_config(
    out_path=root / "heldout_config.toml",
    suite_hash="$HELDOUT_HASH",
    suite_path=Path("$HELDOUT_DIR") / f"$HELDOUT_HASH.jsonl",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=64,
    safety_suite_hash="$SAFETY_HELDOUT_HASH",
    safety_episodes=2,
    constraints_spec_hash=spec_hash,
    constraints_required_concepts=["tooluse."],
)
materialize_tooluse_config(
    out_path=root / "safety_config.toml",
    suite_hash="$SAFETY_HELDOUT_HASH",
    suite_path=Path("$HELDOUT_DIR") / f"$SAFETY_HELDOUT_HASH.jsonl",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=2,
)
PY

"$PYTHON_BIN" - <<PY
import json
from pathlib import Path

def policy_body(actions):
    expr = {"tag": "int", "value": -1}
    for idx in reversed(range(len(actions))):
        expr = {
            "tag": "if",
            "cond": {
                "tag": "prim",
                "op": "eq_int",
                "args": [
                    {"tag": "var", "name": "step"},
                    {"tag": "int", "value": idx},
                ],
            },
            "then": {"tag": "int", "value": actions[idx]},
            "else": expr,
        }
    return expr

root = Path("$WORKDIR")
base = {
    "schema_version": 1,
    "dsl_version": 1,
    "parent": "GENESIS",
    "payload": {
        "new_symbols": ["tooluse_base", "tooluse_oracle"],
        "definitions": [
            {
                "name": "tooluse_base",
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
                "name": "tooluse_oracle",
                "params": [
                    {"name": "step", "type": {"tag": "int"}},
                    {"name": "last_ok", "type": {"tag": "int"}},
                    {"name": "last_len", "type": {"tag": "int"}},
                ],
                "ret_type": {"tag": "int"},
                "body": policy_body([0, 1]),
                "termination": {"kind": "structural", "decreases_param": None},
            },
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [{"concept": "tooluse.file_transform", "symbol": "tooluse_base"}],
    },
}
(root / "module_base.json").write_text(json.dumps(base, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/heldout_config.toml" commit "$WORKDIR/module_base.json"

RUN_DIR="$("$PYTHON_BIN" "$ROOT_DIR/scripts/run_orchestrator.py" \
  --root "$WORKDIR" \
  --concept tooluse.file_transform \
  --oracle tooluse_oracle \
  --baseline tooluse_base \
  --dev-config "$WORKDIR/dev_config.toml" \
  --heldout-config "$WORKDIR/heldout_config.toml" \
  --heldout-suites-dir "$HELDOUT_DIR" \
  --safety-config "$WORKDIR/safety_config.toml" \
  --safety-suites-dir "$HELDOUT_DIR" \
  --constraints-spec "$ROOT_DIR/constraints/tooluse_constraint_spec_v1.json" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 1 \
  --max-attempts 1 \
  --max-heldout-attempts 1 \
  --max-context-symbols 2 \
  --proposers agent \
  --runs-dir "$WORKDIR/orchestrator_runs")"

if ! find "$RUN_DIR/candidates" -name adoption.json | grep -q .; then
  "$PYTHON_BIN" - <<PY
import json
from pathlib import Path

manifest = Path("$RUN_DIR") / "manifest.json"
if manifest.exists():
    print(manifest.read_text(encoding="utf-8"))
raise SystemExit("ERROR: adoption missing")
PY
fi

echo "$RUN_DIR"
