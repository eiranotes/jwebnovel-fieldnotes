from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .http import PoliteHttpClient
from .sites.kakuyomu import KakuyomuSite
from .sites.narou import NarouSite


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _resolve_site(url: str, http: PoliteHttpClient):
    for cls in (NarouSite, KakuyomuSite):
        work_id = cls.parse_work_id(url)
        if work_id:
            return cls(http), work_id
    raise ValueError(f"Unsupported Narou/Kakuyomu work URL: {url}")


def export_work(
    *,
    url: str,
    output_dir: str | Path,
    episodes: int = 5,
    delay_seconds: float = 1.5,
    timeout_seconds: float = 30.0,
    user_agent: str = "novel-daily-pipeline/0.2 (personal automation)",
    force: bool = False,
) -> dict:
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "acquisition_manifest.json"

    requested_mode = "all" if int(episodes) <= 0 else "first_n"
    existing: dict = {}
    reusable_by_url: dict[str, dict] = {}
    if not force and manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            files = [output / x["file"] for x in existing.get("episodes", [])]
            if existing.get("url") == url:
                reusable_by_url = {
                    str(x.get("url")): x
                    for x in existing.get("episodes", [])
                    if x.get("url") and x.get("file") and (output / str(x["file"])).is_file()
                }
            if (
                existing.get("url") == url
                and existing.get("requested_mode", "first_n") == requested_mode
                and (
                    requested_mode == "all"
                    or int(existing.get("requested_episodes", 0)) == int(episodes)
                )
                and files
                and all(path.exists() for path in files)
                and (
                    requested_mode != "all"
                    or int(existing.get("acquired_episodes", 0)) == int(existing.get("available_episodes", 0))
                )
            ):
                return {**existing, "reused": True}
        except Exception:
            pass

    http = PoliteHttpClient(
        user_agent=user_agent,
        delay_seconds=delay_seconds,
        timeout_seconds=timeout_seconds,
    )
    site, work_id = _resolve_site(url, http)
    meta = site.fetch_metadata(work_id, url)
    expected_count = int(meta.extra.get("public_episode_count") or 0) if meta.extra else 0
    if requested_mode == "all" and expected_count and len(meta.episode_urls) != expected_count:
        raise RuntimeError(
            f"Full episode list incomplete for {url}: expected {expected_count}, found {len(meta.episode_urls)}"
        )
    wanted = list(meta.episode_urls) if int(episodes) <= 0 else meta.episode_urls[: max(1, int(episodes))]
    if not wanted:
        raise RuntimeError(f"No readable episodes found for {url}")

    episode_rows: list[dict] = []
    ruby_map: dict[str, str] = dict(existing.get("ruby_notes") or {}) if existing.get("url") == url and not force else {}

    def checkpoint(*, complete: bool) -> dict:
        manifest = {
            "schema_version": "1.0",
            "acquisition_mode": "public_reader_page_capture",
            "site": meta.site,
            "work_id": meta.work_id,
            "url": meta.url,
            "title": meta.title,
            "author": meta.author,
            "summary": meta.summary,
            "requested_mode": requested_mode,
            "requested_episodes": "all" if requested_mode == "all" else int(episodes),
            "available_episodes": len(meta.episode_urls),
            "acquired_episodes": len(episode_rows),
            "episodes": episode_rows,
            "ruby_notes": ruby_map,
            "acquired_at": datetime.now(timezone.utc).isoformat(),
            "complete": complete,
            "reused": False,
        }
        _write_json(manifest_path, manifest)
        return manifest

    for number, episode_url in enumerate(wanted, start=1):
        reusable = reusable_by_url.get(episode_url)
        if reusable:
            row = dict(reusable)
            row["number"] = number
            episode_rows.append(row)
            checkpoint(complete=False)
            continue
        episode = site.fetch_episode(episode_url, number)
        title = episode.title or f"Episode {number}"
        payload = (
            f"===== {number:03d}. {title} =====\n"
            f"URL: {episode_url}\n\n"
            f"{episode.text.strip()}\n"
        )
        filename = f"{number:03d}.txt"
        path = output / filename
        path.write_text(payload, encoding="utf-8")
        for base, reading in episode.ruby_pairs:
            if not base or not reading:
                continue
            if set(reading) <= {"・", "･", ".", "·"}:
                continue
            if base not in ruby_map:
                ruby_map[base] = reading
        episode_rows.append(
            {
                "number": number,
                "title": title,
                "url": episode_url,
                "file": filename,
                "chars": len(payload),
                "sha256": _sha256_text(payload),
            }
        )
        checkpoint(complete=False)

    return checkpoint(complete=True)
