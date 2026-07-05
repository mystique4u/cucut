#!/bin/bash
# Wrapper: exit 0 when push contains only service/meta file changes.
#
# Usage:
#   PUSH_REFS_FILE=/tmp/refs bash scripts/is-service-only-change.sh --pre-push
#   git diff --name-only A B | bash scripts/is-service-only-change.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ "${1:-}" = "--pre-push" ] && [ -n "${PUSH_REFS_FILE:-}" ] && [ -f "$PUSH_REFS_FILE" ]; then
  bash scripts/get-push-changed-files.sh < "$PUSH_REFS_FILE" \
    | python3 scripts/is-service-only-change.py
  exit $?
fi

if [ ! -t 0 ]; then
  python3 scripts/is-service-only-change.py
  exit $?
fi

# No push context — treat as app change (do not skip checks)
exit 1
