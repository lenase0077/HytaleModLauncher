from __future__ import annotations

import hashlib
import webbrowser
from pathlib import Path
from typing import Callable

import requests

from hytale_launcher import lockfile_store
from hytale_launcher.curseforge_client import CurseForgeClient
from hytale_launcher.models import Mod, ModFile


Logger = Callable[[str], None]


class ModInstaller:
    def __init__(self, client: CurseForgeClient) -> None:
        self.client = client
        self.session = requests.Session()

    def install_all(
        self,
        files: list[ModFile],
        mods_by_id: dict[int, Mod],
        mods_directory: Path,
        logger: Logger,
    ) -> None:
        if not files:
            logger("No hay archivos para instalar.")
            return

        mods_directory.mkdir(parents=True, exist_ok=True)
        lockfile = lockfile_store.load(mods_directory)
        installed = []

        try:
            for file in files:
                mod = mods_by_id.get(file.mod_id)
                mod_name = mod.name if mod else f"Mod {file.mod_id}"
                logger(f"Instalando {mod_name} -> {file.display_name}")

                self._remove_previous_version(mods_directory, lockfile, file.mod_id, logger)
                self._download_and_validate(file, mod, mods_directory, logger)

                lockfile.mods[file.mod_id] = lockfile_store.InstalledModRef(
                    mod_id=file.mod_id,
                    file_id=file.id,
                    file_name=file.file_name,
                )
                installed.append(file)
        finally:
            lockfile_store.save(mods_directory, lockfile)

        logger(f"Listo. Instalados/actualizados: {len(installed)} mods.")

    @staticmethod
    def _remove_previous_version(
        mods_directory: Path,
        lockfile: lockfile_store.Lockfile,
        mod_id: int,
        logger: Logger,
    ) -> None:
        previous = lockfile.mods.get(mod_id)
        if previous is None or not previous.file_name:
            return
        old_path = mods_directory / previous.file_name
        if old_path.exists():
            old_path.unlink()
            logger(f"Eliminado mod previo: {previous.file_name}")

    def _download_and_validate(
        self,
        file: ModFile,
        mod: Mod | None,
        mods_directory: Path,
        logger: Logger,
    ) -> None:
        if not file.download_url:
            browser_url = self.client.fallback_browser_download_url(mod, file)
            message = "Este archivo no permite descarga directa por API (author distribution disabled)."
            if browser_url:
                message += f" Abriendo navegador para descarga manual: {browser_url}"
                webbrowser.open(browser_url)
            raise RuntimeError(message)

        destination = mods_directory / file.file_name
        tmp = mods_directory / f"{file.file_name}.part"

        with self.session.get(file.download_url, timeout=180, stream=True) as response:
            if not 200 <= response.status_code < 300:
                raise RuntimeError(f"Error descargando {file.file_name}: HTTP {response.status_code}")
            with tmp.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        output.write(chunk)

        self._validate_hash_if_present(file, tmp)
        tmp.replace(destination)

    @staticmethod
    def _validate_hash_if_present(file: ModFile, downloaded_path: Path) -> None:
        sha1 = next((item for item in file.hashes if item.is_sha1), None)
        if sha1:
            actual = _digest(downloaded_path, "sha1")
            if actual.lower() != sha1.value.lower():
                raise RuntimeError(f"SHA1 mismatch para {file.file_name}")
            return

        md5 = next((item for item in file.hashes if item.is_md5), None)
        if md5:
            actual = _digest(downloaded_path, "md5")
            if actual.lower() != md5.value.lower():
                raise RuntimeError(f"MD5 mismatch para {file.file_name}")


def _digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()
