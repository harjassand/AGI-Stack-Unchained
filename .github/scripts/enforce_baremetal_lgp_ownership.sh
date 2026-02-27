#!/usr/bin/env bash
set -euo pipefail

branch_name="${BRANCH_NAME:-${GITHUB_HEAD_REF:-${GITHUB_REF_NAME:-unknown}}}"
head_sha="${HEAD_SHA:-${GITHUB_SHA:-HEAD}}"
base_sha="${BASE_SHA:-}"

if [[ -z "${base_sha}" || "${base_sha}" =~ ^0+$ ]]; then
  if git rev-parse --verify "${head_sha}^" >/dev/null 2>&1; then
    base_sha="$(git rev-parse "${head_sha}^")"
  else
    base_sha="${head_sha}"
  fi
fi

echo "Ownership gate: branch=${branch_name} base=${base_sha} head=${head_sha}"

changed_files=()
while IFS= read -r path; do
  if [[ -n "${path}" ]]; then
    changed_files+=("${path}")
  fi
done < <(git diff --name-only --diff-filter=ACMRTD "${base_sha}" "${head_sha}" | sed '/^$/d')

if [[ ${#changed_files[@]} -eq 0 ]]; then
  echo "No changed files in range. Gate passes."
  exit 0
fi

echo "Changed files:"
for path in "${changed_files[@]}"; do
  echo "  - ${path}"
done

starts_with_any() {
  local path="$1"
  shift
  local prefix
  for prefix in "$@"; do
    if [[ "${path}" == "${prefix}"* ]]; then
      return 0
    fi
  done
  return 1
}

matches_any_glob() {
  local path="$1"
  shift
  local pattern
  for pattern in "$@"; do
    if [[ "${path}" == ${pattern} ]]; then
      return 0
    fi
  done
  return 1
}

# bootstrap mode: base does not yet contain OWNERS.md
bootstrap_mode=0
if ! git cat-file -e "${base_sha}:baremetal_lgp/OWNERS.md" >/dev/null 2>&1; then
  bootstrap_mode=1
fi

shared_bootstrap_only=(
  "baremetal_lgp/Cargo.toml"
  "baremetal_lgp/src/lib.rs"
  "baremetal_lgp/README.md"
  "baremetal_lgp/OWNERS.md"
)

agent1_prefixes=(
  "baremetal_lgp/src/abi.rs"
  "baremetal_lgp/src/isa/"
  "baremetal_lgp/src/bytecode/"
  "baremetal_lgp/src/cfg/"
  "baremetal_lgp/src/vm/"
  "baremetal_lgp/src/accel/"
  "baremetal_lgp/src/jit/"
)
agent1_globs=(
  "baremetal_lgp/tests/agent1_*.rs"
)

agent2_prefixes=(
  "baremetal_lgp/src/oracle/"
)
agent2_globs=(
  "baremetal_lgp/tests/agent2_*.rs"
  "baremetal_lgp/rfcs/RFC_*.md"
)

agent3_prefixes=(
  "baremetal_lgp/src/search/"
  "baremetal_lgp/src/library/"
  "baremetal_lgp/src/outer_loop/"
  "baremetal_lgp/src/bin/"
  "baremetal_lgp/scripts/"
  "baremetal_lgp/benches/"
)
agent3_globs=(
  "baremetal_lgp/tests/agent3_*.rs"
  "baremetal_lgp/rfcs/RFC_*.md"
)

allowed_prefixes=()
allowed_globs=()
case "${branch_name}" in
  "pivot/agent1_vm_isa_jit"|"codex/agent1_vm_isa_jit")
    allowed_prefixes=("${agent1_prefixes[@]}")
    allowed_globs=("${agent1_globs[@]}")
    ;;
  "pivot/agent2_oracle"|"codex/agent2_oracle")
    allowed_prefixes=("${agent2_prefixes[@]}")
    allowed_globs=("${agent2_globs[@]}")
    ;;
  "pivot/agent3_search_architect"|"codex/agent3_search_architect")
    allowed_prefixes=("${agent3_prefixes[@]}")
    allowed_globs=("${agent3_globs[@]}")
    ;;
esac

violations_shared=()
violations_ownership=()

for path in "${changed_files[@]}"; do
  if [[ ${bootstrap_mode} -eq 0 ]]; then
    for shared in "${shared_bootstrap_only[@]}"; do
      if [[ "${path}" == "${shared}" ]]; then
        violations_shared+=("${path}")
        break
      fi
    done
  fi

  if [[ ${bootstrap_mode} -eq 1 ]]; then
    # During bootstrap, only agent1 branch may perform broad setup changes.
    if [[ "${branch_name}" != "pivot/agent1_vm_isa_jit" && "${branch_name}" != "codex/agent1_vm_isa_jit" ]]; then
      violations_ownership+=("${path}")
    fi
    continue
  fi

  if [[ ${#allowed_prefixes[@]} -eq 0 && ${#allowed_globs[@]} -eq 0 ]]; then
    continue
  fi

  if starts_with_any "${path}" "${allowed_prefixes[@]}"; then
    continue
  fi
  if matches_any_glob "${path}" "${allowed_globs[@]}"; then
    continue
  fi

  violations_ownership+=("${path}")
done

failed=0

if [[ ${#violations_shared[@]} -gt 0 ]]; then
  failed=1
  echo
  echo "ERROR: Shared bootstrap-only files modified after bootstrap:"
  printf '  - %s\n' "${violations_shared[@]}"
fi

if [[ ${#violations_ownership[@]} -gt 0 ]]; then
  failed=1
  echo
  echo "ERROR: Branch ${branch_name} modified out-of-ownership paths:"
  printf '  - %s\n' "${violations_ownership[@]}"
fi

if [[ ${failed} -ne 0 ]]; then
  exit 1
fi

echo
if [[ ${bootstrap_mode} -eq 1 ]]; then
  echo "Ownership gate passed (bootstrap mode)."
else
  echo "Ownership gate passed."
fi
