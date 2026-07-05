#!/bin/bash
# Validate semantic version consistency (pyproject.toml + cucut.__version__).
#
# Usage:
#   bash scripts/check-version.sh
#   bash scripts/check-version.sh --pre-push

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PRE_PUSH=false
if [ "${1:-}" = "--pre-push" ]; then
  PRE_PUSH=true
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

ERRORS=0
fail() { echo -e "${RED}  ❌ $1${NC}"; ((ERRORS++)) || true; }
pass() { echo -e "${GREEN}  ✅ $1${NC}"; }

read_version() {
  python3 - <<'PY'
import re
from pathlib import Path

pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
if not match:
    raise SystemExit("missing version in pyproject.toml")
print(match.group(1))
PY
}

read_init_version() {
  python3 - <<'PY'
import re
from pathlib import Path

text = Path("src/cucut/__init__.py").read_text(encoding="utf-8")
match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
if not match:
    raise SystemExit("missing __version__ in src/cucut/__init__.py")
print(match.group(1))
PY
}

PKG_VERSION="$(read_version)"
INIT_VERSION="$(read_init_version)"

if [[ "$PKG_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  pass "pyproject.toml version: $PKG_VERSION (valid semver)"
else
  fail "pyproject.toml version '$PKG_VERSION' is not valid semver (X.Y.Z)"
fi

if [ "$INIT_VERSION" != "$PKG_VERSION" ]; then
  fail "src/cucut/__init__.py ($INIT_VERSION) != pyproject.toml ($PKG_VERSION)"
else
  pass "package __version__ matches pyproject.toml"
fi

if [ -f CHANGELOG.md ]; then
  if grep -q '## \[Unreleased\]' CHANGELOG.md; then
    pass "CHANGELOG.md has [Unreleased] section"
  else
    fail "CHANGELOG.md missing ## [Unreleased] section"
  fi
else
  fail "CHANGELOG.md not found"
fi

if [ "$PRE_PUSH" = true ]; then
  PUSHING_TO_MAIN=false
  if [ -n "${PUSH_REFS_FILE:-}" ] && [ -f "$PUSH_REFS_FILE" ]; then
    while read -r _local_ref _local_sha remote_ref _remote_sha; do
      if [[ "$remote_ref" == "refs/heads/main" ]]; then
        PUSHING_TO_MAIN=true
      fi
    done < "$PUSH_REFS_FILE"
  fi

  if [ "$PUSHING_TO_MAIN" = true ]; then
    if bash scripts/is-service-only-change.sh --pre-push 2>/dev/null; then
      pass "Service-only push to main — version bump not required"
    else
      LAST_TAG="$(git describe --tags --abbrev=0 --match 'v*' 2>/dev/null || echo '')"
      if [ -n "$LAST_TAG" ]; then
        LAST_VERSION="${LAST_TAG#v}"
        if [ "$PKG_VERSION" = "$LAST_VERSION" ]; then
          fail "Pushing app changes to main but version is still v$PKG_VERSION (same as tag $LAST_TAG)"
          echo "       Run: bash scripts/bump-version.sh [patch|minor|major]"
        else
          pass "Version v$PKG_VERSION is ahead of last tag $LAST_TAG"
        fi
      else
        pass "No prior v* tag — first release push"
      fi
    fi
  fi
fi

if [ "$ERRORS" -gt 0 ]; then
  exit 1
fi

exit 0
