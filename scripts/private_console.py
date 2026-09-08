#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import mimetypes
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from xml.sax.saxutils import escape as xml_escape

from automation_log import log_event
from artifact_naming import alternating_translation_filename
from preference_atoms import ATOMIZER_VERSION, extract_note_atoms
from preference_feedback import review_id
from preference_state import state_lock, save, digest
from rebuild_work_index import canonical


ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / "config" / "search-profiles.json"
AUTOMATION = ROOT / "config" / "automation.json"
WORK_INDEX = ROOT / "data" / "work-index.json"
FULL_QUEUE = ROOT / "data" / "full-translation-queue.json"
LOGS = ROOT / "data" / "automation-logs.json"
ROTATION = ROOT / "data" / "profile-rotation-state.json"
REGISTRY = ROOT / "data" / "work-registry.json"
PREFERENCE_FEEDBACK = ROOT / "workspace" / "preference-feedback.json"
PREFERENCE_MODEL = ROOT / "workspace" / "preference-model.json"
PREFERENCE_HISTORY = ROOT / "workspace" / "preference-learning-history.json"
DAILY_TASTE = ROOT / "workspace" / "daily-taste-state.json"
ENTRIES = ROOT / "data" / "entries"
SAFE_STATIC_FILES = {"/", "/index.html", "/taste.html", "/taste.js", "/console.html", "/styles.css", "/archive.js", "/console.js", "/.nojekyll"}
SAFE_STATIC_ROOTS = ("entries", "docs", "data")


def load(path: Path, fallback):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def atomic_write(path: Path, data) -> None:
    save(path,data)


def profile_document() -> dict:
    data=load(PROFILES,{})
    return {**data,'_revision':digest(data)}


def save_profiles(body: dict) -> dict:
    with state_lock(ROOT/'workspace'):
        incoming=dict(body);expected=incoming.pop('_revision',None)
        if expected!=digest(load(PROFILES,{})):
            raise ValueError('Profiles changed since this page loaded; reload before saving')
        save(PROFILES,validate_profiles(incoming))
        return profile_document()


def update_selection(body: dict) -> dict:
    with state_lock(ROOT/'workspace'):
        data=load(PROFILES,{})
        if body.get('profile_revision')!=digest(data):
            raise ValueError('Profiles changed since this page loaded; reload before saving selection')
        selection=data.setdefault('selection',{})
        valid={p.get('profile_id') for p in data.get('profiles',[]) if p.get('enabled')}
        selection['selected_profile_ids']=[x for x in body.get('selected_profile_ids',[]) if x in valid]
        if body.get('explicit_selection_mode') in {'once','sticky'}:selection['explicit_selection_mode']=body['explicit_selection_mode']
        if body.get('when_none') in {'round_robin','least_recently_run','random_daily','all_enabled'}:selection['when_none']=body['when_none']
        if body.get('rotation_batch_size') is not None:selection['rotation_batch_size']=max(1,int(body['rotation_batch_size']))
        save(PROFILES,data)
        return {**selection,'_profiles_revision':digest(data)}


def json_response(handler, status: int, payload) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def validate_profiles(data: dict) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), list):
        raise ValueError("profiles must be an array")
    seen = set()
    for profile in data["profiles"]:
        pid = str(profile.get("profile_id") or "").strip()
        name = str(profile.get("name") or "").strip()
        if not pid or not name:
            raise ValueError("Each profile requires profile_id and name")
        if pid in seen:
            raise ValueError(f"Duplicate profile_id: {pid}")
        seen.add(pid)
        profile["profile_id"] = pid
        profile["name"] = name
        refs = profile.get("reference_works") or []
        if not isinstance(refs, list):
            raise ValueError("reference_works must be an array")
        normalized_refs = []
        for ref in refs:
            if isinstance(ref, dict):
                title = str(ref.get("title") or "").strip()
                url = str(ref.get("url") or "").strip()
                if title or url:
                    normalized_refs.append({k:v for k,v in (("title",title),("url",url)) if v})
                continue
            value = str(ref or "").strip()
            if not value:
                continue
            if value.startswith("https://") and normalized_refs and isinstance(normalized_refs[-1], str):
                normalized_refs[-1] = {"title": normalized_refs[-1], "url": value}
            else:
                normalized_refs.append(value)
        profile["reference_works"] = normalized_refs
        hard = profile.setdefault("hard_filters", {})
        hard["min_chars"] = max(0, int(hard.get("min_chars", data.get("defaults", {}).get("min_chars", 300000)) or 0))
        profile.setdefault("output", {})["shortlist_count"] = max(1, int(profile.get("output", {}).get("shortlist_count", 10) or 10))
    selected = data.setdefault("selection", {}).setdefault("selected_profile_ids", [])
    data["selection"]["selected_profile_ids"] = [x for x in selected if x in seen]
    data["criteria_ready"] = any(bool(p.get("enabled")) for p in data["profiles"])
    return data


def artifact_inventory() -> list[dict]:
    rows: list[dict] = []
    registry = load(REGISTRY, {"works": []})
    for work in registry.get("works", []):
        workspace = work.get("workspace")
        if workspace:
            output_dir = (ROOT / workspace / "translation" / "output").resolve()
            if output_dir.is_dir():
                title = str(work.get("title") or work.get("work_id") or "untitled")
                expected = (output_dir / alternating_translation_filename(title)).resolve()
                candidates = [expected] if expected.is_file() else sorted(output_dir.glob("* - 번역본.txt"))
                for target in candidates[:1]:
                    target = target.resolve()
                    if not target.is_file() or not target.is_relative_to(output_dir):
                        continue
                    rows.append({
                        "kind": "alternating_translation",
                        "title": work.get("title"),
                        "work_id": work.get("work_id"),
                        "path": str(target.relative_to(ROOT)),
                        "filename": target.name,
                        "size": target.stat().st_size,
                    })
    full = load(FULL_QUEUE, {"requests": []})
    for request in full.get("requests", []):
        for rel in request.get("artifacts") or []:
            target = (ROOT / rel).resolve()
            if target.is_file() and target.name.endswith(" - 번역본.txt"):
                rows.append({
                    "kind": "alternating_translation",
                    "title": request.get("title"),
                    "work_id": request.get("work_id"),
                    "path": str(target.relative_to(ROOT)),
                    "filename": target.name,
                    "size": target.stat().st_size,
                })
    unique = {row["path"]: row for row in rows}
    return sorted(unique.values(), key=lambda x: (str(x.get("title") or ""), x["kind"], x["filename"]))


def state_payload() -> dict:
    with state_lock(ROOT / "workspace"):
        return _state_payload()


def _state_payload() -> dict:
    return {
        "profiles": profile_document(),
        "automation": load(AUTOMATION, {}),
        "work_index": load(WORK_INDEX, {"works": []}),
        "full_translation": load(FULL_QUEUE, {"requests": []}),
        "logs": load(LOGS, {"entries": []}),
        "rotation": load(ROTATION, {}),
        "artifacts": artifact_inventory(),
        "preference_feedback": load(PREFERENCE_FEEDBACK, {"events": []}),
        "preference_model": load(PREFERENCE_MODEL, {"profiles": {}}),
        "preference_history": load(PREFERENCE_HISTORY, {"snapshots": []}),
        "console": {"writable": True, "root": str(ROOT)},
    }


def refresh_index() -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "rebuild_work_index.py")], cwd=ROOT, check=True, text=True, capture_output=True)


def taste_state() -> dict:
    return load(DAILY_TASTE, {"schema_version": "1.0", "updated_at": None, "responses": []})


def available_taste_dates() -> list[str]:
    dates = set()
    for path in ENTRIES.glob("*.json"):
        try:
            entry = load(path, {})
            if entry.get("date") and any((entry.get("results") or {}).get(bucket) for bucket in ("shortlist", "length_exceptions")):
                dates.add(str(entry["date"]))
        except Exception:
            continue
    return sorted(dates, reverse=True)


def taste_deck(date: str | None = None) -> dict:
    dates = available_taste_dates()
    if not date:
        date = dates[0] if dates else None
    if not date:
        return {"date": None, "available_dates": [], "items": [], "completed_count": 0, "pool_count": 0}
    state = taste_state()
    responses = {(x.get("entry_id"), x.get("canonical_key"), x.get("profile_id")): x for x in state.get("responses", [])}
    registry = load(REGISTRY, {"works": []})
    registry_by_key = {canonical(w): w for w in registry.get("works", []) if w.get("title")}
    by_key: dict[str, dict] = {}
    pool_count = 0
    for path in sorted(ENTRIES.glob(f"{date}-*.json")):
        entry = load(path, {})
        if str(entry.get("date") or "") != date:
            continue
        profile_id = entry.get("search_profile_id") or entry.get("profile_id")
        results = entry.get("results") or {}
        for bucket in ("shortlist", "length_exceptions"):
            for item in results.get(bucket) or []:
                if not isinstance(item, dict) or not item.get("title"):
                    continue
                pool_count += 1
                key = canonical(item)
                row = by_key.setdefault((entry.get("entry_id") or path.stem, key), {
                    "review_key": review_id(key, profile_id, entry.get("entry_id") or path.stem),
                    "canonical_key": key,
                    "title": item.get("title"), "author": item.get("author"), "platform": item.get("platform"),
                    "url": item.get("url"), "length_chars": item.get("length_chars"), "episodes": item.get("episodes"),
                    "rank": item.get("rank"), "preference_rank": item.get("preference_rank"), "why": item.get("why"), "difference": item.get("difference"),
                    "entry_id": entry.get("entry_id") or path.stem, "entry_ids": [], "entry_title": entry.get("title"),
                    "profile_id": profile_id, "bucket": bucket,
                })
                eid = entry.get("entry_id") or path.stem
                if eid not in row["entry_ids"]:
                    row["entry_ids"].append(eid)
                for field in ("author", "platform", "url", "length_chars", "episodes", "rank", "why", "difference"):
                    if item.get(field) not in (None, ""):
                        row[field] = item.get(field)
    items = []
    for row in by_key.values():
        reg = registry_by_key.get(row["canonical_key"])
        sample_available = False
        if reg and reg.get("workspace"):
            workspace = (ROOT / reg["workspace"]).resolve()
            title = str(reg.get("title") or row.get("title") or reg.get("work_id") or "untitled")
            alternating = (workspace / "translation" / "output" / alternating_translation_filename(title)).resolve()
            sample_available = alternating.is_file() and alternating.is_relative_to(workspace) and alternating.stat().st_size > 0
            row["work_id"] = reg.get("work_id")
        row["sample_available"] = sample_available
        response = responses.get((row["entry_id"], row["canonical_key"], row["profile_id"]))
        if response and response.get("atomizer_version") != ATOMIZER_VERSION and response.get("note"):
            response = dict(response)
            response["atoms"] = extract_note_atoms(str(response.get("note") or ""))
            response["atomizer_version"] = ATOMIZER_VERSION
        row["response"] = response
        if sample_available:
            items.append(row)
    def rank_key(row: dict):
        if row.get('preference_rank') is not None:return (0,0,row['preference_rank'],row['entry_id'])
        rank = str(row.get("rank") or "Z")
        group = 0 if rank.startswith("A") else 1 if rank.startswith("B") else 2
        exception = 1 if "-LE" in rank else 0
        digits = "".join(ch for ch in rank if ch.isdigit())
        return group, exception, int(digits or 99), str(row.get("title") or "")
    items.sort(key=rank_key)
    return {
        "date": date,
        "available_dates": dates,
        "items": items,
        "completed_count": sum(1 for x in items if x.get("response")),
        "pool_count": pool_count,
    }


def taste_sample(date: str, canonical_key: str, start: int = 0, limit: int = 6500) -> dict:
    item = next((x for x in taste_deck(date).get("items", []) if canonical_key in (x.get("canonical_key"), x.get("review_key"))), None)
    if not item:
        raise ValueError("work is not in the selected daily taste deck")
    canonical_key = item["canonical_key"]
    registry = load(REGISTRY, {"works": []})
    reg = next((w for w in registry.get("works", []) if w.get("title") and canonical(w) == canonical_key), None)
    if not reg or not reg.get("workspace"):
        raise ValueError("local sample is not available")
    workspace = (ROOT / reg["workspace"]).resolve()
    title = str(reg.get("title") or item.get("title") or reg.get("work_id") or "untitled")
    source = (workspace / "translation" / "output" / alternating_translation_filename(title)).resolve()
    if not source.is_file() or not source.is_relative_to(workspace):
        raise ValueError("completed alternating translation is not available")
    text = source.read_text(encoding="utf-8")
    start = max(0, min(int(start), len(text)))
    end = min(len(text), start + max(500, min(int(limit), 8000)))
    return {
        "canonical_key": canonical_key, "date": date, "start": start, "end": end, "total": len(text),
        "has_more": end < len(text), "reading_mode": "alternating", "text": text[start:end],
    }



def _taste_registry_by_key() -> dict[str, dict]:
    registry = load(REGISTRY, {"works": []})
    return {canonical(w): w for w in registry.get("works", []) if w.get("title")}


def _taste_work_text(item: dict, registry_by_key: dict[str, dict]) -> tuple[str, str] | None:
    reg = registry_by_key.get(str(item.get("canonical_key") or ""))
    if not reg or not reg.get("workspace"):
        return None
    workspace = (ROOT / reg["workspace"]).resolve()
    title = str(reg.get("title") or item.get("title") or reg.get("work_id") or "untitled")
    alternating = (workspace / "translation" / "output" / alternating_translation_filename(title)).resolve()
    if alternating.is_file() and alternating.is_relative_to(workspace) and alternating.stat().st_size > 0:
        return alternating.read_text(encoding="utf-8"), "JA/KO"
    return None


def taste_reading_files(date: str) -> list[dict]:
    deck = taste_deck(date)
    registry_by_key = _taste_registry_by_key()
    rows = []
    for index, item in enumerate(deck.get("items") or [], 1):
        resolved = _taste_work_text(item, registry_by_key)
        if not resolved:
            continue
        text, language = resolved
        header = (
            f"FIELD NOTES DAILY TASTE · {date}\n"
            f"{index:02d}. {item.get('title') or ''}\n"
            f"작가: {item.get('author') or '-'}\n"
            f"플랫폼: {item.get('platform') or '-'} · 추천등급: {item.get('rank') or '-'} · 본문: {language}\n"
            f"원문: {item.get('url') or '-'}\n"
            + "=" * 72 + "\n\n"
        )
        body = header + text.strip() + "\n"
        filename = alternating_translation_filename(str(item.get("title") or "untitled"))
        rows.append({"filename": filename, "body": body, "language": language, "item": item})
    return rows


def taste_bundle(date: str, fmt: str = "txt") -> tuple[bytes, str, str]:
    rows = taste_reading_files(date)
    if not rows:
        raise ValueError("no completed alternating translations for this date")
    combined_parts = [
        f"FIELD NOTES · 오늘의 추천 소설 · {date}\n",
        f"교차 번역 완료 {len(rows)}편\n",
        "원문/한국어 번역을 문장 단위로 교차 표시합니다.\n",
        "#" * 72 + "\n",
    ]
    for row in rows:
        combined_parts.append("\n\n" + row["body"] + "\n")
    combined = "".join(combined_parts).encode("utf-8")
    stem = f"fieldnotes-{date}-daily-taste-ja-ko"
    if fmt == "txt":
        return combined, f"{stem}.txt", "text/plain; charset=utf-8"
    if fmt == "zip":
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("00_오늘추천_교차번역_통합.txt", combined)
            for row in rows:
                archive.writestr(row["filename"], row["body"].encode("utf-8"))
        return buffer.getvalue(), f"{stem}.zip", "application/zip"
    raise ValueError("format must be txt or zip")


def _content_disposition(filename: str) -> str:
    return f"attachment; filename=fieldnotes-daily; filename*=UTF-8''{quote(filename)}"


def _dav_date_and_name(path: str) -> tuple[str | None, str | None]:
    decoded = unquote(path).rstrip("/")
    if decoded == "/dav":
        return None, None
    if not decoded.startswith("/dav/"):
        return None, None
    rest = decoded[len("/dav/"):]
    parts = rest.split("/", 1)
    return (parts[0] or None), (parts[1] if len(parts) > 1 else None)


def _dav_file_map(date: str) -> dict[str, tuple[bytes, str]]:
    rows = taste_reading_files(date)
    files: dict[str, tuple[bytes, str]] = {}
    if rows:
        combined, _, _ = taste_bundle(date, "txt")
        files["00_오늘추천_교차번역_통합.txt"] = (combined, "text/plain; charset=utf-8")
    for row in rows:
        files[row["filename"]] = (row["body"].encode("utf-8"), "text/plain; charset=utf-8")
    return files


def dav_resource(path: str):
    date, name = _dav_date_and_name(path)
    decoded = unquote(path).rstrip("/")
    if decoded == "/dav":
        return {"collection": True, "display": "Field Notes", "date": None, "name": None}
    if date and name is None and date in available_taste_dates():
        return {"collection": True, "display": date, "date": date, "name": None}
    if date and name:
        files = _dav_file_map(date)
        if name in files:
            data, mime = files[name]
            return {"collection": False, "display": name, "date": date, "name": name, "data": data, "mime": mime}
    return None


def dav_children(path: str) -> list[dict]:
    decoded = unquote(path).rstrip("/")
    if decoded == "/dav":
        return [{"path": f"/dav/{date}/", "collection": True, "display": date} for date in available_taste_dates()]
    resource = dav_resource(path)
    if resource and resource.get("collection") and resource.get("date"):
        date = resource["date"]
        base = decoded + "/"
        return [
            {"path": base + name, "collection": False, "display": name, "data": data, "mime": mime}
            for name, (data, mime) in _dav_file_map(date).items()
        ]
    return []


def dav_multistatus(path: str, depth: str = "1") -> bytes:
    resource = dav_resource(path)
    if not resource:
        raise FileNotFoundError(path)
    decoded = unquote(path).rstrip("/") or "/dav"
    base_path = decoded + ("/" if resource.get("collection") else "")
    nodes = [{"path": base_path, **resource}]
    if str(depth) != "0" and resource.get("collection"):
        nodes.extend(dav_children(path))
    responses = []
    for node in nodes:
        href = quote("/fieldnotes" + node["path"], safe="/")
        collection = bool(node.get("collection"))
        length = 0 if collection else len(node.get("data") or b"")
        content_type = "httpd/unix-directory" if collection else node.get("mime", "application/octet-stream")
        resource_type = "<D:collection/>" if collection else ""
        responses.append(
            "<D:response>"
            f"<D:href>{xml_escape(href)}</D:href>"
            "<D:propstat><D:prop>"
            f"<D:displayname>{xml_escape(str(node.get('display') or ''))}</D:displayname>"
            f"<D:resourcetype>{resource_type}</D:resourcetype>"
            f"<D:getcontentlength>{length}</D:getcontentlength>"
            f"<D:getcontenttype>{xml_escape(content_type)}</D:getcontenttype>"
            "</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat>"
            "</D:response>"
        )
    xml = '<?xml version="1.0" encoding="utf-8"?><D:multistatus xmlns:D="DAV:">' + "".join(responses) + "</D:multistatus>"
    return xml.encode("utf-8")



def save_taste_response(body: dict) -> dict:
    date = str(body.get("date") or "").strip()
    key = str(body.get("canonical_key") or "").strip()
    verdict = str(body.get("verdict") or "").strip()
    if not date or not key or verdict not in {"love", "like", "neutral", "dislike", "exclude"}:
        raise ValueError("date, canonical_key and a valid verdict are required")
    deck = taste_deck(date)
    item = next((x for x in deck.get("items", []) if x.get("canonical_key") == key and x.get("entry_id") == body.get("entry_id")), None)
    if not item:
        raise ValueError("work is not in the selected daily taste deck")
    reasons = [str(x).strip() for x in body.get("reasons") or [] if str(x).strip()]
    tags = [str(x).strip()[:80] for x in body.get("tags") or [] if str(x).strip()]
    note = str(body.get("note") or "").strip()
    profile_id = str(body.get("profile_id", item.get("profile_id")) or "").strip() or None
    stamp = datetime.now(timezone.utc).isoformat()
    response = {
        "date": date, "canonical_key": key, "entry_id": body.get("entry_id") or item.get("entry_id"),
        "profile_id": profile_id, "verdict": verdict, "reasons": reasons, "tags": tags, "note": note,
        "atoms": extract_note_atoms(note), "atomizer_version": ATOMIZER_VERSION,
        "read_chars": max(0, int(body.get("read_chars") or 0)), "updated_at": stamp,
    }
    cmd = [
        sys.executable, str(ROOT / "scripts" / "preference_feedback.py"), "record",
        "--key", key, "--verdict", verdict, "--reasons", ",".join(reasons), "--tags", ",".join(tags),
        "--note", note, "--read-chars", str(response["read_chars"]), "--source", "daily_taste", "--external-id", f"daily_taste:{date}:{key}",
        "--context", str(response.get("entry_id") or ""), "--recommended-rank", str(item.get("rank") or ""),
    ]
    if profile_id:
        cmd += ["--profile", profile_id]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    log_event(task="daily_taste", action="respond", status="done", message=f"Taste response: {verdict}", public_details={"date": date, "verdict": verdict})
    return {**json.loads(proc.stdout), "date": date, "entry_id": item["entry_id"]}


def safe_static_request_path(path: str) -> str | None:
    decoded = unquote(path)
    if decoded == "/":
        return "/index.html"
    if decoded in SAFE_STATIC_FILES:
        target = (ROOT / decoded.lstrip("/")).resolve()
        return decoded if target.is_file() else None
    target = (ROOT / decoded.lstrip("/")).resolve()
    if not target.is_file():
        return None
    for rel in SAFE_STATIC_ROOTS:
        allowed_root = (ROOT / rel).resolve()
        if target.is_relative_to(allowed_root):
            return "/" + target.relative_to(ROOT).as_posix()
    return None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        return

    def _body(self):
        size = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(size) if size else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _parsed_route(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/fieldnotes":
            path = "/"
        elif path.startswith("/fieldnotes/"):
            path = path[len("/fieldnotes"):]
        return parsed, path

    def do_GET(self):
        parsed, path = self._parsed_route()
        if path == "/api/state":
            return json_response(self, 200, state_payload())
        if path == "/api/taste/today":
            query = parse_qs(parsed.query)
            return json_response(self, 200, taste_deck((query.get("date") or [None])[0]))
        if path == "/api/taste/read":
            query = parse_qs(parsed.query)
            date = (query.get("date") or [""])[0]
            key = (query.get("key") or [""])[0]
            start = int((query.get("start") or [0])[0])
            return json_response(self, 200, taste_sample(date, key, start=start))
        if path == "/api/taste/bundle":
            query = parse_qs(parsed.query)
            date = (query.get("date") or [""])[0]
            fmt = (query.get("format") or ["txt"])[0]
            data, filename, mime = taste_bundle(date, fmt)
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Disposition", _content_disposition(filename))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if path.startswith("/dav"):
            resource = dav_resource(path)
            if not resource or resource.get("collection"):
                return json_response(self, 404, {"error": "WebDAV file not found"})
            data = resource["data"]
            self.send_response(200)
            self.send_header("Content-Type", resource["mime"])
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/download":
            query = parse_qs(parsed.query)
            rel = (query.get("path") or [""])[0]
            target = (ROOT / rel).resolve()
            allowed = {(ROOT / row["path"]).resolve() for row in artifact_inventory()}
            if target not in allowed or not target.is_file():
                return json_response(self, 404, {"error": "file not available"})
            mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Disposition", _content_disposition(target.name))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        safe_path = safe_static_request_path(path)
        if not safe_path:
            return json_response(self, 404, {"error": "not available from private console"})
        self.path = safe_path
        return super().do_GET()

    def do_OPTIONS(self):
        _, path = self._parsed_route()
        if path.startswith("/dav"):
            self.send_response(200)
            self.send_header("Allow", "OPTIONS, GET, HEAD, PROPFIND")
            self.send_header("DAV", "1")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, POST, OPTIONS")
        self.end_headers()

    def do_PROPFIND(self):
        _, path = self._parsed_route()
        if not path.startswith("/dav"):
            return json_response(self, 404, {"error": "not a WebDAV route"})
        try:
            body = dav_multistatus(path, self.headers.get("Depth", "1"))
            self.send_response(207)
            self.send_header("Content-Type", "application/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("DAV", "1")
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            json_response(self, 404, {"error": "WebDAV resource not found"})
        except Exception as exc:
            json_response(self, 400, {"error": str(exc)})

    def do_HEAD(self):
        parsed, path = self._parsed_route()
        if path == "/api/taste/bundle":
            query = parse_qs(parsed.query)
            date = (query.get("date") or [""])[0]
            fmt = (query.get("format") or ["txt"])[0]
            data, filename, mime = taste_bundle(date, fmt)
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Disposition", _content_disposition(filename))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path.startswith("/dav"):
            resource = dav_resource(path)
            if not resource:
                self.send_response(404); self.end_headers(); return
            data = resource.get("data") or b""
            self.send_response(200)
            self.send_header("Content-Type", "httpd/unix-directory" if resource.get("collection") else resource.get("mime", "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("DAV", "1")
            self.end_headers()
            return
        safe_path = safe_static_request_path(path)
        if not safe_path:
            self.send_response(404); self.end_headers(); return
        self.path = safe_path
        return super().do_HEAD()

    def do_POST(self):
        parsed, path = self._parsed_route()
        try:
            body = self._body()
            if path == "/api/profiles":
                data = save_profiles(body)
                log_event(task="private_console", action="save_profiles", status="done", message=f"Saved {len(data.get('profiles', []))} profiles", public_details={"profiles": len(data.get("profiles", []))})
                return json_response(self, 200, data)
            if path == "/api/selection":
                selection = update_selection(body)
                log_event(task="private_console", action="save_selection", status="done", message="Search profile selection updated", public_details={"selected": len(selection["selected_profile_ids"]), "fallback": selection.get("when_none")})
                return json_response(self, 200, selection)
            if path == "/api/taste/respond":
                return json_response(self, 200, save_taste_response(body))
            if path == "/api/feedback":
                key = str(body.get("canonical_key") or "").strip()
                verdict = str(body.get("verdict") or "").strip()
                reasons = [str(x).strip() for x in (body.get("reasons") or []) if str(x).strip()]
                tags = [str(x).strip() for x in (body.get("tags") or []) if str(x).strip()] if "tags" in body else None
                profile_id = str(body.get("profile_id") or "").strip() or None
                note = str(body.get("note") or "")
                context_id = str(body.get("entry_id") or "").strip()
                recommended_rank = str(body.get("recommended_rank") or "").strip()
                external_id = f"private_console:{profile_id or '__global__'}:{key}"
                cmd = [
                    sys.executable,
                    str(ROOT / "scripts" / "preference_feedback.py"),
                    "record",
                    "--key", key,
                    "--verdict", verdict,
                    "--reasons", ",".join(reasons),
                    "--note", note,
                    "--source", "private_console",
                    "--external-id", external_id,
                    "--context", context_id,
                    "--recommended-rank", recommended_rank,
                ]
                if tags is not None:
                    cmd += ["--tags", ",".join(tags)]
                if profile_id:
                    cmd += ["--profile", profile_id]
                proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
                if proc.returncode != 0:
                    raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
                log_event(task="private_console", action="preference_feedback", status="done", message=f"Preference feedback: {verdict}", public_details={"verdict": verdict})
                return json_response(self, 200, json.loads(proc.stdout))
            if path == "/api/feedback/apply":
                profile_id = str(body.get("profile_id") or "").strip()
                signal = str(body.get("signal") or "").strip()
                direction = str(body.get("direction") or "").strip()
                proc = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "preference_feedback.py"), "apply", "--profile", profile_id, "--reason", signal, "--direction", direction],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                )
                if proc.returncode != 0:
                    raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
                log_event(task="private_console", action="apply_preference", status="done", message=f"Applied learned preference: {signal}", public_details={"profile": profile_id, "direction": direction})
                return json_response(self, 200, json.loads(proc.stdout))
            if path == "/api/full-translation/request":
                key = str(body.get("canonical_key") or "")
                proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "full_translation.py"), "request", "--key", key], cwd=ROOT, text=True, capture_output=True)
                if proc.returncode != 0:
                    raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
                refresh_index()
                return json_response(self, 200, json.loads(proc.stdout))
            if path == "/api/full-translation/run-next":
                log_dir = ROOT / "workspace" / "automation-logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                out = (log_dir / "full-translation-runner.out.log").open("ab")
                err = (log_dir / "full-translation-runner.err.log").open("ab")
                proc = subprocess.Popen(
                    [sys.executable, str(ROOT / "scripts" / "full_translation.py"), "run-next"],
                    cwd=ROOT,
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                )
                return json_response(self, 202, {"status": "started", "pid": proc.pid})
            return json_response(self, 404, {"error": "unknown endpoint"})
        except Exception as exc:
            log_event(task="private_console", action="api", status="error", message=str(exc), public_details={})
            return json_response(self, 400, {"error": str(exc)})


def main() -> int:
    p = argparse.ArgumentParser(description="Private fieldnotes control console")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=18765)
    args = p.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Fieldnotes private console: http://{args.host}:{args.port}/console.html")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
