"""Read only the project's AI settings from a local, git-ignored .env file."""
import os
from pathlib import Path

ALLOWED = {"AI_ROUTER", "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_TIMEOUT_SECONDS"}


def load_env(root):
    path = Path(root) / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if name not in ALLOWED:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        # No evaluation, interpolation, subprocesses or arbitrary environment keys.
        os.environ.setdefault(name, value)
