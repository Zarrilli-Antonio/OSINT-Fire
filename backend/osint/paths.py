import os
import sys
from pathlib import Path


def data_dir(platform: str, env: dict, home: Path) -> Path:
    """Per-user data folder of the packaged app."""
    if platform == "win32":
        return Path(env.get("APPDATA") or home / "AppData" / "Roaming") / "OSINT-Fire"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "OSINT-Fire"
    return Path(env.get("XDG_DATA_HOME") or home / ".local" / "share") / "OSINT-Fire"


def db_path() -> str:
    """Database location. Development keeps ./osint.db; the packaged app uses the user's data folder so it survives updates."""
    if p := os.environ.get("OSINT_DB"):
        return p
    if getattr(sys, "frozen", False):
        base = data_dir(sys.platform, dict(os.environ), Path.home())
        base.mkdir(parents=True, exist_ok=True)
        return str(base / "osint.db")
    return "osint.db"
