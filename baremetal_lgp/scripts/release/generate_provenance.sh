#!/usr/bin/env bash
set -euo pipefail
mkdir -p release

cat > release/provenance.json <<PROV
{
  "builder": "apfsc-local-release",
  "git_commit": "$(git rev-parse HEAD)",
  "built_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "host": "$(uname -srm)",
  "rustc": "$(rustc --version)",
  "cargo": "$(cargo --version)",
  "target": "$(rustc -vV | sed -n 's/^host: //p')"
}
PROV
