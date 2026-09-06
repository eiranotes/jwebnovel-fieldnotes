from __future__ import annotations

import re
from urllib.parse import urlparse

from ..http import PoliteHttpClient
from ..models import Episode, WorkCandidate, WorkMetadata
from .common import attr_content, first_text, soup, text_with_ruby, unique_absolute_links


NCODE_RE = re.compile(r"^/([a-zA-Z]\d{4}[a-zA-Z]{2})/?")


class NarouSite:
    name = "narou"
    api_url = "https://api.syosetu.com/novelapi/api/"

    def __init__(self, http: PoliteHttpClient):
        self.http = http

    @staticmethod
    def parse_work_id(url: str) -> str | None:
        host = urlparse(url).netloc.lower()
        if "syosetu.com" not in host:
            return None
        match = NCODE_RE.match(urlparse(url).path)
        return match.group(1).lower() if match else None

    @staticmethod
    def work_url(work_id: str) -> str:
        return f"https://ncode.syosetu.com/{work_id.lower()}/"

    def discover(self, query: dict) -> list[WorkCandidate]:
        if not query.get("enabled", False):
            return []
        params = {
            "out": "json",
            "lim": min(int(query.get("limit", 50)), 500),
            "order": query.get("order", "weeklypoint"),
            "word": query.get("word", ""),
            "notword": query.get("notword", ""),
        }
        genre = int(query.get("genre", 0) or 0)
        if genre:
            params["genre"] = genre
        data = self.http.get(self.api_url, params=params).json()
        rows = data[1:] if data and isinstance(data[0], dict) and "allcount" in data[0] else data
        result: list[WorkCandidate] = []
        min_episodes = int(query.get("min_episodes", 1))
        min_points = int(query.get("min_total_points", 0))
        min_bookmarks = int(query.get("min_bookmarks", 0))
        for row in rows:
            episodes = int(row.get("general_all_no", 0) or 0)
            points = int(row.get("global_point", 0) or 0)
            bookmarks = int(row.get("fav_novel_cnt", 0) or 0)
            if episodes < min_episodes or points < min_points or bookmarks < min_bookmarks:
                continue
            work_id = str(row.get("ncode", "")).lower()
            if not work_id:
                continue
            result.append(
                WorkCandidate(
                    site=self.name,
                    work_id=work_id,
                    url=self.work_url(work_id),
                    title=str(row.get("title", "")),
                    author=str(row.get("writer", "")),
                    summary=str(row.get("story", "")),
                    episode_count=episodes,
                    source_query=str(query.get("name", "narou")),
                    metadata=row,
                )
            )
        return result

    def fetch_metadata(self, work_id: str, url: str | None = None) -> WorkMetadata:
        url = url or self.work_url(work_id)
        doc = soup(self.http.get(url).text)
        title = first_text(doc, ["h1.p-novel__title", ".novel_title", "h1"])
        author = first_text(doc, [".p-novel__author", ".novel_writername"])
        author = re.sub(r"^作者[:：]\s*", "", author).strip()
        summary = first_text(doc, [".p-novel__summary", "#novel_ex"]) or attr_content(doc, 'meta[name="description"]')
        episode_urls = unique_absolute_links(
            doc,
            "a.p-eplist__subtitle, .novel_sublist2 a, a[href*='/{}/']".format(work_id),
            url,
        )
        episode_urls = [u for u in episode_urls if re.search(rf"/{re.escape(work_id)}/\d+/?$", urlparse(u).path)]
        if not episode_urls:
            # Short stories may have the body directly on the work URL.
            body = doc.select_one(".p-novel__text--body, #novel_honbun")
            if body:
                episode_urls = [url]
        return WorkMetadata(
            site=self.name,
            work_id=work_id,
            url=url,
            title=title,
            author=author,
            summary=summary,
            episode_urls=episode_urls,
        )

    def fetch_episode(self, url: str, number: int) -> Episode:
        doc = soup(self.http.get(url).text)
        title = first_text(doc, [".p-novel__subtitle", ".novel_subtitle", "h1"])
        body_nodes = doc.select(".p-novel__text--body")
        if not body_nodes:
            body_nodes = doc.select("#novel_honbun")
        if not body_nodes:
            body_nodes = doc.select(".p-novel__text")
        if not body_nodes:
            raise ValueError(f"Narou episode body not found: {url}")
        parts: list[str] = []
        ruby_pairs: list[tuple[str, str]] = []
        for node in body_nodes:
            text, rubies = text_with_ruby(node)
            if text:
                parts.append(text)
            ruby_pairs.extend(rubies)
        return Episode(number=number, url=url, title=title, text="\n\n".join(parts).strip(), ruby_pairs=ruby_pairs)
