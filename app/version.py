"""Application version + build metadata.

Layers (theo priority):
  1. ENV vars BUILD_SHA / BUILD_TIME / APP_VERSION (set bởi Docker build args).
  2. File `VERSION` ở repo root + git rev-parse local.
  3. Fallback "dev" / "unknown".

Foooter hiển thị `v{VERSION} · build {SHA[:7]} · {BUILD_TIME}`.
"""

from __future__ import annotations

import os
import subprocess
from functools import cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


@cache
def _read_version_file() -> str:
    f = _ROOT / "VERSION"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    return "0.0.0"


@cache
def _local_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=_ROOT, timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "unknown"


VERSION: str = os.environ.get("APP_VERSION") or _read_version_file()
BUILD_SHA: str = os.environ.get("BUILD_SHA") or _local_git_sha()
BUILD_TIME: str = os.environ.get("BUILD_TIME", "")


def short_sha() -> str:
    return BUILD_SHA[:7] if BUILD_SHA and BUILD_SHA != "unknown" else "dev"


def version_string() -> str:
    """Trả 'v0.1.0 · build a3f5c12 · 2026-05-21 12:30 UTC' hoặc ngắn hơn nếu thiếu info."""
    parts = [f"v{VERSION}"]
    if BUILD_SHA and BUILD_SHA != "unknown":
        parts.append(f"build {short_sha()}")
    if BUILD_TIME:
        parts.append(BUILD_TIME)
    return " · ".join(parts)
