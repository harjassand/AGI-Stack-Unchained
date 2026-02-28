#!/usr/bin/env bash
set -euo pipefail
mkdir -p release

manifest="release/release_manifest.json"
if [[ ! -f "${manifest}" ]]; then
  echo "missing ${manifest}; run build_release.sh first" >&2
  exit 1
fi

manifest_sha="sha256:$(shasum -a 256 "${manifest}" | awk '{print $1}')"
signer="${APFSC_RELEASE_SIGNER:-local-release-manager}"

cat > release/signature.bundle.json <<SIG
{
  "signer": "${signer}",
  "algorithm": "sha256",
  "manifest_digest": "${manifest_sha}",
  "signed_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
SIG
