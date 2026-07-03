"""Runtime build identity, so a performance/error log line can be matched
back to the exact commit that produced it.

Reads git metadata directly at process start rather than baking a commit
hash in at Docker build time: the app's dev workflow live-mounts ./app and
runs uvicorn --reload (see Dockerfile/docker-compose.yml), so a build-time
stamp would go stale the moment someone edits code without rebuilding.
Reading git live means every --reload restart picks up the current state
automatically.

Requires the repo root (not just ./app) to be readable, so
docker-compose.yml mounts the whole repo read-only at /repo. Falls back to
the local checkout when run outside Docker (e.g. `pytest`, bare uvicorn).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_DOCKER_REPO_ROOT = Path("/repo")
_LOCAL_REPO_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _DOCKER_REPO_ROOT if (_DOCKER_REPO_ROOT / ".git").exists() else _LOCAL_REPO_ROOT


def _run_git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _detect() -> tuple[str, bool]:
    commit = _run_git("rev-parse", "--short", "HEAD")
    if not commit:
        return "unknown", False
    # Non-empty output means the working tree has uncommitted changes --
    # relevant here because logs can otherwise misleadingly point at a
    # commit that doesn't fully match what actually ran (plan/06-perf).
    dirty = bool(_run_git("status", "--porcelain"))
    return commit, dirty


GIT_COMMIT, GIT_DIRTY = _detect()
VERSION_LABEL = f"{GIT_COMMIT}{'-dirty' if GIT_DIRTY else ''}"
