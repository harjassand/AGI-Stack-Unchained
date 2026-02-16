#!/usr/bin/env bash
set -euo pipefail

run_dir="${1:-}"
if [[ -z "${run_dir}" ]]; then
  echo "usage: $0 <run_dir>" >&2
  exit 1
fi

if [[ ! -d "${run_dir}" ]]; then
  echo "run_dir not found: ${run_dir}" >&2
  exit 1
fi

grep -R --line-number --fixed-strings -e "CDEL_SEALED_PRIVKEY" -e "epoch_key_v1" -e "\"k_t\"" "${run_dir}" && {
  echo "sealing audit failed: secret markers found in run outputs" >&2
  exit 1
}

python3 - "${run_dir}" <<'PY'
import json
import sys
from pathlib import Path
from hashlib import sha256

run_dir = Path(sys.argv[1]).resolve()
epoch_commit = run_dir / "epoch_commit_v1.json"
learnability = run_dir / "diagnostics" / "learnability_report_v1.json"
if not epoch_commit.exists() or not learnability.exists():
    raise SystemExit("missing epoch_commit_v1.json or learnability_report_v1.json")

commit = json.loads(epoch_commit.read_text(encoding="utf-8"))
learn = json.loads(learnability.read_text(encoding="utf-8"))
commitment = commit.get("commitment")

def inst_hash(family_id, theta, commitment):
    payload = {
        "family_id": family_id,
        "theta": theta,
        "epoch_commitment": commitment,
        "dsl_version": 1,
    }
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + sha256(canon).hexdigest()

family_id = learn.get("family_id")
gate_instances = learn.get("gate_instances", [])
if not gate_instances:
    raise SystemExit("no gate instances found")

for inst in gate_instances:
    expected = inst_hash(family_id, inst.get("theta"), commitment)
    if inst.get("inst_hash") != expected:
        raise SystemExit("gate instance inst_hash mismatch")

tampered = "sha256:" + "0" * 64 if commitment != "sha256:" + "0" * 64 else "sha256:" + "1" * 64
tamper_mismatch = False
for inst in gate_instances:
    expected = inst_hash(family_id, inst.get("theta"), tampered)
    if inst.get("inst_hash") != expected:
        tamper_mismatch = True
        break
if not tamper_mismatch:
    raise SystemExit("tamper test failed: inst_hash unchanged under commitment change")
PY

python3 -m pytest -q ../Extension-1/caoe_v1/tests/test_no_heldout_read_v1_5r.py

echo "sealing audit passed"
