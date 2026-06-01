"""Persistent settings store for HytaleModLauncher.

Saves/loads user preferences (e.g., mods directory) to
%APPDATA%\HytaleModLauncher\settings.json so the app remembers
configuration between sessions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# Config lives in %APPDATA%\HytaleModLauncher\ on Windows
_CONFIG_DIR  = Path(os.environ.get("APPDATA", Path.home())) / "HytaleModLauncher"
_CONFIG_PATH = _CONFIG_DIR / "settings.json"

# Default mods directory — matches the real Hytale install location on Windows
DEFAULT_MODS_DIR = str(
    Path(os.environ.get("APPDATA", Path.home())) / "Hytale" / "UserData" / "Mods"
)


def load() -> dict:
    """Return the full settings dict (empty dict if file doesn't exist)."""
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def save(data: dict) -> None:
    """Persist the full settings dict."""
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def load_mods_dir() -> str:
    return load().get("mods_dir") or DEFAULT_MODS_DIR

def save_mods_dir(path: str) -> None:
    data = load()
    data["mods_dir"] = path
    save(data)

def load_theme() -> str:
    return load().get("theme") or "Dark"

def save_theme(theme_name: str) -> None:
    data = load()
    data["theme"] = theme_name
    save(data)

def load_language() -> str:
    return load().get("language") or "en"

def save_language(lang: str) -> None:
    data = load()
    data["language"] = lang
    save(data)
