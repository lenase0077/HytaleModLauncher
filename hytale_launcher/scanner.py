from __future__ import annotations

"""CurseForge Murmur2 fingerprint scanner.

Detects .jar files in the mods folder that aren't tracked in the lockfile
and computes their CurseForge fingerprints so the API can identify them.
"""

from pathlib import Path

from hytale_launcher import lockfile_store

# Whitespace bytes stripped before hashing (CurseForge spec)
_STRIP = frozenset([9, 10, 13, 32])


def compute_fingerprint(path: Path) -> int:
    """Return the CurseForge Murmur2 fingerprint of a mod file."""
    raw = path.read_bytes()
    data = bytearray(b for b in raw if b not in _STRIP)
    return _murmur2_32(data)


def _murmur2_32(data: bytearray) -> int:
    """MurmurHash2 (32-bit) as used by CurseForge."""
    M = 0x5BD1E995
    R = 24
    length = len(data)
    h = (1 ^ length) & 0xFFFFFFFF

    i = 0
    while i + 4 <= length:
        k  = data[i]
        k |= data[i + 1] << 8
        k |= data[i + 2] << 16
        k |= data[i + 3] << 24
        k &= 0xFFFFFFFF
        k  = (k * M) & 0xFFFFFFFF
        k ^= k >> R
        k  = (k * M) & 0xFFFFFFFF
        h  = (h * M) & 0xFFFFFFFF
        h ^= k
        i += 4

    remaining = length - i
    if remaining == 3:
        h ^= data[i + 2] << 16
        h ^= data[i + 1] << 8
        h ^= data[i]
        h  = (h * M) & 0xFFFFFFFF
    elif remaining == 2:
        h ^= data[i + 1] << 8
        h ^= data[i]
        h  = (h * M) & 0xFFFFFFFF
    elif remaining == 1:
        h ^= data[i]
        h  = (h * M) & 0xFFFFFFFF

    h ^= h >> 13
    h  = (h * M) & 0xFFFFFFFF
    h ^= h >> 15
    return h & 0xFFFFFFFF


def scan_unmanaged(mods_dir: Path, lockfile: lockfile_store.Lockfile) -> list[Path]:
    """Return .jar (and .jar.disabled) files not tracked in the lockfile."""
    tracked: set[str] = set()
    for ref in lockfile.mods.values():
        tracked.add(ref.file_name)
        tracked.add(ref.file_name + lockfile_store.DISABLED_SUFFIX)

    results: list[Path] = []
    for pattern in ("*.jar", "*.jar.disabled"):
        for p in mods_dir.glob(pattern):
            if p.name not in tracked:
                results.append(p)
    return sorted(results, key=lambda p: p.name.lower())
