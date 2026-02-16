#!/usr/bin/env bash
set -euo pipefail

python3 -m unittest -q tests_orchestration/test_apply_and_audit.py
python3 -m unittest -q tests_orchestration/test_apply_determinism.py
python3 -m unittest -q tests_orchestration/test_reject_does_not_mutate_active.py
python3 -m unittest -q tests_orchestration/test_atomicity_simulated_failure.py
python3 -m unittest -q tests_orchestration/test_ledger_entries.py
