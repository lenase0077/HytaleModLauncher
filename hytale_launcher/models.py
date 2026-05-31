from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Pagination:
    index: int = 0
    page_size: int = 0
    result_count: int = 0
    total_count: int = 0

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> "Pagination":
        data = data or {}
        return cls(
            index=int(data.get("index") or 0),
            page_size=int(data.get("pageSize") or 0),
            result_count=int(data.get("resultCount") or 0),
            total_count=int(data.get("totalCount") or 0),
        )


@dataclass
class Links:
    website_url: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> "Links":
        data = data or {}
        return cls(website_url=data.get("websiteUrl"))


@dataclass
class Attachment:
    thumbnail_url: str | None = None
    url: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any] | None) -> "Attachment | None":
        if not data:
            return None
        return cls(thumbnail_url=data.get("thumbnailUrl"), url=data.get("url"))


@dataclass
class Mod:
    id: int
    name: str
    slug: str | None = None
    summary: str | None = None
    links: Links = field(default_factory=Links)
    logo: Attachment | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Mod":
        return cls(
            id=int(data.get("id") or 0),
            name=data.get("name") or "",
            slug=data.get("slug"),
            summary=data.get("summary"),
            links=Links.from_json(data.get("links")),
            logo=Attachment.from_json(data.get("logo")),
        )

    def display_url(self) -> str | None:
        if self.links.website_url:
            return self.links.website_url
        if self.slug:
            return f"https://www.curseforge.com/hytale/mods/{self.slug}"
        return None


@dataclass
class Category:
    id: int
    name: str
    is_class: bool = False
    class_id: int | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Category":
        return cls(
            id=int(data.get("id") or 0),
            name=data.get("name") or "",
            is_class=bool(data.get("isClass")),
            class_id=data.get("classId"),
        )


@dataclass
class FileDependency:
    mod_id: int
    file_id: int
    relation_type: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "FileDependency":
        return cls(
            mod_id=int(data.get("modId") or 0),
            file_id=int(data.get("fileId") or 0),
            relation_type=int(data.get("relationType") or 0),
        )

    @property
    def is_required(self) -> bool:
        return self.relation_type == 3


@dataclass
class FileHash:
    value: str
    algo: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "FileHash":
        return cls(value=data.get("value") or "", algo=int(data.get("algo") or 0))

    @property
    def is_sha1(self) -> bool:
        return self.algo == 1

    @property
    def is_md5(self) -> bool:
        return self.algo == 2


@dataclass
class ModFile:
    id: int
    mod_id: int
    is_available: bool
    display_name: str
    file_name: str
    download_url: str | None = None
    dependencies: list[FileDependency] = field(default_factory=list)
    hashes: list[FileHash] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ModFile":
        return cls(
            id=int(data.get("id") or 0),
            mod_id=int(data.get("modId") or 0),
            is_available=bool(data.get("isAvailable")),
            display_name=data.get("displayName") or data.get("fileName") or f"File {data.get('id')}",
            file_name=data.get("fileName") or f"{data.get('id')}.jar",
            download_url=data.get("downloadUrl"),
            dependencies=[FileDependency.from_json(item) for item in data.get("dependencies") or []],
            hashes=[FileHash.from_json(item) for item in data.get("hashes") or []],
        )

    def __str__(self) -> str:
        return f"{self.display_name} (id: {self.id})"


@dataclass
class ModSearchPage:
    mods: list[Mod] = field(default_factory=list)
    pagination: Pagination = field(default_factory=Pagination)


@dataclass
class FingerprintMatch:
    """A single result from the CurseForge fingerprint API."""
    fingerprint: int
    file: "ModFile"
    mod_id: int
    mod_name: str = ""
