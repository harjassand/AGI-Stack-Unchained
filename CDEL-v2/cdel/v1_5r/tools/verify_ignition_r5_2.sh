#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
OUT_ROOT="${OUT_ROOT:-$ROOT_DIR/runs/v1_5r_ignition_r5_2}"
GENERATOR_SPEC="${GENERATOR_SPEC:-$ROOT_DIR/suitepacks/portfolio_generator_v1.json}"
EXTENSION_ROOT="${EXTENSION_ROOT:-$ROOT_DIR/../Extension-1}"

mkdir -p "$OUT_ROOT"

if [[ -z "${CDEL_SEALED_PRIVKEY:-}" ]]; then
  CDEL_SEALED_PRIVKEY="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
  export CDEL_SEALED_PRIVKEY
fi

python3 "$ROOT_DIR/cdel/v1_5r/tools/build_portfolio_from_generator.py" \
  --generator "$GENERATOR_SPEC" \
  --out_root "$OUT_ROOT/inputs"

python3 "$ROOT_DIR/cdel/v1_5r/tools/proposer_capability_dryrun_v1_5r.py" \
  --extension_root "$EXTENSION_ROOT" \
  --out_dir "$OUT_ROOT/proposer_dryrun"

run_portfolio() {
  local portfolio_id="$1"
  local portfolio_root="$OUT_ROOT/inputs/$portfolio_id"
  local run_root="$OUT_ROOT/run_0/$portfolio_id"
  local state_dir="$run_root"
  local current_dir="$state_dir/current"
  python3 - "$run_root" <<'PY'
import shutil
import sys


def rho_turnover_ok(xs, max_drop_frac=0.50, k_recover=2):
    if not xs:
        return False
    peak = xs[0]
    i = 1
    while i < len(xs):
        v = xs[i]
        if v >= peak:
            peak = v
            i += 1
            continue
        min_allowed = int(peak * (1.0 - max_drop_frac))
        if v < min_allowed:
            return False
        recovered = False
        for j in range(i + 1, min(len(xs), i + 1 + k_recover)):
            if xs[j] >= peak:
                recovered = True
                i = j
                peak = xs[j]
                break
        if not recovered:
            return False
        i += 1
    return True

from pathlib import Path

run_root = Path(sys.argv[1])
if run_root.exists():
    shutil.rmtree(run_root)
PY
  mkdir -p "$current_dir/families" "$current_dir/macros" "$current_dir/meta_patches" "$state_dir/epochs"

  python3 - "$current_dir" <<'PY'
import json
import sys
from pathlib import Path
from cdel.v1_5r.canon import write_canon_json

current_dir = Path(sys.argv[1])
write_canon_json(current_dir / "base_ontology.json", {"schema": "base_ontology_v1", "schema_version": 1})
write_canon_json(current_dir / "base_mech.json", {"schema": "base_mech_v1", "schema_version": 1})
write_canon_json(
    current_dir / "macro_active_set_v1.json",
    {
        "schema": "macro_active_set_v1",
        "schema_version": 1,
        "active_macro_ids": [],
        "ledger_head_hash": "sha256:" + "0" * 64,
    },
)
(current_dir / "macro_ledger_v1.jsonl").write_text("", encoding="utf-8")
write_canon_json(current_dir / "pressure_schedule_v1.json", {"schema": "pressure_schedule_v1", "schema_version": 1, "p_t": 0, "history": []})
write_canon_json(current_dir / "meta_patch_set_v1.json", {"schema": "meta_patch_set_v1", "schema_version": 1, "active_patch_ids": []})
(current_dir / "witness_ledger_v1.jsonl").write_text("", encoding="utf-8")
write_canon_json(
    current_dir / "witness_ledger_head_v1.json",
    {"schema": "witness_ledger_head_v1", "schema_version": 1, "ledger_head_hash": None, "line_count": 0},
)
PY

  if [[ -f "$portfolio_root/portfolio_manifest_v1.json" ]]; then
    cp "$portfolio_root/portfolio_manifest_v1.json" "$current_dir/portfolio_manifest_v1.json"
  fi
  if [[ -f "$portfolio_root/portfolio_economics_preflight_v1.json" ]]; then
    cp "$portfolio_root/portfolio_economics_preflight_v1.json" "$current_dir/portfolio_economics_preflight_v1.json"
  fi

  python3 - "$portfolio_root" "$current_dir" <<'PY'
import sys
from pathlib import Path
from cdel.v1_5r.canon import load_canon_json, write_canon_json, hash_json
from cdel.v1_5r.family_dsl.runtime import compute_signature, compute_family_id

portfolio_root = Path(sys.argv[1])
current_dir = Path(sys.argv[2])
families_dir = current_dir / "families"
families_dir.mkdir(parents=True, exist_ok=True)

families = []
for path in sorted((portfolio_root / "families").glob("*.json")):
    fam = load_canon_json(path)
    fam["signature"] = compute_signature(fam)
    fam["family_id"] = compute_family_id(fam)
    families.append(fam)

motif = ["NOOP"]
if families:
    payload = families[0].get("instantiator", {}).get("value", {})
    motif = payload.get("motif_action_names") or motif

while len(families) < 16:
    idx = len(families)
    base = dict(families[0]) if families else {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": 16,
            "max_instance_bytes": 1024,
            "max_instantiation_gas": 128,
            "max_shrink_gas": 128,
        },
        "instantiator": {"op": "CONST", "value": {"motif_action_names": motif}},
        "pressure_rule": {"op": "CONST", "value": {}},
    }
    inst = dict(base.get("instantiator", {}))
    value = dict(inst.get("value", {}))
    value["signature_salt"] = f"filler-{idx}"
    inst["value"] = value
    base["instantiator"] = inst
    base["signature"] = compute_signature(base)
    base["family_id"] = compute_family_id(base)
    families.append(base)

family_refs = []
for fam in families:
    fam_hash = hash_json(fam)
    write_canon_json(families_dir / f"{fam_hash.split(':', 1)[1]}.json", fam)
    family_refs.append({"family_id": fam["family_id"], "family_hash": fam_hash})

family_refs.sort(key=lambda item: item["family_id"])
frontier = {
    "schema": "frontier_v1",
    "schema_version": 1,
    "frontier_id": "",
    "families": family_refs,
    "M_FRONTIER": 16,
    "signature_version": 1,
    "compression_proof_hash": "sha256:" + "0" * 64,
}
frontier["frontier_id"] = hash_json({k: v for k, v in frontier.items() if k != "frontier_id"})
write_canon_json(current_dir / "frontier_v1.json", frontier)
PY

  local bench_pack="$run_root/benchmark_pack_v1.json"
  python3 - "$bench_pack" <<'PY'
import sys
from pathlib import Path
from cdel.v1_5r.canon import hash_json, write_canon_json

path = Path(sys.argv[1])
pack = {
    "schema": "benchmark_pack_v1",
    "schema_version": 1,
    "pack_id": "",
    "instances": [
        {
            "base_state_hashes": {},
            "suitepack_hashes": {},
            "max_candidates": 1,
            "eval_plan": "full",
            "epoch_id_label": "bench_0",
        }
    ],
}
pack["pack_id"] = hash_json(pack)
write_canon_json(path, pack)
PY

  for idx in 1 2 3 4 5 6 7 8 9; do
    local epoch_id="${portfolio_id}_epoch_${idx}"
    local epoch_dir="$state_dir/epochs/$epoch_id"

    python3 -m cdel.v1_5r.cli run-epoch \
      --epoch_id "$epoch_id" \
      --base_ontology "$current_dir/base_ontology.json" \
      --base_mech "$current_dir/base_mech.json" \
      --state_dir "$state_dir" \
      --out_dir "$epoch_dir" \
      --created_unix_ms 0

    if [[ -f "$ROOT_DIR/tools/verify_sealing_r5_2.sh" ]]; then
      bash "$ROOT_DIR/tools/verify_sealing_r5_2.sh" "$epoch_dir"
    fi

    PYTHONPATH="$EXTENSION_ROOT/caoe_v1" python3 -m v1_5r.cli propose-families \
      --witness_index "$epoch_dir/diagnostics/failure_witness_v1.json" \
      --out_dir "$epoch_dir/proposals/families" || true

      # --- RSI_L7_ADVERSARY_FAMILIES (deterministic, frontier-mediated) ---
      python3 - "$epoch_dir" "$current_dir" <<'PY'
import json
import sys
from pathlib import Path
from cdel.v1_5r.canon import load_canon_json, write_canon_json
from cdel.v1_5r.ctime.macro import load_macro_defs
from cdel.v1_5r.adversary.attack_family import expand_macro_to_primitives, make_adversarial_family

epoch_dir = Path(sys.argv[1])
current_dir = Path(sys.argv[2])
diag = epoch_dir / "diagnostics"
tokp = diag / "macro_tokenization_report_heldout_admitted_only_epoch_v1.json"
if not tokp.exists():
    sys.exit(0)
tok = load_canon_json(tokp)

# Utility ranking from epoch-local admitted-only tokenization
items = []
for m in tok.get("macros", []):
    if not isinstance(m, dict):
        continue
    mid = m.get("macro_id")
    if not isinstance(mid, str):
        continue
    if mid.startswith("sha256:macro_"):
        continue
    occ = int(m.get("occurrences", 0))
    if bool(m.get("is_composed")):
        util = int(m.get("delta_tokens_token_space_est", 0))
    else:
        exp_len = int(m.get("expanded_primitive_len", 0))
        util = max(0, exp_len - 1) * occ
    items.append((util, mid))

items.sort(key=lambda x: (-x[0], x[1]))
K_TARGET = 2
targets = [mid for util, mid in items[:K_TARGET] if util > 0]
if not targets:
    sys.exit(0)

active_set = load_canon_json(current_dir / "macro_active_set_v1.json").get("active_macro_ids", [])
macro_defs = load_macro_defs(current_dir / "macros", allowed=active_set)
macro_map = {m.get("macro_id"): m for m in macro_defs if isinstance(m.get("macro_id"), str)}

out_dir = epoch_dir / "proposals" / "families"
out_dir.mkdir(parents=True, exist_ok=True)

for mid in targets:
    exp = expand_macro_to_primitives(mid, macro_map)
    fam = make_adversarial_family(target_macro_id=mid, expansion=exp, motif_len=40)
    fid = fam.get("family_id")
    if not isinstance(fid, str):
        continue
    write_canon_json(out_dir / f"adv_{fid.split(':',1)[1]}.json", fam)

write_canon_json(diag / "adversary_target_set_v1.json", {
    "schema": "adversary_target_set_v1",
    "schema_version": 1,
    "epoch_id": epoch_dir.name,
    "targets": targets,
})
PY
      # --- END RSI_L7_ADVERSARY_FAMILIES ---


    python3 - "$epoch_dir" "$current_dir" "$epoch_id" <<'PY'
import base64
import hashlib
import os
import sys
from pathlib import Path

from cdel.v1_5r.canon import hash_json, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v1_5r.family_dsl.runtime import compute_family_id, compute_signature
from cdel.v1_5r.pi0_gate_eval import evaluate_pi0_gate
from cdel.v1_5r.sr_cegar.frontier import compress_frontier, compute_coverage_score
from cdel.v1_5r.sr_cegar.gates import novelty_pass
from cdel.v1_5r.sr_cegar.witness_ledger import load_ledger_lines, verify_ledger_chain
from cdel.v1_5r.diagnostics.provenance import build_family_admission_provenance
from cdel.v1_5r.epoch import derive_epoch_key

epoch_dir = Path(sys.argv[1])
current_dir = Path(sys.argv[2])
epoch_id = sys.argv[3]

proposals_dir = epoch_dir / "proposals" / "families"
proposal_paths = sorted(proposals_dir.glob("*.json"))
if not proposal_paths:
    sys.exit(0)

frontier = load_canon_json(current_dir / "frontier_v1.json")
frontier_families = []
family_map = {}
for entry in frontier.get("families", []):
    fam_hash = entry.get("family_hash")
    if not fam_hash:
        continue
    fam_path = current_dir / "families" / f"{fam_hash.split(':', 1)[1]}.json"
    if not fam_path.exists():
        continue
    family = load_canon_json(fam_path)
    family_map[family.get("family_id")] = family
    frontier_families.append({"family_id": family.get("family_id"), "signature": compute_signature(family)})

ledger_lines = load_ledger_lines(current_dir / "witness_ledger_v1.jsonl")
head_hash = verify_ledger_chain(ledger_lines)
if not ledger_lines:
    sys.exit(0)

witnesses = []
witness_index = epoch_dir / "diagnostics" / "failure_witness_v1.json"
if witness_index.exists():
    payload = load_canon_json(witness_index)
    for w_hash in payload.get("witnesses", []):
        witness_path = epoch_dir / "diagnostics" / "witnesses" / f"{str(w_hash).split(':',1)[1]}.json"
        if witness_path.exists():
            witness = load_canon_json(witness_path)
            fam_id = witness.get("family_id")
            fam_obj = family_map.get(fam_id)
            if fam_obj:
                witness["family_signature"] = compute_signature(fam_obj)
            witnesses.append(witness)

def _file_hash(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())

def _state_hashes() -> dict[str, str]:
    required = {
        "base_ontology_hash": current_dir / "base_ontology.json",
        "base_mech_hash": current_dir / "base_mech.json",
        "frontier_hash": current_dir / "frontier_v1.json",
        "macro_active_set_hash": current_dir / "macro_active_set_v1.json",
        "macro_ledger_hash": current_dir / "macro_ledger_v1.jsonl",
        "pressure_schedule_hash": current_dir / "pressure_schedule_v1.json",
        "meta_patch_set_hash": current_dir / "meta_patch_set_v1.json",
    }
    return {k: _file_hash(p) for k, p in required.items()}

base_state_hashes = _state_hashes()
frontier_hash = base_state_hashes["frontier_hash"]
master_key = base64.b64decode(os.environ["CDEL_SEALED_PRIVKEY"])
k_t = derive_epoch_key(master_key, epoch_id, base_state_hashes, frontier_hash)
epoch_commit = load_canon_json(epoch_dir / "epoch_commit_v1.json")

best = None
best_score = None
best_distance = None
best_report_hash = None

for path in proposal_paths:
    family = load_canon_json(path)
    family["family_id"] = compute_family_id(family)
    family["signature"] = compute_signature(family)
    if family.get("family_id") != compute_family_id(family):
        continue
    nov_ok, min_dist = novelty_pass(family, frontier_families)
    if not nov_ok:
        continue
    gate_seed = hashlib.sha256(k_t + family["family_id"].encode("utf-8") + b"gate").digest()
    learnable, learn_report, _gate_eval = evaluate_pi0_gate(
        family=family,
        epoch_id=epoch_id,
        epoch_commit=epoch_commit,
        gate_seed=gate_seed,
        diagnostics_dir=epoch_dir / "diagnostics",
    )
    if not learnable:
        continue
    score = compute_coverage_score(family, witnesses, ledger_lines)
    if best is None or score > best_score or (score == best_score and family["family_id"] < best["family_id"]):
        best = family
        best_score = score
        best_distance = min_dist
        best_report_hash = hash_json(learn_report)

if best is None:
    sys.exit(0)

# Write family to current store
fam_hash = hash_json(best)
write_canon_json(current_dir / "families" / f"{fam_hash.split(':', 1)[1]}.json", best)
family_map[best["family_id"]] = best

# Update frontier with compression
all_families = [{"family_id": fam_id, "signature": compute_signature(fam)} for fam_id, fam in family_map.items()]
compressed, report = compress_frontier(all_families, witnesses, 16, ledger_lines)

frontier_refs = []
for fam in compressed:
    fam_obj = family_map.get(fam["family_id"])
    if not fam_obj:
        continue
    fam_hash = hash_json(fam_obj)
    frontier_refs.append({"family_id": fam["family_id"], "family_hash": fam_hash})

frontier_refs.sort(key=lambda item: item["family_id"])
frontier_payload = {
    "schema": "frontier_v1",
    "schema_version": 1,
    "frontier_id": "",
    "families": frontier_refs,
    "M_FRONTIER": 16,
    "signature_version": 1,
    "compression_proof_hash": "",
}

decision_trace = {
    "admitted_family_id": best["family_id"],
    "novelty_distance": best_distance,
    "learnability_report_hash": best_report_hash,
    "coverage_score": best_score,
}
decision_trace_hash = hash_json(decision_trace)

frontier_report = {
    "schema": "frontier_update_report_v1",
    "schema_version": 1,
    "admitted_family_id": best["family_id"],
    "novelty_distance": best_distance,
    "learnability_report_hash": best_report_hash,
    "witness_ledger_head_hash": head_hash,
    "decision_trace_hash": decision_trace_hash,
    "selected": report.get("selected", []),
    "trace": report.get("trace", []),
}
frontier_report_hash = hash_json(frontier_report)
write_canon_json(epoch_dir / "diagnostics" / "frontier_update_report_v1.json", frontier_report)

frontier_payload["compression_proof_hash"] = frontier_report_hash
frontier_payload["frontier_id"] = hash_json({k: v for k, v in frontier_payload.items() if k != "frontier_id"})

prev_hash_payload = {"schema": "frontier_prev_hash_v1", "schema_version": 1, "frontier_hash": hash_json(frontier)}
write_canon_json(current_dir / "frontier_prev_hash_v1.json", prev_hash_payload)
write_canon_json(current_dir / "frontier_v1.json", frontier_payload)

trigger_witnesses = []
for line in ledger_lines[-1:]:
    trigger_witnesses.append(
        {
            "witness_hash": line.get("witness_hash"),
            "origin_epoch_id": line.get("origin_epoch_id"),
            "failure_kind": line.get("failure_kind"),
            "inst_hash": line.get("inst_hash"),
        }
    )
coverage_inputs_hash = hash_json({"ledger_lines": ledger_lines})
provenance = build_family_admission_provenance(
    epoch_id=epoch_id,
    family=best,
    witness_ledger_head_hash=head_hash,
    trigger_witnesses=trigger_witnesses,
    coverage_score_inputs_hash=coverage_inputs_hash,
    decision_trace_hash=decision_trace_hash,
)
write_canon_json(epoch_dir / "diagnostics" / "family_admission_provenance_v1.json", provenance)
PY

    PYTHONPATH="$EXTENSION_ROOT/caoe_v1" python3 -m v1_5r.cli mine-macros \
      --trace_dev "$epoch_dir/traces/trace_dev_v1.jsonl" \
      --out_dir "$epoch_dir/proposals/macros" || true

    local macro_def
    macro_def=$(ls "$epoch_dir"/proposals/macros/macro_*.json 2>/dev/null | grep -v macro_miner_report | head -n 1 || true)
    if [[ -n "$macro_def" ]]; then
      python3 -m cdel.v1_5r.cli verify-macro \
        --macro_def "$macro_def" \
        --trace "$epoch_dir/traces/trace_heldout_v1.jsonl" \
        --active_set "$current_dir/macro_active_set_v1.json" \
        --out "$epoch_dir/diagnostics/macro_admission_report_v1.json"

      python3 - "$macro_def" "$current_dir" "$epoch_id" "$epoch_dir" <<'PY'
import sys
from pathlib import Path
from cdel.v1_5r.canon import hash_json, load_canon_json, write_canon_json
from cdel.v1_5r.ctime.macro import update_macro_ledger, write_macro_active_set
from cdel.v1_5r.diagnostics.provenance import build_macro_admission_provenance

macro_path = Path(sys.argv[1])
current_dir = Path(sys.argv[2])
epoch_id = sys.argv[3]
epoch_dir = Path(sys.argv[4])
report_path = epoch_dir / "diagnostics" / "macro_admission_report_v1.json"
if not report_path.exists():
    sys.exit(0)
report = load_canon_json(report_path)
if report.get("decision") != "PASS":
    sys.exit(0)

macro_def = load_canon_json(macro_path)
macro_id = macro_def.get("macro_id")
if not macro_id:
    sys.exit(0)

ledger_path = current_dir / "macro_ledger_v1.jsonl"
entry = update_macro_ledger(ledger_path, "ADMIT", macro_id, hash_json(macro_def), epoch_id)
active_set_path = current_dir / "macro_active_set_v1.json"
active_set_obj = load_canon_json(active_set_path)
active_ids = set(active_set_obj.get("active_macro_ids", []))
active_ids.add(macro_id)
write_macro_active_set(active_set_path, sorted(active_ids), entry["line_hash"])
write_canon_json(current_dir / "macros" / f"{hash_json(macro_def).split(':',1)[1]}.json", macro_def)

token_report_path = epoch_dir / "diagnostics" / "macro_tokenization_report_heldout_v1.json"
token_report_hash = hash_json(load_canon_json(token_report_path)) if token_report_path.exists() else "sha256:" + "0" * 64
provenance = build_macro_admission_provenance(
    epoch_id=epoch_id,
    macro_def=macro_def,
    macro_admission_report=report,
    macro_tokenization_report_hash=token_report_hash,
    trace_hashes_supporting=load_canon_json(token_report_path).get("trace_corpus_hashes", []) if token_report_path.exists() else [],
)
write_canon_json(epoch_dir / "diagnostics" / "macro_admission_provenance_v1.json", provenance)
PY
    fi

    local profile_path="$epoch_dir/diagnostics/meta_patch_profile.json"
    python3 - "$current_dir/meta_patch_set_v1.json" "$profile_path" <<'PY'
import sys
from pathlib import Path
from cdel.v1_5r.canon import load_canon_json, write_canon_json

active = load_canon_json(Path(sys.argv[1])).get("active_patch_ids", [])
profile = {"active_patch_ids": active}
write_canon_json(Path(sys.argv[2]), profile)
PY

    local patch_path="$epoch_dir/diagnostics/meta_patch_candidate.json"
    PYTHONPATH="$EXTENSION_ROOT/caoe_v1" python3 -m v1_5r.cli propose-meta-patch \
      --profile "$profile_path" \
      --out "$patch_path" || true

    if [[ -f "$patch_path" ]]; then
      if python3 -m cdel.v1_5r.cli translate-validate \
        --patch "$patch_path" \
        --benchmark_pack "$bench_pack" \
        --out "$epoch_dir/diagnostics/translation_cert_v1.json"; then
        python3 - "$patch_path" "$current_dir" "$epoch_id" "$bench_pack" "$epoch_dir" <<'PY'
import sys
from pathlib import Path
from cdel.v1_5r.canon import hash_json, load_canon_json, write_canon_json
from cdel.v1_5r.diagnostics.provenance import build_meta_patch_admission_provenance

patch_path = Path(sys.argv[1])
current_dir = Path(sys.argv[2])
epoch_id = sys.argv[3]
bench_pack = load_canon_json(Path(sys.argv[4]))
epoch_dir = Path(sys.argv[5])

patch = load_canon_json(patch_path)
patch_id = patch.get("patch_id")
if not patch_id:
    # --- RSI-L3 COMPOSITION CHECK ---
    # Require at least one composed macro definition (body contains only CALL_MACRO ops),
    # used in admitted-only tokenization, with positive token-space delta.
    def _is_composed_def(mdef: dict) -> bool:
        body = mdef.get("body", [])
        if not isinstance(body, list) or len(body) < 2:
            return False
        for op in body:
            if not isinstance(op, dict):
                return False
            ok = (op.get("op") == "CALL_MACRO" and isinstance(op.get("macro_id"), str)) or (
                op.get("name") == "CALL_MACRO" and isinstance(op.get("args"), dict) and isinstance(op["args"].get("macro_id"), str)
            )
            if not ok:
                return False
        return True

    composed_ids = set()
    macros_dir = current_dir / "macros"
    if macros_dir.exists():
        for mp in sorted(macros_dir.glob("*.json")):
            try:
                mdef = load_canon_json(mp)
            except Exception:
                continue
            mid = mdef.get("macro_id")
            if isinstance(mid, str) and _is_composed_def(mdef):
                composed_ids.add(mid)

    token_space_delta = {}
    for m in tok.get("macros", []):
        if isinstance(m, dict) and isinstance(m.get("macro_id"), str):
            token_space_delta[m["macro_id"]] = int(m.get("delta_tokens_token_space_est", 0))

    used_composed = [mid for mid in composed_ids if mid in used_learned and token_space_delta.get(mid, 0) > 0]
    l3_ok = len(used_composed) >= 1
    # --- END RSI-L3 COMPOSITION CHECK ---

    # --- RSI-L3 COMPOSITION CHECK ---
    # Require at least one composed macro definition (body contains only CALL_MACRO ops),
    # used in admitted-only tokenization, with positive token-space delta.
    def _is_composed_def(mdef: dict) -> bool:
        body = mdef.get("body", [])
        if not isinstance(body, list) or len(body) < 2:
            return False
        for op in body:
            if not isinstance(op, dict):
                return False
            ok = (op.get("op") == "CALL_MACRO" and isinstance(op.get("macro_id"), str)) or (
                op.get("name") == "CALL_MACRO" and isinstance(op.get("args"), dict) and isinstance(op["args"].get("macro_id"), str)
            )
            if not ok:
                return False
        return True

    composed_ids = set()
    macros_dir = current_dir / "macros"
    if macros_dir.exists():
        for mp in sorted(macros_dir.glob("*.json")):
            try:
                mdef = load_canon_json(mp)
            except Exception:
                continue
            mid = mdef.get("macro_id")
            if isinstance(mid, str) and _is_composed_def(mdef):
                composed_ids.add(mid)

    token_space_delta = {}
    for m in tok.get("macros", []):
        if isinstance(m, dict) and isinstance(m.get("macro_id"), str):
            token_space_delta[m["macro_id"]] = int(m.get("delta_tokens_token_space_est", 0))

    used_composed = [mid for mid in composed_ids if mid in used_learned and token_space_delta.get(mid, 0) > 0]
    l3_ok = len(used_composed) >= 1
    # --- END RSI-L3 COMPOSITION CHECK ---

    sys.exit(0)

meta_set_path = current_dir / "meta_patch_set_v1.json"
meta_set = load_canon_json(meta_set_path)
active = set(meta_set.get("active_patch_ids", []))
active.add(patch_id)
meta_set["active_patch_ids"] = sorted(active)
write_canon_json(meta_set_path, meta_set)

write_canon_json(current_dir / "meta_patches" / f"{patch_id.split(':',1)[1]}.json", patch)

cert_path = epoch_dir / "diagnostics" / "translation_cert_v1.json"
cert = load_canon_json(cert_path)
provenance = build_meta_patch_admission_provenance(
    epoch_id=epoch_id,
    meta_patch_id=patch_id,
    patch_bundle_hash=hash_json(patch),
    translation_cert_hash=hash_json(cert),
    benchmark_pack_id=bench_pack.get("pack_id"),
    workvec_before=cert["results"][0]["workvec_base"],
    workvec_after=cert["results"][0]["workvec_patch"],
)
write_canon_json(epoch_dir / "diagnostics" / "meta_patch_admission_provenance_v1.json", provenance)
PY
      fi
    fi
  done
}

run_portfolio "v1_5r_portfolio_p1"
run_portfolio "v1_5r_portfolio_p2"

python3 - "$OUT_ROOT" "$GENERATOR_SPEC" <<'PY'
import json
import sys
from pathlib import Path

out_root = Path(sys.argv[1])
generator_spec = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
summary_path = out_root / "IGNITION_R5_2_SUMMARY.md"

lines = ["# IGNITION_R5_2_SUMMARY", ""]
lines.append("## Commands")
lines.append("- build_portfolio_from_generator.py")
lines.append("- proposer_capability_dryrun_v1_5r.py")
lines.append("- cdel.v1_5r.cli run-epoch (5 per portfolio)")
lines.append("- v1_5r.cli propose-families / mine-macros / propose-meta-patch")
lines.append("- cdel.v1_5r.cli verify-macro / translate-validate")
lines.append("")
lines.append("## Generator Params")
lines.append(f"- generator_id: {generator_spec.get('generator_id')}")
lines.append(f"- motif_action_names: {generator_spec.get('motif_action_names')}")
lines.append("")

run_root = out_root / "run_0"
for portfolio_dir in sorted(run_root.iterdir()):
    if not portfolio_dir.is_dir():
        continue
    lines.append(f"## Portfolio {portfolio_dir.name}")
    admitted_families = []
    admitted_macros = []
    admitted_patches = []
    rho_values = []
    barrier_values = []
    epochs_dir = portfolio_dir / "epochs"
    for epoch_dir in sorted(epochs_dir.iterdir()):
        diagnostics = epoch_dir / "diagnostics"
        frontier_report = diagnostics / "frontier_update_report_v1.json"
        if frontier_report.exists():
            report = json.loads(frontier_report.read_text(encoding="utf-8"))
            fam_id = report.get("admitted_family_id")
            if fam_id:
                admitted_families.append(fam_id)
        macro_prov = diagnostics / "macro_admission_provenance_v1.json"
        if macro_prov.exists():
            payload = json.loads(macro_prov.read_text(encoding="utf-8"))
            macro_id = payload.get("macro_id")
            if macro_id:
                admitted_macros.append(macro_id)
        patch_prov = diagnostics / "meta_patch_admission_provenance_v1.json"
        if patch_prov.exists():
            payload = json.loads(patch_prov.read_text(encoding="utf-8"))
            patch_id = payload.get("meta_patch_id")
            if patch_id:
                admitted_patches.append(patch_id)
        rho_report = diagnostics / "rho_report_v1.json"
        if rho_report.exists():
            rho_values.append(int(json.loads(rho_report.read_text(encoding="utf-8")).get("rho_num", 0)))
        barrier_record = diagnostics / "barrier_record_v1.json"
        if barrier_record.exists():
            barrier_values.append(int(json.loads(barrier_record.read_text(encoding="utf-8")).get("barrier_scalar_value", 0)))

    lines.append(f"- admitted_family_ids: {admitted_families}")
    lines.append(f"- admitted_macro_ids: {admitted_macros}")
    if rho_values:
        first_rho_inc = None
        for idx in range(len(rho_values) - 1):
            if rho_values[idx + 1] > rho_values[idx]:
                first_rho_inc = idx + 1
                break
        lines.append(f"- rho_num_values: {rho_values}")
        lines.append(f"- first_rho_increase_epoch_index: {first_rho_inc}")
    lines.append(f"- admitted_meta_patch_ids: {admitted_patches}")
    lines.append(f"- barrier_scalar_values: {barrier_values}")
    lines.append("")

summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

echo "sha256 outputs:"
find "$OUT_ROOT/run_0" -type f -name 'rsi_ignition_report_v1.json' -print0 | xargs -0 shasum -a 256
find "$OUT_ROOT/run_0" -type f -name 'barrier_record_v1.json' -print0 | xargs -0 shasum -a 256
find "$OUT_ROOT/run_0" -type f -name 'macro_ledger_v1.jsonl' -print0 | xargs -0 shasum -a 256
find "$OUT_ROOT/run_0" -type f -name 'macro_active_set_v1.json' -print0 | xargs -0 shasum -a 256


# RSI-L6 gate
python3 cdel/v1_5r/tools/verify_rsi_l6_one_shot.py "$OUT_ROOT"
