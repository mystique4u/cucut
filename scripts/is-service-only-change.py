#!/usr/bin/env python3
"""Return 0 if all changed files are service/meta paths; 1 if any app file changed."""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PATHS_FILE = REPO_ROOT / "scripts" / "service-paths.list"


def load_patterns() -> list[str]:
    patterns: list[str] = []
    for line in PATHS_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def normalize_path(path: str) -> str:
    path = path.replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    return path


def matches_service_path(path: str, patterns: list[str]) -> bool:
    path = normalize_path(path)
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        prefix = pattern.rstrip("*").rstrip("/")
        if prefix and path.startswith(prefix + "/"):
            return True
        if prefix and path == prefix:
            return True
    return False


def main() -> int:
    patterns = load_patterns()
    files = [line.strip() for line in sys.stdin if line.strip()]
    if not files:
        return 1

    app_files = [f for f in files if not matches_service_path(f, patterns)]
    if app_files:
        print("App files changed (pipeline required):", file=sys.stderr)
        for f in app_files:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("Service-only changes (pipeline skipped):", file=sys.stderr)
    for f in files:
        print(f"  - {f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
