#!/usr/bin/env bash
set -euo pipefail
cargo run --bin apfsc_release_verify -- \
  --manifest release/release_manifest.json \
  --sbom release/sbom.spdx.json \
  --provenance release/provenance.json \
  --signature release/signature.bundle.json
