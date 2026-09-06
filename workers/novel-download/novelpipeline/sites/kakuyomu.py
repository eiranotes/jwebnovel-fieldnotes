from __future__ import annotations

import json
import re
from urllib.parse import quote, urlparse

from ..http import PoliteHttpClient
from ..models import Episode, WorkCandidate, WorkMetadata
from .common import attr_content, first_text, soup, text_with_ruby, unique_absolute_links


WORK_RE = re.compile(r"^/works/(\d+)")


def embedded_toc_episode_urls(doc, work_id: str) -> tuple[list[str], int | None]:
    script = doc.select_one("script#__NEXT_DATA__")
    if not script:
        return [], None
    try:
        raw = script.string or script.get_text("", strip=False)
        data = json.loads(raw)
        page_props = data.get("props", {}).get("pageProps", {})
        expected = page_props.get("additionalDataLayer", {}).get("publicEpisodeCount")
        expected_count = int(expected) if expected is not None else None
        apollo = page_props.get("__APOLLO_STATE__", {})
        work = apollo.get(f"Work:{work_id}", {})
        refs = work.get("tableOfContentsV2") or []
        episode_ids: list[str] = []
        seen: set[str] = set()
        for chapter_ref in refs:
            if not isinstance(chapter_ref, dict):
                continue
            chapter_key = str(chapter_ref.get("__ref") or "")
            chapter = apollo.get(chapter_key, {})
            for union in chapter.get("episodeUnions") or []:
                if not isinstance(union, dict):
                    continue
                ref = str(union.get("__ref") or "")
                if not ref.startswith("Episode:"):
                    continue
                episode_id = ref.split(":", 1)[1]
                if episode_id and episode_id not in seen:
                    seen.add(episode_id)
                    episode_ids.append(episode_id)
        return [f"https://kakuyomu.jp/works/{work_id}/episodes/{episode_id}" for episode_id in episode_ids], expected_count
    except (TypeError, ValueError, json.JSONDecodeError):
        return [], None


class KakuyomuSite:
    name = "kakuyomu"

    def __init__(self, http: PoliteHttpClient):
        self.http = http

    @staticmethod
    def parse_work_id(url: str) -> str | None:
        parsed = urlparse(url)
        if parsed.netloc.lower() != "kakuyomu.jp":
            return None
        match = WORK_RE.match(parsed.path)
        return match.group(1) if match else None

    @staticmethod
    def work_url(work_id: str) -> str:
        return f"https://kakuyomu.jp/works/{work_id}"

    def discover(self, query: dict) -> list[WorkCandidate]:
        if not query.get("enabled", False):
            return []
        term = str(query.get("query", "")).strip()
        if not term:
            return []
        max_pages = max(1, min(int(query.get("max_pages", 1)), 10))
        include_terms = [str(x).lower() for x in query.get("include_terms", [])]
        exclude_terms = [str(x).lower() for x in query.get("exclude_terms", [])]
        found: dict[str, WorkCandidate] = {}
        for page in range(1, max_pages + 1):
            url = f"https://kakuyomu.jp/search?q={quote(term)}&page={page}"
            doc = soup(self.http.get(url).text)
            for a in doc.select("a[href^='/works/']"):
                href = str(a.get("href", ""))
                match = WORK_RE.match(href)
                if not match:
                    continue
                work_id = match.group(1)
                text = a.get_text(" ", strip=True)
                text_lower = text.lower()
                if include_terms and not all(x in text_lower for x in include_terms):
                    continue
                if exclude_terms and any(x in text_lower for x in exclude_terms):
                    continue
                found.setdefault(
                    work_id,
                    WorkCandidate(
                        site=self.name,
                        work_id=work_id,
                        url=self.work_url(work_id),
                        title=text,
                        source_query=str(query.get("name", "kakuyomu")),
                        metadata={
                            "min_episodes": int(query.get("min_episodes", 1) or 1),
                            "include_terms": list(query.get("include_terms", [])),
                            "exclude_terms": list(query.get("exclude_terms", [])),
                        },
                    ),
                )
        return list(found.values())

    def fetch_metadata(self, work_id: str, url: str | None = None) -> WorkMetadata:
        url = url or self.work_url(work_id)
        doc = soup(self.http.get(url).text)
        title = attr_content(doc, 'meta[property="og:title"]') or first_text(doc, ["h1", "[data-testid='work-title']"])
        summary = attr_content(doc, 'meta[property="og:description"]') or attr_content(doc, 'meta[name="description"]')
        author = first_text(doc, ["a[href^='/users/']", "[data-testid='work-author']"])
        if title.endswith(" - カクヨム"):
            title = title[: -len(" - カクヨム")].rstrip()
        if author and title.endswith(f"（{author}）"):
            title = title[: -(len(author) + 2)].rstrip()
        episode_urls = unique_absolute_links(doc, "a[href*='/episodes/']", url)
        episode_urls = [u for u in episode_urls if f"/works/{work_id}/episodes/" in urlparse(u).path]
        embedded_urls, expected_count = embedded_toc_episode_urls(doc, work_id)
        toc_source = "dom"
        if len(embedded_urls) > len(episode_urls):
            episode_urls = embedded_urls
            toc_source = "next_data_apollo"
        return WorkMetadata(
            site=self.name,
            work_id=work_id,
            url=url,
            title=title,
            author=author,
            summary=summary,
            episode_urls=episode_urls,
            extra={"public_episode_count": expected_count, "toc_source": toc_source},
        )

    def fetch_episode(self, url: str, number: int) -> Episode:
        doc = soup(self.http.get(url).text)
        title = first_text(
            doc,
            [
                ".widget-episodeTitle",
                "[class*='episodeTitle']",
                "h2",
                "[data-testid='episode-title']",
                "h1",
            ],
        )
        node = None
        for selector in [
            ".widget-episodeBody",
            "div[class*='episodeBody']",
            "[data-episode-body]",
            "article",
        ]:
            node = doc.select_one(selector)
            if node:
                break
        if not node:
            raise ValueError(f"Kakuyomu episode body not found: {url}")
        text, ruby_pairs = text_with_ruby(node)
        return Episode(number=number, url=url, title=title, text=text, ruby_pairs=ruby_pairs)
