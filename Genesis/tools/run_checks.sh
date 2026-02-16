#!/usr/bin/env bash
set -euo pipefail

python3 tools/validate_schema.py
python3 tools/canonicalize.py --verify
python3 tools/canonicalize_ref.py --verify
python3 tools/check_budget_strings.py
python3 tools/validate_receipt.py
python3 tools/verify_receipt.py receipt_examples/pass_receipt.json examples/algorithm.capsule.json
python3 ledger_sim/alpha_ledger_sim.py
python3 ledger_sim/privacy_ledger_sim.py
python3 ledger_sim/compute_ledger_sim.py
python3 tools/consistency_check.py
python3 tools/check_links.py
