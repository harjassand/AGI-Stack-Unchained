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

added_files=()
while IFS= read -r path; do
  if [[ -n "${path}" ]]; then
    added_files+=("${path}")
  fi
done < <(git diff --name-only --diff-filter=A "${base_sha}" "${head_sha}" | sed '/^$/d')

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
branch_recognized=0
case "${branch_name}" in
  "pivot/agent1_vm_isa_jit"|"codex/agent1_vm_isa_jit")
    branch_recognized=1
    allowed_prefixes=("${agent1_prefixes[@]}")
    allowed_globs=("${agent1_globs[@]}")
    ;;
  "pivot/agent2_oracle"|"codex/agent2_oracle")
    branch_recognized=1
    allowed_prefixes=("${agent2_prefixes[@]}")
    allowed_globs=("${agent2_globs[@]}")
    ;;
  "pivot/agent3_search_architect"|"codex/agent3_search_architect")
    branch_recognized=1
    allowed_prefixes=("${agent3_prefixes[@]}")
    allowed_globs=("${agent3_globs[@]}")
    ;;
  "pivot/baremetal_lgp_rsi"|"codex/pivot/baremetal_lgp_rsi")
    # Integration branch: shared-file rules still apply.
    branch_recognized=1
    ;;
esac

violations_shared=()
violations_ownership=()
rfc_create_violations=()
unknown_branch_violation=0

if [[ ${bootstrap_mode} -eq 0 && ${branch_recognized} -eq 0 ]]; then
  unknown_branch_violation=1
fi

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

# RFC policy nuance: agent3 creates RFC_*.md, agent2 may edit but not create.
if [[ "${branch_name}" == "pivot/agent2_oracle" || "${branch_name}" == "codex/agent2_oracle" ]]; then
  for path in "${added_files[@]}"; do
    if [[ "${path}" == baremetal_lgp/rfcs/RFC_*.md ]]; then
      rfc_create_violations+=("${path}")
    fi
  done
fi

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

if [[ ${#rfc_create_violations[@]} -gt 0 ]]; then
  failed=1
  echo
  echo "ERROR: RFC file creation is restricted to agent3 branches:"
  printf '  - %s\n' "${rfc_create_violations[@]}"
fi

if [[ ${unknown_branch_violation} -ne 0 ]]; then
  failed=1
  echo
  echo "ERROR: Unrecognized branch for ownership policy: ${branch_name}"
  echo "Use one of:"
  echo "  - pivot/agent1_vm_isa_jit"
  echo "  - pivot/agent2_oracle"
  echo "  - pivot/agent3_search_architect"
  echo "  - pivot/baremetal_lgp_rsi (integration)"
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
