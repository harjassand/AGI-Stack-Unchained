#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <version>" >&2
  exit 1
fi

version="$1"
if [[ ! -d "releases/${version}" ]]; then
  echo "release not found: ${version}" >&2
  exit 1
fi

ln -sfn "${version}" releases/active
echo "rolled back active release to ${version}"
