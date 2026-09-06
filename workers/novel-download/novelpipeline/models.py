from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class WorkCandidate:
    site: str
    work_id: str
    url: str
    title: str = ""
    author: str = ""
    summary: str = ""
    episode_count: int = 0
    source_query: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class WorkMetadata:
    site: str
    work_id: str
    url: str
    title: str
    author: str
    summary: str
    episode_urls: list[str]
    extra: dict = field(default_factory=dict)


@dataclass(slots=True)
class Episode:
    number: int
    url: str
    title: str
    text: str
    ruby_pairs: list[tuple[str, str]] = field(default_factory=list)
