#!/bin/sh
set -eu

BUNDLE_DIR="${BUNDLE_DIR:-paper_bundle}"
ANALYSIS_FULL="${ANALYSIS_FULL:-analysis_full}"
ANALYSIS_ADDR="${ANALYSIS_ADDR:-analysis_addressability_big}"
ANALYSIS_REPL="${ANALYSIS_REPL:-analysis_repl}"
RUNS_FULL="${RUNS_FULL:-runs_full}"
RUNS_ADDR="${RUNS_ADDR:-runs_addressability_big}"
RUNS_REPL="${RUNS_REPL:-runs_repl}"

rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR"

cat <<'README' > "$BUNDLE_DIR/README.md"
# CDEL Paper Bundle

This bundle contains analysis outputs and selected run metadata for the paper-grade results.

Included:
- analysis_full/
- analysis_addressability_big/
- analysis_repl/
- runs_full/ (symlink or copy if present)
- runs_addressability_big/ (symlink or copy if present)
- runs_repl/ (symlink or copy if present)

Key claims are reported in each analysis directory's README_summary.md and claims_report.json.
README

if [ -d "$ANALYSIS_FULL" ]; then
  cp -R "$ANALYSIS_FULL" "$BUNDLE_DIR/analysis_full"
fi
if [ -d "$ANALYSIS_ADDR" ]; then
  cp -R "$ANALYSIS_ADDR" "$BUNDLE_DIR/analysis_addressability_big"
fi
if [ -d "$ANALYSIS_REPL" ]; then
  cp -R "$ANALYSIS_REPL" "$BUNDLE_DIR/analysis_repl"
fi

if [ -d "$RUNS_FULL" ]; then
  ln -s "../$RUNS_FULL" "$BUNDLE_DIR/runs_full" 2>/dev/null || cp -R "$RUNS_FULL" "$BUNDLE_DIR/runs_full"
fi
if [ -d "$RUNS_ADDR" ]; then
  ln -s "../$RUNS_ADDR" "$BUNDLE_DIR/runs_addressability_big" 2>/dev/null || cp -R "$RUNS_ADDR" "$BUNDLE_DIR/runs_addressability_big"
fi
if [ -d "$RUNS_REPL" ]; then
  ln -s "../$RUNS_REPL" "$BUNDLE_DIR/runs_repl" 2>/dev/null || cp -R "$RUNS_REPL" "$BUNDLE_DIR/runs_repl"
fi
