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
echo "Hooks active (all call scripts/validate.sh — same as CI):"
echo "  pre-commit  → validate.sh"
echo "  pre-push    → validate.sh --pre-push"
echo ""
echo "Install pre-commit env once: pip install -e '.[dev]' && pre-commit install-hooks"
