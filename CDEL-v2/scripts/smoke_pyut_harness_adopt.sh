#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"
DEV_HASH="8bc574fc9c05218aaa7d24963a4f03a97c9cfa07031fae30cdeb07f37898370c"
HELDOUT_HASH="490227575f49b06c8dfcf1b2d783e0cdf086cbd2a20bedc441a8a083fcb5f13a"

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
for i, n in enumerate(range(10, 42)):
    rows.append({
        "episode": i,
        "task_id": "abs_int_v1",
        "fn_name": "abs_int",
        "signature": "def abs_int(x: int) -> int:",
        "tests": [{"args": [n], "expected": abs(n)}],
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

materialize("$ROOT_DIR/configs/sealed_pyut_dev.toml", "dev_config.toml")
materialize("$ROOT_DIR/configs/sealed_pyut_heldout.toml", "heldout_config.toml")
PY

python3 - <<PY
from pathlib import Path
import json

def list_literal(values):
    term = {"tag": "nil"}
    for value in reversed(values):
        term = {"tag": "cons", "head": {"tag": "int", "value": value}, "tail": term}
    return term

def code_def(name, source):
    data = source.encode("ascii")
    return {
        "name": name,
        "params": [],
        "ret_type": {"tag": "list", "of": {"tag": "int"}},
        "body": list_literal(list(data)),
        "termination": {"kind": "structural", "decreases_param": None},
    }

root = Path("$WORKDIR")
base = {
    "schema_version": 1,
    "dsl_version": 1,
    "parent": "GENESIS",
    "payload": {
        "new_symbols": ["abs_int_base", "abs_int_oracle"],
        "definitions": [
            code_def("abs_int_base", "def abs_int(x: int) -> int:\n    return 0\n"),
            code_def("abs_int_oracle", "def abs_int(x: int) -> int:\n    return x if x >= 0 else -x\n"),
        ],
        "declared_deps": [],
        "specs": [],
        "concepts": [],
    },
}
(root / "module_base.json").write_text(json.dumps(base, sort_keys=True) + "\\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/heldout_config.toml" commit "$WORKDIR/module_base.json"

python3 - <<PY
from pathlib import Path
import json

def list_literal(values):
    term = {"tag": "nil"}
    for value in reversed(values):
        term = {"tag": "cons", "head": {"tag": "int", "value": value}, "tail": term}
    return term

def code_def(name, source):
    data = source.encode("ascii")
    return {
        "name": name,
        "params": [],
        "ret_type": {"tag": "list", "of": {"tag": "int"}},
        "body": list_literal(list(data)),
        "termination": {"kind": "structural", "decreases_param": None},
    }

root = Path("$WORKDIR")
overfit_src = (
    "def abs_int(x: int) -> int:\n"
    "    if -3 <= x <= 3:\n"
    "        return x if x >= 0 else -x\n"
    "    return 0\n"
)
overfit = {
    "new_symbols": ["abs_int_overfit"],
    "definitions": [code_def("abs_int_overfit", overfit_src)],
    "declared_deps": [],
    "specs": [],
    "concepts": [{"concept": "py.abs_int", "symbol": "abs_int_overfit"}],
}
(root / "candidate_overfit.json").write_text(json.dumps(overfit, sort_keys=True) + "\\n", encoding="utf-8")

malicious = {
    "new_symbols": ["abs_int_malicious"],
    "definitions": [
        code_def("abs_int_malicious", "def abs_int(x: int) -> int:\\n    f = open('/etc/passwd', 'r')\\n    return 0\\n"),
    ],
    "declared_deps": [],
    "specs": [],
    "concepts": [{"concept": "py.abs_int", "symbol": "abs_int_malicious"}],
}
(root / "candidate_malicious.json").write_text(json.dumps(malicious, sort_keys=True) + "\\n", encoding="utf-8")

good = {
    "new_symbols": ["abs_int_good"],
    "definitions": [
        code_def("abs_int_good", "def abs_int(x: int) -> int:\n    return x if x >= 0 else -x\n"),
    ],
    "declared_deps": [],
    "specs": [],
    "concepts": [{"concept": "py.abs_int", "symbol": "abs_int_good"}],
}
(root / "candidate_good.json").write_text(json.dumps(good, sort_keys=True) + "\\n", encoding="utf-8")
PY

if python3 scripts/promote_candidate_dev_vs_heldout.py \
  --concept py.abs_int \
  --baseline abs_int_base \
  --candidate abs_int_malicious \
  --oracle abs_int_oracle \
  --dev-config "$WORKDIR/dev_config.toml" \
  --heldout-config "$WORKDIR/heldout_config.toml" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 8 \
  --request-out "$WORKDIR/request_malicious.json" \
  --signed-cert-out "$WORKDIR/signed_malicious.json" \
  --module-out "$WORKDIR/module_malicious.json" \
  --candidate-module "$WORKDIR/candidate_malicious.json" \
  --heldout-suites-dir "$HELDOUT_DIR" \
  --root "$WORKDIR"; then
  echo "ERROR: expected dev gating to fail for malicious candidate"
  exit 1
fi

if python3 scripts/promote_candidate_dev_vs_heldout.py \
  --concept py.abs_int \
  --baseline abs_int_base \
  --candidate abs_int_overfit \
  --oracle abs_int_oracle \
  --dev-config "$WORKDIR/dev_config.toml" \
  --heldout-config "$WORKDIR/heldout_config.toml" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 8 \
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
  --concept py.abs_int \
  --baseline abs_int_base \
  --candidate abs_int_good \
  --oracle abs_int_oracle \
  --dev-config "$WORKDIR/dev_config.toml" \
  --heldout-config "$WORKDIR/heldout_config.toml" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 8 \
  --request-out "$WORKDIR/request_good.json" \
  --signed-cert-out "$WORKDIR/signed_good.json" \
  --module-out "$WORKDIR/module_good.json" \
  --candidate-module "$WORKDIR/candidate_good.json" \
  --heldout-suites-dir "$HELDOUT_DIR" \
  --root "$WORKDIR"

echo "$WORKDIR"
