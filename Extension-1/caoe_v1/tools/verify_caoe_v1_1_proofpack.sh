#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <path/to/caoe_v1_1_hypothesis_demo_bundle.tar>" >&2
  exit 2
fi

bundle_path="$1"
if [[ ! -f "$bundle_path" ]]; then
  echo "bundle not found: $bundle_path" >&2
  exit 2
fi

bundle_dir="$(cd "$(dirname "$bundle_path")" && pwd)"
sha_path="$bundle_dir/$(basename "$bundle_path" .tar).sha256"
if [[ ! -f "$sha_path" ]]; then
  echo "sha256 file not found: $sha_path" >&2
  exit 2
fi

calc_sha() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

expected_sha="$(awk '{print $1}' "$sha_path")"
actual_sha="$(calc_sha "$bundle_path")"
if [[ "$expected_sha" != "$actual_sha" ]]; then
  echo "bundle sha256 mismatch: expected=$expected_sha actual=$actual_sha" >&2
  exit 1
fi

tmp_dir="$(mktemp -d)"
cleanup() { rm -rf "$tmp_dir"; }
trap cleanup EXIT

tar -xf "$bundle_path" -C "$tmp_dir"

epoch_12_dir="$(find "$tmp_dir" -type d -name epoch_12_mdl_witness -print -quit)"
epoch_13_dir="$(find "$tmp_dir" -type d -name epoch_13_post_promotion -print -quit)"
if [[ -z "$epoch_12_dir" || -z "$epoch_13_dir" ]]; then
  echo "epoch dirs not found in bundle" >&2
  exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
verify_epoch="$script_dir/verify_epoch_consistency_v1_1.py"
verify_witness="$script_dir/verify_failure_witness_index_v1_1.py"
verify_receipts="$script_dir/verify_receipts_meta_core_v1.py"

run_verify_epoch() {
  local epoch_dir="$1"
  local report_path="$epoch_dir/epoch_consistency_report.json"
  local sha_path="$epoch_dir/epoch_consistency_report.sha256"
  local tmp_report=""
  local tmp_sha=""
  if [[ -f "$report_path" ]]; then
    tmp_report="$(mktemp)"
    cp "$report_path" "$tmp_report"
  fi
  if [[ -f "$sha_path" ]]; then
    tmp_sha="$(mktemp)"
    cp "$sha_path" "$tmp_sha"
  fi
  python3 "$verify_epoch" "$epoch_dir"
  if [[ -n "$tmp_report" ]]; then
    mv "$tmp_report" "$report_path"
  fi
  if [[ -n "$tmp_sha" ]]; then
    mv "$tmp_sha" "$sha_path"
  fi
}

run_verify_epoch "$epoch_12_dir"
run_verify_epoch "$epoch_13_dir"

selected_id="$(python3 - "$epoch_12_dir/selection.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("selected_candidate_id") or "")
PY
)"

expected_selection_path="$(find "$tmp_dir" -type f -name proofpack_selection.json -print -quit)"
if [[ -z "$expected_selection_path" ]]; then
  echo "proofpack_selection.json missing in bundle" >&2
  exit 1
fi
expected_selection="$(python3 - "$expected_selection_path" <<'PY'
import json,sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("epoch_12_selected_candidate_id") or "")
PY
)"
if [[ "$selected_id" != "$expected_selection" ]]; then
  echo "selected_candidate_id mismatch: expected=$expected_selection actual=$selected_id" >&2
  exit 1
fi

if [[ -z "$selected_id" || "$selected_id" == "none" ]]; then
  echo "epoch_12 selected_candidate_id missing" >&2
  exit 1
fi

find_candidate_dir() {
  local epoch_dir="$1"
  local candidate_id="$2"
  local results_dir="$epoch_dir/cdel_results_full"
  for cand_dir in "$results_dir"/candidate_*; do
    [[ -d "$cand_dir" ]] || continue
    if [[ -f "$cand_dir/evidence_report.json" ]]; then
      local cid
      cid="$(python3 - "$cand_dir/evidence_report.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("candidate_id") or "")
PY
)"
      if [[ "$cid" == "$candidate_id" ]]; then
        echo "$cand_dir"
        return
      fi
    fi
  done
}

selected_dir="$(find_candidate_dir "$epoch_12_dir" "$selected_id")"
if [[ -z "$selected_dir" ]]; then
  echo "selected candidate dir not found for $selected_id" >&2
  exit 1
fi
python3 "$verify_witness" "$selected_dir"

identity_12_id="$(python3 - "$epoch_12_dir/candidate_decisions.json" <<'PY'
import json,sys
data=json.load(open(sys.argv[1], "r", encoding="utf-8"))
for entry in data.get("entries", []):
    if entry.get("proposal_type") == "identity":
        print(entry.get("candidate_id") or "")
        raise SystemExit(0)
raise SystemExit(1)
PY
)" || true
if [[ -z "$identity_12_id" ]]; then
  echo "identity candidate not found in epoch_12 candidate_decisions" >&2
  exit 1
fi
identity_12_dir="$(find_candidate_dir "$epoch_12_dir" "$identity_12_id")"
if [[ -z "$identity_12_dir" ]]; then
  echo "identity candidate dir not found for $identity_12_id" >&2
  exit 1
fi
python3 "$verify_witness" "$identity_12_dir"

identity_id="$(python3 - "$epoch_13_dir/candidate_decisions.json" <<'PY'
import json,sys
data=json.load(open(sys.argv[1], "r", encoding="utf-8"))
for entry in data.get("entries", []):
    if entry.get("proposal_type") == "identity":
        print(entry.get("candidate_id") or "")
        raise SystemExit(0)
raise SystemExit(1)
PY
)" || true

if [[ -z "$identity_id" ]]; then
  echo "identity candidate not found in epoch_13 candidate_decisions" >&2
  exit 1
fi

identity_dir="$(find_candidate_dir "$epoch_13_dir" "$identity_id")"
if [[ -z "$identity_dir" ]]; then
  echo "identity candidate dir not found for $identity_id" >&2
  exit 1
fi
python3 "$verify_witness" "$identity_dir"

python3 "$verify_receipts" "$epoch_12_dir"
python3 "$verify_receipts" "$epoch_13_dir"

python3 - "$epoch_13_dir/success_matrix.json" <<'PY'
import json,sys
base = json.load(open(sys.argv[1], "r", encoding="utf-8")).get("base") or {}
if not base:
    raise SystemExit("base row missing in success_matrix")
if not all(float(v) == 1.0 for v in base.values()):
    raise SystemExit("epoch_13 base row not all ones")
PY

python3 - "$identity_dir/failure_witness_index.json" <<'PY'
import json,sys
fw = json.load(open(sys.argv[1], "r", encoding="utf-8"))
held = (fw.get("heldout") or {}).get("base") or {}
if int(held.get("total_bytes", -1)) != 0:
    raise SystemExit("epoch_13 base failure_witness_bytes != 0")
PY

python3 - "$(find "$tmp_dir" -type f -name lifecycle.json -print -quit)" <<'PY'
import json,sys
data=json.load(open(sys.argv[1], "r", encoding="utf-8"))
state=data.get("state")
if state != "STABLE":
    raise SystemExit(f"lifecycle state != STABLE ({state})")
PY

sha_list="$(find "$tmp_dir" -type f -name proofpack_artifacts.sha256 -print -quit)"
if [[ -z "$sha_list" ]]; then
  echo "proofpack_artifacts.sha256 missing in bundle" >&2
  exit 1
fi

bundle_root="$(dirname "$sha_list")"
while read -r expected path; do
  [[ -n "$expected" ]] || continue
  target="$bundle_root/$path"
  if [[ ! -f "$target" ]]; then
    echo "missing artifact: $path" >&2
    exit 1
  fi
  actual="$(calc_sha "$target")"
  if [[ "$expected" != "$actual" ]]; then
    echo "artifact hash mismatch: $path expected=$expected actual=$actual" >&2
    exit 1
  fi
done < "$sha_list"

echo "proofpack verification passed"
