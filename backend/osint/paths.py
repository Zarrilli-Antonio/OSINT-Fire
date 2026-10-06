import os
import sys
from pathlib import Path


def db_path() -> str:
    """Database location. Development keeps ./osint.db; the packaged app uses the user's data folder so it survives updates."""
    if p := os.environ.get("OSINT_DB"):
        return p
    if getattr(sys, "frozen", False):
        base = Path.home() / ("Library/Application Support" if sys.platform == "darwin" else ".local/share") / "OSINT-Fire"
        base.mkdir(parents=True, exist_ok=True)
        return str(base / "osint.db")
    return "osint.db"
