#!/bin/bash
# Pre-push validation for cucut — mirrors CI locally.
# Called automatically by .githooks/pre-push on every git push.
# Manual run (optional): bash scripts/pre-push-check.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CHECKS_PASSED=0
CHECKS_FAILED=0

print_section() { echo ""; echo -e "${BLUE}━━ $1 ━━${NC}"; }
pass() { echo -e "${GREEN}  ✅ $1${NC}"; ((CHECKS_PASSED++)) || true; }
fail() { echo -e "${RED}  ❌ $1${NC}"; ((CHECKS_FAILED++)) || true; }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║           🚀 PRE-PUSH VALIDATION CHECKS (cucut)                 ║"
echo "╚═══════════════════════════════════════════════════════════════╝"

if [ -n "${PUSH_REFS_FILE:-}" ] && bash scripts/is-service-only-change.sh --pre-push 2>/dev/null; then
  echo -e "${GREEN}Service-only change detected — skipping app validation${NC}"
  exit 0
fi

print_section "1️⃣  SECRETS SCAN"
if bash scripts/check-secrets.sh "$REPO_ROOT"; then
  pass "No hardcoded secrets detected"
else
  fail "Found hardcoded secrets"
fi

print_section "2️⃣  YAML / TOML SYNTAX"
YAML_ERRORS=0
python3 -m pip install -q pyyaml 2>/dev/null || true

for wf in .github/workflows/*.yml .github/workflows/*.yaml; do
  [ -f "$wf" ] || continue
  if python3 -c "import yaml; yaml.safe_load(open('$wf'))" 2>/dev/null; then
    pass "$(basename "$wf")"
  else
    fail "$(basename "$wf")"
    ((YAML_ERRORS++)) || true
  fi
done

if python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))" 2>/dev/null; then
  pass "pyproject.toml"
else
  fail "pyproject.toml"
fi

print_section "3️⃣  PYTHON QUALITY"
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python3 -m pip install -q -e ".[dev]" 2>/dev/null || true

if command -v ruff &>/dev/null; then
  if ruff check src tests; then
    pass "ruff check"
  else
    fail "ruff check"
  fi
  if ruff format --check src tests; then
    pass "ruff format"
  else
    fail "ruff format"
  fi
else
  warn "ruff not installed — run: pip install -e '.[dev]'"
fi

print_section "4️⃣  TESTS"
if pytest; then
  pass "pytest"
else
  fail "pytest"
fi

print_section "5️⃣  VERSION"
if bash scripts/check-version.sh --pre-push; then
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
  echo -e "${GREEN}║  ✅ ALL CHECKS PASSED — READY TO PUSH! 🚀${NC}"
  exit 0
else
  echo -e "${RED}║  ❌ VALIDATION FAILED — fix issues above${NC}"
  exit 1
fi
