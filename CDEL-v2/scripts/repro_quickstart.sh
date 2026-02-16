#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR_STAT="$(mktemp -d)"
WORKDIR_GEN="$(mktemp -d)"

cd "$ROOT_DIR"

# Explicit init + keygen (smoke_statcert_adopt also performs its own init/keygen).
cdel --root "$WORKDIR_STAT" init --budget 1000000 >/dev/null
cdel --root "$WORKDIR_STAT" sealed keygen --out "$WORKDIR_STAT/sealed_keypair.json" >/dev/null

scripts/smoke_statcert_adopt.sh "$WORKDIR_STAT" >/dev/null
scripts/smoke_generalization_experiment.sh "$WORKDIR_GEN" >/dev/null

echo "stat_cert_root=$WORKDIR_STAT"
echo "generalization_root=$WORKDIR_GEN"
echo "generalization_summary=$WORKDIR_GEN/out/summary.md"
echo "generalization_results=$WORKDIR_GEN/out/results.json"
