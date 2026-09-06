from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import AppConfig
from .db import StateDB
from .models import Episode, WorkMetadata


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def work_dir(config: AppConfig, site: str, work_id: str) -> Path:
    return config.pipeline.data_dir / "works" / site / work_id


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def write_state(path: Path, *, status: str, error: str | None = None, extra: dict | None = None) -> None:
    payload = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "last_error": error,
    }
    if extra:
        payload.update(extra)
    write_json(path, payload)


def metadata_payload(meta: WorkMetadata) -> dict:
    return {
        "site": meta.site,
        "work_id": meta.work_id,
        "url": meta.url,
        "title": meta.title,
        "author": meta.author,
        "summary": meta.summary,
        "episode_urls": meta.episode_urls,
        "extra": meta.extra,
    }


def update_glossary_seed(path: Path, episodes: list[Episode]) -> None:
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {"entries": []}
    else:
        payload = {"entries": []}
    entries = payload.setdefault("entries", [])
    by_original = {str(x.get("original", "")): x for x in entries if x.get("original")}
    for ep in episodes:
        for base, reading in ep.ruby_pairs:
            if not base or not reading:
                continue
            current = by_original.get(base)
            if current:
                if not current.get("reading"):
                    current["reading"] = reading
                current.setdefault("first_seen_episode", ep.number)
            else:
                entry = {
                    "original": base,
                    "reading": reading,
                    "ko": "",
                    "type": "ruby_hint",
                    "first_seen_episode": ep.number,
                }
                entries.append(entry)
                by_original[base] = entry
    entries.sort(key=lambda x: (int(x.get("first_seen_episode", 999999)), str(x.get("original", ""))))
    write_json(path, payload)


class WorkDownloader:
    def __init__(self, config: AppConfig, db: StateDB):
        self.config = config
        self.db = db

    def save_metadata(self, meta: WorkMetadata) -> None:
        root = work_dir(self.config, meta.site, meta.work_id)
        root.mkdir(parents=True, exist_ok=True)
        payload = metadata_payload(meta)
        write_json(root / "metadata.json", payload)
        self.db.update_work(
            meta.site,
            meta.work_id,
            title=meta.title,
            author=meta.author,
            summary=meta.summary,
            episode_count=len(meta.episode_urls),
            status="METADATA_READY",
            last_error=None,
        )
        write_state(root / "state.json", status="METADATA_READY")

    def download(self, meta: WorkMetadata, site_adapter) -> list[Episode]:
        root = work_dir(self.config, meta.site, meta.work_id)
        raw_dir = root / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        wanted = meta.episode_urls[: self.config.pipeline.episodes_per_work]
        if not wanted:
            raise ValueError(f"No episodes found for {meta.url}")

        episodes: list[Episode] = []
        for number, url in enumerate(wanted, start=1):
            source_path = raw_dir / f"{number:03d}.txt"
            sidecar_path = raw_dir / f"{number:03d}.meta.json"
            old = self.db.get_episode(meta.site, meta.work_id, number)
            if old and source_path.exists() and old["url"] == url:
                text = source_path.read_text(encoding="utf-8")
                digest = sha256_text(text)
                if digest == old["source_sha256"]:
                    title = old["title"]
                    pairs: list[tuple[str, str]] = []
                    if sidecar_path.exists():
                        try:
                            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
                            title = str(sidecar.get("title", title))
                            pairs = [
                                tuple(x)
                                for x in sidecar.get("ruby_pairs", [])
                                if isinstance(x, list) and len(x) == 2
                            ]
                        except Exception:
                            pairs = []
                    episodes.append(
                        Episode(
                            number=number,
                            url=url,
                            title=title,
                            text=text.rstrip("\n"),
                            ruby_pairs=pairs,
                        )
                    )
                    continue

            ep = site_adapter.fetch_episode(url, number)
            source_path.write_text(ep.text.rstrip() + "\n", encoding="utf-8")
            digest = sha256_text(ep.text.rstrip() + "\n")
            write_json(
                sidecar_path,
                {
                    "number": number,
                    "url": ep.url,
                    "title": ep.title,
                    "source_sha256": digest,
                    "ruby_pairs": [[base, reading] for base, reading in ep.ruby_pairs],
                },
            )
            self.db.upsert_episode(
                site=meta.site,
                work_id=meta.work_id,
                number=number,
                url=url,
                title=ep.title,
                source_sha256=digest,
                source_path=str(source_path.resolve()),
            )
            episodes.append(ep)

        merged_dir = root / "merged"
        merged_dir.mkdir(parents=True, exist_ok=True)
        count = len(episodes)
        merged_path = merged_dir / f"original_001-{count:03d}.txt"
        parts: list[str] = []
        for ep in episodes:
            heading = f"===== {ep.number:03d}. {ep.title or 'Episode'} ====="
            parts.append(f"{heading}\nURL: {ep.url}\n\n{ep.text.strip()}")
        merged_path.write_text("\n\n".join(parts).rstrip() + "\n", encoding="utf-8")
        update_glossary_seed(root / "glossary.json", episodes)
        self.db.update_work(meta.site, meta.work_id, status="DOWNLOADED", last_error=None)
        write_state(
            root / "state.json",
            status="DOWNLOADED",
            extra={"downloaded_episodes": count, "merged_source": str(merged_path.relative_to(root))},
        )
        return episodes
