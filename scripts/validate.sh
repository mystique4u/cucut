#!/bin/bash
# Single validation entry point — used by CI, pre-commit, and pre-push hooks.
#
# Usage:
#   bash scripts/validate.sh            # full check (CI, pre-commit hook)
#   bash scripts/validate.sh --pre-push # full check + main/version gate (pre-push hook)
#
# Manual (optional): same as above.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PRE_PUSH=false
if [ "${1:-}" = "--pre-push" ]; then
  PRE_PUSH=true
fi

CHECKS_PASSED=0
CHECKS_FAILED=0

print_section() { echo ""; echo -e "${BLUE}━━ $1 ━━${NC}"; }
pass() { echo -e "${GREEN}  ✅ $1${NC}"; ((CHECKS_PASSED++)) || true; }
fail() { echo -e "${RED}  ❌ $1${NC}"; ((CHECKS_FAILED++)) || true; }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║              🔍 VALIDATION (cucut) — CI parity                 ║"
echo "╚═══════════════════════════════════════════════════════════════╝"

if [ "$PRE_PUSH" = true ] && [ -n "${PUSH_REFS_FILE:-}" ] \
  && bash scripts/is-service-only-change.sh --pre-push 2>/dev/null; then
  echo -e "${GREEN}Service-only change detected — skipping app validation${NC}"
  exit 0
fi

print_section "1️⃣  DEPENDENCIES"
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
if python3 -m pip install -q -e ".[dev]" 2>/dev/null; then
  pass "dev dependencies installed"
else
  fail "pip install -e '.[dev]'"
fi

print_section "2️⃣  SECRETS SCAN"
if bash scripts/check-secrets.sh "$REPO_ROOT"; then
  pass "No hardcoded secrets detected"
else
  fail "Found hardcoded secrets"
fi

print_section "3️⃣  PRE-COMMIT (all files)"
if command -v pre-commit &>/dev/null; then
  if pre-commit run --all-files; then
    pass "pre-commit run --all-files"
  else
    fail "pre-commit run --all-files"
  fi
else
  fail "pre-commit not found — run: pip install -e '.[dev]'"
fi

print_section "4️⃣  TESTS"
if pytest; then
  pass "pytest"
else
  fail "pytest"
fi

print_section "5️⃣  VERSION"
VERSION_ARGS=()
if [ "$PRE_PUSH" = true ]; then
  VERSION_ARGS=(--pre-push)
fi
if bash scripts/check-version.sh "${VERSION_ARGS[@]}"; then
  pass "version consistency"
else
  fail "version consistency"
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                    📊 VALIDATION SUMMARY                       ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "  ${GREEN}✅ Passed: $CHECKS_PASSED${NC}  ${RED}❌ Failed: $CHECKS_FAILED${NC}"
echo ""

if [ "$CHECKS_FAILED" -eq 0 ]; then
  echo -e "${GREEN}║  ✅ ALL CHECKS PASSED${NC}"
  exit 0
else
  echo -e "${RED}║  ❌ VALIDATION FAILED — fix issues above${NC}"
  exit 1
fi
