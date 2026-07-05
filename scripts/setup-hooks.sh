#!/bin/bash
# One-time hook setup for cucut.
# Uses .githooks/ (do NOT run `pre-commit install` — conflicts with core.hooksPath).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

git config core.hooksPath .githooks
chmod +x .githooks/pre-commit .githooks/pre-push .githooks/commit-msg 2>/dev/null || true

echo "✅ git hooksPath → .githooks"
echo ""
echo "Hooks active:"
echo "  pre-commit  → pre-commit run (ruff, yaml, …)"
echo "  commit-msg  → conventional commits"
echo "  pre-push    → scripts/pre-push-check.sh"
echo ""
echo "Install pre-commit env once: pip install -e '.[dev]' && pre-commit install-hooks"
