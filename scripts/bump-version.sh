#!/bin/bash
# Bump semantic version in pyproject.toml and src/cucut/__init__.py.
#
# Usage:
#   bash scripts/bump-version.sh patch
#   bash scripts/bump-version.sh minor
#   bash scripts/bump-version.sh major
#   bash scripts/bump-version.sh          # auto-detect from commits

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BUMP_TYPE="${1:-auto}"

detect_bump_from_commits() {
  local last_tag
  last_tag="$(git describe --tags --abbrev=0 --match 'v*' 2>/dev/null || echo '')"

  local range
  if [ -n "$last_tag" ]; then
    range="${last_tag}..HEAD"
  else
    range="HEAD"
  fi

  local commits
  commits="$(git log "$range" --pretty=format:'%s' 2>/dev/null || true)"

  if [ -z "$commits" ]; then
    echo "patch"
    return
  fi

  if echo "$commits" | grep -qE '(^|:)![:\)]|BREAKING CHANGE'; then
    echo "major"
  elif echo "$commits" | grep -qE '^feat(\(.+\))?:'; then
    echo "minor"
  else
    echo "patch"
  fi
}

if [ "$BUMP_TYPE" = "auto" ]; then
  BUMP_TYPE="$(detect_bump_from_commits)"
  echo "Auto-detected bump type: $BUMP_TYPE"
fi

case "$BUMP_TYPE" in
  patch|minor|major) ;;
  *)
    echo "Usage: bash scripts/bump-version.sh [patch|minor|major|auto]" >&2
    exit 1
    ;;
esac

python3 - "$BUMP_TYPE" <<'PY'
import re
import sys
from pathlib import Path

bump = sys.argv[1]

pyproject_path = Path("pyproject.toml")
init_path = Path("src/cucut/__init__.py")

text = pyproject_path.read_text(encoding="utf-8")
match = re.search(r'^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"', text, re.M)
if not match:
    raise SystemExit("Cannot parse version from pyproject.toml")

major, minor, patch = map(int, match.groups())
if bump == "major":
    major, minor, patch = major + 1, 0, 0
elif bump == "minor":
    minor, patch = minor + 1, 0
else:
    patch += 1

new_version = f"{major}.{minor}.{patch}"
print(f"Bumping version → {new_version}")

new_text = re.sub(
    r'^version\s*=\s*"[^"]+"',
    f'version = "{new_version}"',
    text,
    count=1,
    flags=re.M,
)
pyproject_path.write_text(new_text, encoding="utf-8")

init_text = init_path.read_text(encoding="utf-8")
init_path.write_text(
    re.sub(
        r'__version__\s*=\s*"[^"]+"',
        f'__version__ = "{new_version}"',
        init_text,
        count=1,
    ),
    encoding="utf-8",
)
PY

echo ""
echo "Next steps:"
echo "  1. Move CHANGELOG.md [Unreleased] entries to [X.Y.Z] - date"
echo "  2. bash scripts/pre-push-check.sh"
echo "  3. git add pyproject.toml src/cucut/__init__.py CHANGELOG.md"
