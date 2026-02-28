#!/usr/bin/env bash
set -euo pipefail

if ! git diff --quiet --ignore-submodules --exit-code; then
  echo "release build requires a clean working tree" >&2
  exit 1
fi

mkdir -p release
cargo build --release --bin apfscd --bin apfscctl --bin apfsc_release_verify
cp target/release/apfscd release/apfscd
cp target/release/apfscctl release/apfscctl
cp target/release/apfsc_release_verify release/apfsc_release_verify

version="${RELEASE_VERSION:-0.1.0-dev}"
git_commit="$(git rev-parse HEAD)"
build_profile="release"
rust_toolchain="stable"
target_triple="$(rustc -vV | sed -n 's/^host: //p')"

apfscd_digest="sha256:$(shasum -a 256 release/apfscd | awk '{print $1}')"
apfscctl_digest="sha256:$(shasum -a 256 release/apfscctl | awk '{print $1}')"
verify_digest="sha256:$(shasum -a 256 release/apfsc_release_verify | awk '{print $1}')"

cat > release/release_manifest.json <<MANIFEST
{
  "release_manifest_version": 1,
  "version": "${version}",
  "git_commit": "${git_commit}",
  "build_profile": "${build_profile}",
  "rust_toolchain": "${rust_toolchain}",
  "target_triple": "${target_triple}",
  "artifact_digests": {
    "release/apfscd": "${apfscd_digest}",
    "release/apfscctl": "${apfscctl_digest}",
    "release/apfsc_release_verify": "${verify_digest}"
  },
  "sbom_path": "release/sbom.spdx.json",
  "provenance_path": "release/provenance.json",
  "signature_bundle_path": "release/signature.bundle.json"
}
MANIFEST
