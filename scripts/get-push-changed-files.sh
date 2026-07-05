#!/bin/bash
# List files changed in a git push (one path per line).
#
# Usage:
#   PUSH_REFS_FILE=/tmp/refs bash scripts/get-push-changed-files.sh
#   bash scripts/get-push-changed-files.sh < refs-file

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

read_refs() {
  if [ -n "${PUSH_REFS_FILE:-}" ] && [ -f "$PUSH_REFS_FILE" ]; then
    cat "$PUSH_REFS_FILE"
  elif [ ! -t 0 ]; then
    cat
  else
    return 1
  fi
}

zero="0000000000000000000000000000000000000000"
files=()

while read -r local_ref local_sha remote_ref remote_sha; do
  [ -z "${local_sha:-}" ] || [ "$local_sha" = "$zero" ] && continue

  if [ "${remote_sha:-$zero}" = "$zero" ]; then
    range="$local_sha"
  else
    range="${remote_sha}..${local_sha}"
  fi

  while IFS= read -r path; do
    [ -n "$path" ] && files+=("$path")
  done < <(git log --name-only --pretty=format: "$range" | sort -u)
done < <(read_refs || true)

if [ "${#files[@]}" -eq 0 ]; then
  # Manual fallback: last commit
  git diff-tree --no-commit-id --name-only -r HEAD 2>/dev/null || true
  exit 0
fi

printf '%s\n' "${files[@]}" | sort -u
