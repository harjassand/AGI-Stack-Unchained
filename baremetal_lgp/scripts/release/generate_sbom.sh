#!/usr/bin/env bash
set -euo pipefail
mkdir -p release

manifest="release/release_manifest.json"
if [[ ! -f "${manifest}" ]]; then
  echo "missing ${manifest}; run build_release.sh first" >&2
  exit 1
fi

commit="$(sed -n 's/.*"git_commit": "\([^"]*\)".*/\1/p' "${manifest}" | head -n1)"
cat > release/sbom.spdx.json <<SBOM
{
  "spdxVersion": "SPDX-2.3",
  "dataLicense": "CC0-1.0",
  "SPDXID": "SPDXRef-DOCUMENT",
  "name": "apfsc-release-${commit}",
  "documentNamespace": "https://apfsc.local/spdx/${commit}",
  "creationInfo": {
    "created": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "creators": ["Tool: apfsc-release-script"]
  },
  "packages": [
    {
      "SPDXID": "SPDXRef-Package-apfscd",
      "name": "apfscd",
      "versionInfo": "${commit}",
      "downloadLocation": "NOASSERTION"
    },
    {
      "SPDXID": "SPDXRef-Package-apfscctl",
      "name": "apfscctl",
      "versionInfo": "${commit}",
      "downloadLocation": "NOASSERTION"
    }
  ]
}
SBOM
