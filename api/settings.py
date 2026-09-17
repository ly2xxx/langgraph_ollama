"""Configuration, read from the environment at import time."""
from __future__ import annotations

import os
from pathlib import Path

# Bind address. Localhost by default: a run executes an LLM-driven agent that
# writes files and runs commands on the selected folder, so this must not be
# exposed to a network without deliberate thought.
HOST = os.getenv("CODING_ENGINEER_API_HOST", "127.0.0.1")
PORT = int(os.getenv("CODING_ENGINEER_API_PORT", "8009"))

# Optional allow-list of directories that may be targeted, os.pathsep-separated.
# Unset means "anywhere the process can reach", which is what makes picking an
# arbitrary local folder convenient -- and is only reasonable while the server
# is bound to localhost.
_roots = os.getenv("CODING_ENGINEER_API_ROOTS", "").strip()
ALLOWED_ROOTS: list[Path] = [
    Path(p).expanduser().resolve() for p in _roots.split(os.pathsep) if p.strip()
]

# How many finished runs to keep in memory before evicting the oldest.
MAX_REMEMBERED_RUNS = int(os.getenv("CODING_ENGINEER_API_MAX_RUNS", "50"))


def roots_description() -> str:
    if not ALLOWED_ROOTS:
        return "unrestricted (set CODING_ENGINEER_API_ROOTS to limit)"
    return os.pathsep.join(str(p) for p in ALLOWED_ROOTS)
