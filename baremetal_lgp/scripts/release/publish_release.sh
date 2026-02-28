#!/usr/bin/env bash
set -euo pipefail

manifest="release/release_manifest.json"
if [[ ! -f "${manifest}" ]]; then
  echo "missing ${manifest}; run build/release generation first" >&2
  exit 1
fi

version="$(sed -n 's/.*"version": "\([^"]*\)".*/\1/p' "${manifest}" | head -n1)"
if [[ -z "${version}" ]]; then
  echo "unable to determine version from ${manifest}" >&2
  exit 1
fi

out_dir="releases/${version}"
mkdir -p "${out_dir}"
cp -R release/. "${out_dir}/"

ln -sfn "${version}" releases/active

echo "published release ${version} to ${out_dir}"
