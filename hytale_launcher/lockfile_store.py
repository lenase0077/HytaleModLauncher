from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


LOCKFILE_NAME = ".hytale-mod-lock.json"

# Extension appended to a mod file when it is disabled
DISABLED_SUFFIX = ".disabled"


@dataclass
class InstalledModRef:
    mod_id: int
    file_id: int
    file_name: str
    enabled: bool = True
    mod_name: str = ""
    is_managed: bool = True   # True = installed via tool, False = externally detected

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "InstalledModRef":
        return cls(
            mod_id=int(data.get("modId") or data.get("mod_id") or 0),
            file_id=int(data.get("fileId") or data.get("file_id") or 0),
            file_name=data.get("fileName") or data.get("file_name") or "",
            enabled=bool(data.get("enabled", True)),
            mod_name=data.get("modName") or data.get("mod_name") or "",
            is_managed=bool(data.get("isManaged", True)),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "modId": self.mod_id,
            "fileId": self.file_id,
            "fileName": self.file_name,
            "enabled": self.enabled,
            "modName": self.mod_name,
            "isManaged": self.is_managed,
        }

    # ── Disk helpers ──────────────────────────────────────────────────────────
    def active_path(self, mods_dir: Path) -> Path:
        """Returns the path where the file lives on disk right now."""
        if self.enabled:
            return mods_dir / self.file_name
        return mods_dir / (self.file_name + DISABLED_SUFFIX)

    def enable(self, mods_dir: Path) -> None:
        """Rename .jar.disabled → .jar and mark enabled."""
        disabled = mods_dir / (self.file_name + DISABLED_SUFFIX)
        active = mods_dir / self.file_name
        if disabled.exists() and not active.exists():
            disabled.rename(active)
        self.enabled = True

    def disable(self, mods_dir: Path) -> None:
        """Rename .jar → .jar.disabled and mark disabled."""
        active = mods_dir / self.file_name
        disabled = mods_dir / (self.file_name + DISABLED_SUFFIX)
        if active.exists() and not disabled.exists():
            active.rename(disabled)
        self.enabled = False


@dataclass
class Lockfile:
    mods: dict[int, InstalledModRef] = field(default_factory=dict)


def load(mods_directory: Path) -> Lockfile:
    lock_path = mods_directory / LOCKFILE_NAME
    if not lock_path.exists():
        return Lockfile()

    with lock_path.open("r", encoding="utf-8") as file:
        data = json.load(file) or {}

    raw_mods = data.get("mods") or {}
    mods: dict[int, InstalledModRef] = {}
    for key, value in raw_mods.items():
        ref = InstalledModRef.from_json(value)
        mods[int(key)] = ref
    return Lockfile(mods=mods)


def save(mods_directory: Path, lockfile: Lockfile) -> None:
    mods_directory.mkdir(parents=True, exist_ok=True)
    lock_path = mods_directory / LOCKFILE_NAME
    data = {"mods": {str(mod_id): ref.to_json() for mod_id, ref in lockfile.mods.items()}}
    with lock_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
