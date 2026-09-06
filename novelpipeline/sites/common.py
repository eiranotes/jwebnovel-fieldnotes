from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag


WHITESPACE_RE = re.compile(r"[ \t\u3000]+")
BLANKS_RE = re.compile(r"\n{3,}")


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def first_text(doc: BeautifulSoup | Tag, selectors: list[str], default: str = "") -> str:
    for selector in selectors:
        node = doc.select_one(selector)
        if node:
            value = node.get_text(" ", strip=True)
            if value:
                return value
    return default


def attr_content(doc: BeautifulSoup | Tag, selector: str, attr: str = "content") -> str:
    node = doc.select_one(selector)
    return str(node.get(attr, "")).strip() if node else ""


def text_with_ruby(node: Tag) -> tuple[str, list[tuple[str, str]]]:
    ruby_pairs: list[tuple[str, str]] = []

    def walk(cur) -> str:
        if isinstance(cur, NavigableString):
            return str(cur)
        if not isinstance(cur, Tag):
            return ""
        name = cur.name.lower() if cur.name else ""
        if name in {"script", "style"}:
            return ""
        if name == "br":
            return "\n"
        if name in {"rt", "rp"}:
            return ""
        if name == "ruby":
            reading_nodes = cur.find_all("rt")
            reading = "".join(x.get_text("", strip=True) for x in reading_nodes).strip()
            base_parts: list[str] = []
            for child in cur.children:
                if isinstance(child, Tag) and child.name and child.name.lower() in {"rt", "rp"}:
                    continue
                base_parts.append(walk(child))
            base = "".join(base_parts).strip()
            if base and reading:
                ruby_pairs.append((base, reading))
                return f"{base}《{reading}》"
            return base
        text = "".join(walk(child) for child in cur.children)
        if name in {"p", "div", "li", "section"}:
            text += "\n"
        return text

    text = walk(node).replace("\r\n", "\n").replace("\r", "\n")
    lines = [WHITESPACE_RE.sub(" ", line).rstrip() for line in text.split("\n")]
    normalized = "\n".join(lines).strip()
    normalized = BLANKS_RE.sub("\n\n", normalized)
    return normalized, ruby_pairs


def unique_absolute_links(doc: BeautifulSoup, selector: str, base_url: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for a in doc.select(selector):
        href = str(a.get("href", "")).strip()
        if not href:
            continue
        url = urljoin(base_url, href).split("#", 1)[0]
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result
