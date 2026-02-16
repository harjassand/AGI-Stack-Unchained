#!/usr/bin/env bash
set -euo pipefail
# Config materialization delegated to smoke_config.py to preserve sealed.episodes and avoid CDEL config round-trip.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"

export PYTHONPATH="$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

export ORCH_LLM_BACKEND="replay"
export ORCH_LLM_MAX_CALLS="3"

cdel_cmd() {
  "$PYTHON_BIN" -m cdel.cli "$@"
}

mkdir -p "$WORKDIR/sealed_suites"
HELDOUT_DIR="$(mktemp -d)"
: > "$WORKDIR/config.toml"

"$PYTHON_BIN" - <<PY
import json
from pathlib import Path

root = Path("$WORKDIR")
dev_path = root / "sealed_suites" / "pyut_dev.jsonl"
heldout_path = Path("$HELDOUT_DIR") / "pyut_heldout.jsonl"
# Use 64 episodes to stabilize heldout e-value over the default alpha schedule.
episodes = 64

def write_rows(path: Path, values: list[int]) -> None:
    rows = []
    for i, n in enumerate(values):
        rows.append({
            "episode": i,
            "task_id": "abs_int_v1",
            "fn_name": "abs_int",
            "signature": "def abs_int(x: int) -> int:",
            "tests": [{"args": [n], "expected": abs(n)}],
        })
    content = "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n"
    path.write_text(content, encoding="utf-8")

write_rows(dev_path, list(range(-32, 32)))
write_rows(heldout_path, list(range(100, 100 + episodes)))
PY

DEV_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$WORKDIR/sealed_suites/pyut_dev.jsonl")"
HELDOUT_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$HELDOUT_DIR/pyut_heldout.jsonl")"
mv "$WORKDIR/sealed_suites/pyut_dev.jsonl" "$WORKDIR/sealed_suites/${DEV_HASH}.jsonl"
mv "$HELDOUT_DIR/pyut_heldout.jsonl" "$HELDOUT_DIR/${HELDOUT_HASH}.jsonl"

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
from orchestrator.smoke_config import materialize_pyut_config

root = Path("$WORKDIR")
keypair = json.loads((root / "sealed_keypair.json").read_text(encoding="utf-8"))

materialize_pyut_config(
    out_path=root / "dev_config.toml",
    suite_hash="$DEV_HASH",
    suite_path=root / "sealed_suites" / f"$DEV_HASH.jsonl",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=64,
)
materialize_pyut_config(
    out_path=root / "heldout_config.toml",
    suite_hash="$HELDOUT_HASH",
    suite_path=Path("$HELDOUT_DIR") / f"$HELDOUT_HASH.jsonl",
    public_key=keypair["public_key"],
    key_id=keypair["key_id"],
    episodes=64,
)
PY

"$PYTHON_BIN" - <<PY
import json
from pathlib import Path

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
(root / "module_base.json").write_text(json.dumps(base, sort_keys=True) + "\n", encoding="utf-8")
PY

cdel_cmd --root "$WORKDIR" --config "$WORKDIR/heldout_config.toml" commit "$WORKDIR/module_base.json"

REPLAY_PATH="$WORKDIR/pyut_replay.jsonl"
"$PYTHON_BIN" - <<PY
import json
from pathlib import Path

from orchestrator.context_pack import ContextPackLimits, build_context_pack_v1
from orchestrator.domains.python_ut_v1 import load_domain
from orchestrator.ledger_view import LedgerView
from orchestrator.proposer.llm import ProposerLimits
from orchestrator.pyut_utils import python_source_payload
from orchestrator.retrieval import retrieve_context
from orchestrator.types import ContextBundle

root = Path("$WORKDIR")
ledger = LedgerView(root)
sig = ledger.get_symbol_signature("abs_int_base") or ledger.get_symbol_signature("abs_int_oracle")
type_norm = sig.type_norm if sig else "List[Int]"

bundle = ContextBundle(
    concept="py.abs_int",
    baseline_symbol="abs_int_base",
    oracle_symbol="abs_int_oracle",
    type_norm=type_norm,
    symbols=[],
)
context_symbols = retrieve_context(ledger=ledger, bundle=bundle, limit=5)
bundle = ContextBundle(
    concept=bundle.concept,
    baseline_symbol=bundle.baseline_symbol,
    oracle_symbol=bundle.oracle_symbol,
    type_norm=bundle.type_norm,
    symbols=context_symbols,
)

domain = load_domain(None)
limits = domain.proposer_limits or ProposerLimits(max_new_symbols=1, max_ast_nodes=2000, max_ast_depth=2000)
pack = build_context_pack_v1(
    root_dir=root,
    config_path=root / "dev_config.toml",
    concept=bundle.concept,
    baseline_symbol=bundle.baseline_symbol,
    oracle_symbol=bundle.oracle_symbol,
    context_symbols=bundle.symbols,
    counterexamples=[],
    rng_seed=0,
    limits=ContextPackLimits(
        max_new_symbols=limits.max_new_symbols,
        max_ast_nodes=limits.max_ast_nodes,
        max_ast_depth=limits.max_ast_depth,
        allow_primitives=limits.allow_primitives,
    ),
)
prompt = json.dumps(pack, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

payload = python_source_payload(
    name="abs_int_replay",
    source="def abs_int(x: int) -> int:\n    return x if x >= 0 else -x\n",
    concept="py.abs_int",
)
response = json.dumps(payload, sort_keys=True)

Path("$REPLAY_PATH").write_text(json.dumps({"prompt": prompt, "response": response}, sort_keys=True) + "\n", encoding="utf-8")
PY

export ORCH_LLM_REPLAY_PATH="$REPLAY_PATH"

RUN_DIR="$("$PYTHON_BIN" "$ROOT_DIR/scripts/run_orchestrator.py" \
  --root "$WORKDIR" \
  --domain python-ut-v1 \
  --dev-config "$WORKDIR/dev_config.toml" \
  --heldout-config "$WORKDIR/heldout_config.toml" \
  --heldout-suites-dir "$HELDOUT_DIR" \
  --seed-key "sealed-seed" \
  --min-dev-diff-sum 1 \
  --max-attempts 1 \
  --max-heldout-attempts 1 \
  --max-context-symbols 5 \
  --proposers llm \
  --runs-dir "$WORKDIR/orchestrator_runs")"

if ! find "$RUN_DIR/candidates" -name adoption.json | grep -q .; then
  "$PYTHON_BIN" - <<PY
import json
from pathlib import Path

manifest = Path("$RUN_DIR") / "manifest.json"
if not manifest.exists():
    raise SystemExit("ERROR: adoption missing and manifest not found")
data = json.loads(manifest.read_text(encoding="utf-8"))
reason = data.get("reason", "unknown")
raise SystemExit(f"ERROR: expected adoption output (reason={reason})")
PY
  exit 1
fi

echo "$RUN_DIR"
