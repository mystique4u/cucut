#!/bin/bash
set -euo pipefail
ROOT="${1:-.}"
cd "$ROOT"
echo "🔍 Scanning for hardcoded secrets..."
if grep -r -i -E "(password|secret|api_key|token).*=.*['\"][^'\"]{8,}['\"]" \
  --exclude="*.example" --exclude="README.md" --exclude="CHANGELOG.md" \
  --exclude="CONTRIBUTING.md" --exclude="AGENTS.md" \
  --exclude-dir=".git" --exclude-dir=".venv" --exclude-dir=".pytest_cache" \
  . 2>/dev/null \
  | grep -v "^[[:space:]]*#" \
  | grep -v "os.environ.get" \
  | grep -v "os.getenv" \
  | grep -v "gitleaks:allow"; then
  echo "::error::Found potential hardcoded secrets!" >&2
  exit 1
fi
echo "✅ No hardcoded secrets detected"
