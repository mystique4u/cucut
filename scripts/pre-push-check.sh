#!/bin/bash
# Pre-push validation — delegates to validate.sh (CI parity).
exec bash "$(git rev-parse --show-toplevel)/scripts/validate.sh" --pre-push
