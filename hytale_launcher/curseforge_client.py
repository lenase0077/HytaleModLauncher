from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import requests

from hytale_launcher.models import Category, FingerprintMatch, Mod, ModFile, ModSearchPage, Pagination


HYTALE_GAME_ID = 70216
HYTALE_MODS_CLASS_ID = 9137
SEARCH_PAGE_SIZE = 30
BASE_URL = "https://api.curseforge.com/v1"


class CurseForgeClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "HytaleModDownloader/0.1 (+Python requests)",
                "x-api-key": api_key,
            }
        )

    def search_mods(
        self,
        query: str,
        page: int,
        category_id: int | None,
        sort_field: int,
        sort_order: str,
    ) -> ModSearchPage:
        params: dict[str, Any] = {
            "gameId": HYTALE_GAME_ID,
            "classId": HYTALE_MODS_CLASS_ID,
            "sortField": sort_field,
            "sortOrder": sort_order,
            "pageSize": SEARCH_PAGE_SIZE,
            "index": page * SEARCH_PAGE_SIZE,
        }
        if query.strip():
            params["searchFilter"] = query.strip()
        if category_id is not None:
            params["categoryId"] = category_id

        payload = self._get(f"{BASE_URL}/mods/search?{urlencode(params)}")
        mods = [Mod.from_json(item) for item in payload.get("data") or []]
        return ModSearchPage(mods=mods, pagination=Pagination.from_json(payload.get("pagination")))

    def get_mod_categories(self) -> list[Category]:
        payload = self._get(f"{BASE_URL}/categories?gameId={HYTALE_GAME_ID}")
        categories = [Category.from_json(item) for item in payload.get("data") or []]
        return sorted(
            [
                category
                for category in categories
                if not category.is_class and category.class_id == HYTALE_MODS_CLASS_ID
            ],
            key=lambda category: category.name.lower(),
        )

    def get_mods_by_ids(self, mod_ids: list[int]) -> dict[int, Mod]:
        if not mod_ids:
            return {}
        payload = self._post(f"{BASE_URL}/mods", {"modIds": mod_ids, "filterPcOnly": True})
        mods = [Mod.from_json(item) for item in payload.get("data") or []]
        return {mod.id: mod for mod in mods}

    def get_files_for_mod(self, mod_id: int) -> list[ModFile]:
        payload = self._get(f"{BASE_URL}/mods/{mod_id}/files?pageSize=50")
        files = [ModFile.from_json(item) for item in payload.get("data") or []]
        return sorted([file for file in files if file.is_available], key=lambda file: file.id, reverse=True)

    def get_latest_file_for_mod(self, mod_id: int) -> ModFile | None:
        """Return the newest available file for a mod, or None."""
        files = self.get_files_for_mod(mod_id)
        return files[0] if files else None

    def get_mods_by_fingerprints(self, fingerprints: list[int]) -> list[FingerprintMatch]:
        """Use the CurseForge fingerprint API to identify mod files by Murmur2 hash.

        Uses the generic /fingerprints endpoint (no gameId) which is supported
        for all games. Returns an empty list on any API error so callers can
        fall back to treating unrecognized files as external mods.
        """
        if not fingerprints:
            return []
        try:
            # Generic endpoint (no gameId) — works even for pre-release games
            payload = self._post(
                f"{BASE_URL}/fingerprints",
                {"fingerprints": fingerprints},
            )
            if not isinstance(payload, dict):
                return []
            data = payload.get("data")
            if not isinstance(data, dict):
                return []
            matches: list[FingerprintMatch] = []
            for entry in data.get("exactMatches") or []:
                file_data = entry.get("file")
                if not file_data:
                    continue
                file = ModFile.from_json(file_data)
                matches.append(FingerprintMatch(
                    fingerprint=int(entry.get("id") or 0),
                    file=file,
                    mod_id=file.mod_id,
                ))
            return matches
        except Exception:
            return []

    def get_file(self, mod_id: int, file_id: int) -> ModFile | None:
        payload = self._get(f"{BASE_URL}/mods/{mod_id}/files/{file_id}")
        data = payload.get("data")
        return ModFile.from_json(data) if data else None

    def resolve_install_plan(self, root_file: ModFile) -> list[ModFile]:
        selected_by_mod_id: dict[int, ModFile] = {}
        queue = [root_file]

        while queue:
            current = queue.pop(0)
            existing = selected_by_mod_id.get(current.mod_id)
            if existing is not None and existing.id >= current.id:
                continue
            selected_by_mod_id[current.mod_id] = current

            for dependency in current.dependencies:
                if not dependency.is_required:
                    continue
                dep_file = None
                if dependency.file_id > 0:
                    dep_file = self.get_file(dependency.mod_id, dependency.file_id)
                if dep_file is None:
                    dep_files = self.get_files_for_mod(dependency.mod_id)
                    dep_file = dep_files[0] if dep_files else None
                if dep_file is not None:
                    queue.append(dep_file)

        return sorted(selected_by_mod_id.values(), key=lambda file: file.mod_id)

    def fallback_browser_download_url(self, mod: Mod | None, file: ModFile) -> str | None:
        if mod and mod.links.website_url:
            return f"{mod.links.website_url}/download/{file.id}"
        if mod and mod.slug:
            return f"https://www.curseforge.com/hytale/mods/{mod.slug}/download/{file.id}"
        return None

    def _get(self, url: str) -> dict[str, Any]:
        response = self._send_with_one_retry("GET", url)
        return self._json_or_raise(response)

    def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self._send_with_one_retry("POST", url, json=body)
        return self._json_or_raise(response)

    def _send_with_one_retry(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        response = self.session.request(method, url, timeout=60, **kwargs)
        if response.status_code != 403:
            return response
        time.sleep(0.25)
        return self.session.request(method, url, timeout=60, **kwargs)

    @staticmethod
    def _json_or_raise(response: requests.Response) -> dict[str, Any]:
        if 200 <= response.status_code < 300:
            return response.json()
        body = response.text.strip()
        if body:
            raise RuntimeError(f"CurseForge API error: HTTP {response.status_code} - {body}")
        raise RuntimeError(f"CurseForge API error: HTTP {response.status_code}")
