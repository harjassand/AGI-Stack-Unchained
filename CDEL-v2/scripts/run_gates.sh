#!/bin/sh
set -eu

ROOT="${ROOT:-.}"

python3 -c "from cdel.cli import main; main()" selfcheck

if [ -d "runs_gate_quick" ] && [ -d "analysis_gate_quick" ]; then
  if bash scripts/validate_suite_out.sh runs_gate_quick analysis_gate_quick; then
    echo "quick gate already valid"
  else
    bash scripts/run_suite_quick.sh
    bash scripts/validate_suite_out.sh runs_gate_quick analysis_gate_quick
  fi
else
  bash scripts/run_suite_quick.sh
  bash scripts/validate_suite_out.sh runs_gate_quick analysis_gate_quick
fi

if [ -d "runs_gate_mid" ] && [ -d "analysis_gate_mid" ]; then
  if bash scripts/validate_suite_out.sh runs_gate_mid analysis_gate_mid; then
    echo "mid gate already valid"
  else
    bash scripts/run_suite_mid.sh
    bash scripts/validate_suite_out.sh runs_gate_mid analysis_gate_mid
  fi
else
  bash scripts/run_suite_mid.sh
  bash scripts/validate_suite_out.sh runs_gate_mid analysis_gate_mid
fi
