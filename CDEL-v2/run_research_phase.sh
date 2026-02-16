#!/bin/bash
set -e  # Exit on error

echo "Starting Full Matrix + Analysis..."
python3 experiments/run_matrix.py --matrix experiments/matrix.json --out runs_full --resume
python3 analysis/aggregate_runs.py --runs runs_full --out analysis_full
python3 analysis/export_curves.py --runs runs_full --out analysis_full/curves
python3 analysis/check_claims.py --runs runs_full --out analysis_full/claims_report.json
python3 analysis/make_summary.py --analysis analysis_full --out analysis_full/README_summary.md
bash scripts/validate_suite_out.sh runs_full analysis_full

echo "Starting Addressability + Scan Scaling..."
python3 experiments/run_matrix.py --matrix experiments/flagships/addressability_big.json --out runs_addressability_big --resume
python3 analysis/aggregate_runs.py --runs runs_addressability_big --out analysis_addressability_big
python3 analysis/check_claims.py --runs runs_addressability_big --out analysis_addressability_big/claims_report.json
python3 analysis/make_summary.py --analysis analysis_addressability_big --out analysis_addressability_big/README_summary.md
bash scripts/validate_suite_out.sh runs_addressability_big analysis_addressability_big
python3 bench/scan_scaling.py --out analysis_addressability_big/scan_scaling.csv

echo "Starting Replicates (Seeds 0-4)..."
python3 experiments/run_replicates.py --matrix experiments/replicates.json --seeds 0,1,2,3,4 --out runs_repl --resume
python3 analysis/aggregate_runs.py --runs runs_repl --out analysis_repl
python3 analysis/check_claims.py --runs runs_repl --out analysis_repl/claims_report.json
python3 analysis/make_summary.py --analysis analysis_repl --out analysis_repl/README_summary.md
bash scripts/validate_suite_out.sh runs_repl analysis_repl

echo "Generating Paper Bundle..."
bash scripts/make_paper_bundle.sh

echo "All tasks complete."
