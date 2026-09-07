"""One place for user-visible Fieldnotes artifact names."""
from __future__ import annotations


_INVALID_FILENAME_CHARS = set('/\\:*?"<>|\r\n\t')


def safe_title_filename(title: str, *, fallback: str = "untitled", max_bytes: int = 180) -> str:
    """Keep the original Unicode title while remaining safe on macOS/Windows filesystems."""
    cleaned = "".join("_" if ch in _INVALID_FILENAME_CHARS else ch for ch in str(title or "")).strip(" ._")
    cleaned = cleaned or fallback
    encoded = cleaned.encode("utf-8")
    if len(encoded) <= max_bytes:
        return cleaned
    clipped = encoded[:max_bytes]
    while clipped:
        try:
            return clipped.decode("utf-8").rstrip(" ._") or fallback
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return fallback


def alternating_translation_filename(title: str) -> str:
    return f"{safe_title_filename(title)} - 번역본.txt"
