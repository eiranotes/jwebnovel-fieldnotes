#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
ENTRIES = ROOT / "data" / "entries"
OUT = ROOT / "data" / "work-index.json"
REGISTRY = ROOT / "data" / "work-registry.json"
FULL_QUEUE = ROOT / "data" / "full-translation-queue.json"


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower().strip()
    return re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE)


def platform_id(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url or "")
    if "syosetu.com" in parsed.netloc:
        m = re.search(r"/([a-z]\d{4}[a-z]{2})/?", parsed.path, re.I)
        if m:
            return "narou", m.group(1).lower()
    if parsed.netloc == "kakuyomu.jp":
        m = re.search(r"/works/(\d+)", parsed.path)
        if m:
            return "kakuyomu", m.group(1)
    return None


def canonical(item: dict) -> str:
    title = norm(str(item.get("title") or ""))
    author = norm(str(item.get("author") or ""))
    if title and author:
        return f"title-author:{title}:{author}"
    pid = platform_id(str(item.get("url") or ""))
    if pid:
        return f"{pid[0]}:{pid[1]}"
    return f"title:{title}"


def candidate_rows(entry: dict):
    results = entry.get("results") or {}
    for bucket in ("shortlist", "length_exceptions", "queue", "deprioritized", "excluded"):
        for item in results.get(bucket) or []:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            yield bucket, item


def rebuild() -> dict:
    works: dict[str, dict] = {}
    for path in sorted(ENTRIES.glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        eid = entry.get("entry_id") or path.stem
        for bucket, item in candidate_rows(entry):
            key = canonical(item)
            row = works.setdefault(
                key,
                {
                    "canonical_key": key,
                    "title": item.get("title"),
                    "author": item.get("author"),
                    "platform": item.get("platform"),
                    "url": item.get("url"),
                    "length_chars": item.get("length_chars"),
                    "first_seen_entry": eid,
                    "last_seen_entry": eid,
                    "seen_count": 0,
                    "entry_ids": [],
                    "classifications": [],
                    "platform_instances": [],
                },
            )
            row["seen_count"] += 1
            if eid not in row["entry_ids"]:
                row["entry_ids"].append(eid)
            row["last_seen_entry"] = eid
            row["classifications"].append({"entry_id": eid, "bucket": bucket, "rank": item.get("rank")})
            instance = {"platform": item.get("platform"), "url": item.get("url")}
            if instance["url"] and instance not in row["platform_instances"]:
                row["platform_instances"].append(instance)
            for field in ("title", "author", "platform", "url", "length_chars"):
                if item.get(field) not in (None, ""):
                    row[field] = item.get(field)

    registry = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {"works": []}
    full_queue = json.loads(FULL_QUEUE.read_text(encoding="utf-8")) if FULL_QUEUE.exists() else {"requests": []}
    full_by_key = {x.get("canonical_key"): x for x in full_queue.get("requests", [])}
    by_url = {str(w.get("url") or ""): w for w in registry.get("works", []) if w.get("url")}
    for row in works.values():
        reg = by_url.get(str(row.get("url") or ""))
        if reg:
            row["work_id"] = reg.get("work_id")
            row["workspace"] = reg.get("workspace")
            row["pipeline_status"] = reg.get("status")
            row["chunks_done"] = reg.get("chunks_done")
            row["chunks_total"] = reg.get("chunks_total")
            row["full_translation"] = reg.get("full_translation")
        if row["canonical_key"] in full_by_key:
            req = full_by_key[row["canonical_key"]]
            row["full_translation"] = {
                "request_id": req.get("request_id"),
                "status": req.get("status"),
                "chunks_done": req.get("chunks_done", 0),
                "chunks_total": req.get("chunks_total", 0),
                "artifacts": req.get("artifacts", []),
            }

    payload = {
        "schema_version": "1.0",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "works": sorted(works.values(), key=lambda x: (norm(x.get("title") or ""), x["canonical_key"])),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = rebuild()
    print(json.dumps({"works": len(result["works"]), "updated_at": result["updated_at"]}, ensure_ascii=False))
