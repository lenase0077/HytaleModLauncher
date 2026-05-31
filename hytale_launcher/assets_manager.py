"""Assets manager for HytaleModLauncher.

Handles fetching and caching Lucide icons locally to avoid bundling
thousands of SVGs into the executable while keeping dependencies minimal.
"""

from __future__ import annotations

import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtGui import QIcon

_ICONS_DIR = Path(os.environ.get("APPDATA", Path.home())) / "HytaleModLauncher" / "icons"
_BASE_URL  = "https://raw.githubusercontent.com/lucide-icons/lucide/main/icons"

# Icons used by the app
REQUIRED_ICONS = [
    "search",
    "package",
    "settings",
    "plus",
    "trash-2",
    "external-link",
    "check",
    "refresh-cw",
    "circle-arrow-up",
    "folder",
    "chevron-left",
    "chevron-right",
    "zap",
]

def _ensure_icon(name: str) -> None:
    """Download the icon from GitHub if it doesn't exist locally."""
    dest = _ICONS_DIR / f"{name}.svg"
    if dest.exists():
        return
    try:
        url = f"{_BASE_URL}/{name}.svg"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            content = response.read()
            # Replace default 'currentColor' with a neutral bright color for testing,
            # or keep it as is. Qt uses styling if applied correctly, but we'll
            # let QIcon load it directly. 
            # Actually, standard Lucide icons use `stroke="currentColor"`.
            # In Qt, for QIcon to auto-recolor, it must be loaded properly, or 
            # we just replace "currentColor" with "#F1F5F9" (C_TEXT) for consistency.
            svg_text = content.decode('utf-8')
            svg_text = svg_text.replace('currentColor', '#F1F5F9')
            dest.write_text(svg_text, encoding='utf-8')
    except Exception as e:
        print(f"Failed to download icon {name}: {e}")


def prefetch_icons() -> None:
    """Download all required icons in parallel so the UI is snappy."""
    _ICONS_DIR.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=5) as executor:
        for name in REQUIRED_ICONS:
            executor.submit(_ensure_icon, name)


def get_icon(name: str) -> QIcon:
    """Return a QIcon for the given Lucide icon name.
    
    If it wasn't downloaded yet, it will do it synchronously.
    """
    _ICONS_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_icon(name)
    path = _ICONS_DIR / f"{name}.svg"
    if path.exists():
        return QIcon(str(path))
    return QIcon()  # Empty fallback
