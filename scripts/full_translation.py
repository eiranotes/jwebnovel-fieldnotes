#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from automation_log import log_event, new_run_id
from preference_feedback import record as record_preference


ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "data" / "work-index.json"
QUEUE = ROOT / "data" / "full-translation-queue.json"
WORKER = ROOT / "workers" / "novel-download"
AUTOMATION = ROOT / "config" / "automation.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_queue(data: dict) -> None:
    data["updated_at"] = now()
    QUEUE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def worker_python() -> str:
    path = WORKER / ".venv" / "bin" / "python"
    return str(path if path.exists() else Path(sys.executable))


def safe_id(row: dict) -> str:
    parsed = urlparse(str(row.get("url") or ""))
    if "syosetu.com" in parsed.netloc:
        m = re.search(r"/([a-z]\d{4}[a-z]{2})/?", parsed.path, re.I)
        if m:
            return f"narou-{m.group(1).lower()}"
    if parsed.netloc == "kakuyomu.jp":
        m = re.search(r"/works/(\d+)", parsed.path)
        if m:
            return f"kakuyomu-{m.group(1)}"
    cleaned = re.sub(r"[^0-9A-Za-z_-]+", "-", str(row.get("title") or "work").lower()).strip("-")
    return cleaned[:80] or "work"


def request(canonical_key: str) -> dict:
    index = load(INDEX)
    work = next((w for w in index.get("works", []) if w.get("canonical_key") == canonical_key), None)
    if not work:
        raise SystemExit(f"work not found in index: {canonical_key}")
    queue = load(QUEUE)
    existing = next((x for x in queue.get("requests", []) if x.get("canonical_key") == canonical_key and x.get("status") not in {"cancelled"}), None)
    if existing:
        return existing
    work_id = safe_id(work)
    rel = Path("workspace") / "full-translations" / work_id
    item = {
        "request_id": f"full-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{work_id}",
        "canonical_key": canonical_key,
        "work_id": work_id,
        "title": work.get("title"),
        "author": work.get("author"),
        "platform": work.get("platform"),
        "url": work.get("url"),
        "workspace": str(rel),
        "status": "queued",
        "requested_at": now(),
        "updated_at": now(),
        "chunks_total": 0,
        "chunks_done": 0,
        "artifacts": [],
    }
    queue.setdefault("requests", []).append(item)
    save_queue(queue)
    record_preference(canonical_key=canonical_key, verdict="love", reasons=[], tags=[], source="full_translation")
    log_event(task="full_translation", action="request", status="queued", message=f"Full translation requested: {item['title']}", details={"request_id": item["request_id"], "canonical_key": canonical_key}, public_details={"title": item["title"], "request_id": item["request_id"]})
    return item


def run_next() -> dict:
    queue = load(QUEUE)
    item = next((x for x in queue.get("requests", []) if x.get("status") in {"queued", "acquisition_error"}), None)
    if not item:
        return {"status": "nothing_queued"}
    run_id = new_run_id("full-acquire")
    wdir = ROOT / item["workspace"]
    inbox = wdir / "source_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    item.update({"status": "acquiring", "updated_at": now()})
    save_queue(queue)
    log_event(task="full_translation", action="acquire_all", status="started", run_id=run_id, message=f"Acquiring all episodes: {item['title']}", public_details={"title": item["title"]})
    try:
        cmd = [worker_python(), "-m", "novelpipeline", "fetch-work", "--url", item["url"], "--output-dir", str(inbox), "--all"]
        proc = subprocess.run(cmd, cwd=WORKER, text=True, capture_output=True, check=True)
        acquisition = json.loads(proc.stdout)
        metadata = {
            "entry_id": None,
            "work_id": item["work_id"],
            "title": item["title"],
            "author": item.get("author"),
            "platform": item.get("platform"),
            "url": item.get("url"),
            "source_policy": "public_reader_full_private_local",
            "workspace": item["workspace"],
        }
        (wdir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cfg = load(AUTOMATION).get("translation", {})
        prep = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "source_pipeline.py"), "prepare", "--work-dir", item["workspace"], "--work", item["work_id"], "--title", item["title"] or item["work_id"], "--platform", item.get("platform") or "", "--target", str(int(cfg.get("target_chunk_chars", 9000))), "--hard-max", str(int(cfg.get("hard_max_chunk_chars", 12000)))],
            cwd=ROOT, text=True, capture_output=True, check=True,
        )
        prepared = json.loads(prep.stdout)
        manifest = load(wdir / "translation" / "manifest.json")
        item.update({"status": "translation_pending", "updated_at": now(), "acquired_episodes": acquisition.get("acquired_episodes"), "available_episodes": acquisition.get("available_episodes"), "chunks_total": manifest.get("chunk_count", 0), "chunks_done": sum(1 for c in manifest.get("chunks", []) if c.get("status") == "done")})
        save_queue(queue)
        log_event(task="full_translation", action="acquire_all", status="done", run_id=run_id, message=f"Full source prepared: {item['title']}", details={"episodes": item.get("acquired_episodes"), "chunks": item.get("chunks_total")}, public_details={"title": item["title"], "episodes": item.get("acquired_episodes"), "chunks": item.get("chunks_total")})
        return {"request": item, "acquisition": acquisition, "prepare": prepared}
    except Exception as exc:
        item.update({"status": "acquisition_error", "updated_at": now(), "last_error": str(exc)})
        save_queue(queue)
        log_event(task="full_translation", action="acquire_all", status="error", run_id=run_id, message=str(exc), public_details={"title": item.get("title")})
        raise


def pending_request() -> dict | None:
    queue = load(QUEUE)
    return next((x for x in queue.get("requests", []) if x.get("status") == "translation_pending"), None)


def next_task() -> dict:
    item = pending_request()
    if not item:
        return {"status": "complete"}
    cfg = load(AUTOMATION).get("translation", {})
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "source_pipeline.py"), "next-task", "--work-dir", item["workspace"], "--work", item["work_id"], "--context-tail", str(int(cfg.get("context_tail_chars", 700))), "--context-head", str(int(cfg.get("context_head_chars", 500)))],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    text = proc.stdout.strip()
    try:
        terminal = json.loads(text)
        if terminal.get("status") == "complete":
            finalize(item["request_id"])
            return {"status": "complete", "request_id": item["request_id"]}
    except Exception:
        pass
    task_path = Path(text)
    task = load(task_path)
    task["full_translation_request_id"] = item["request_id"]
    task["queue_priority"] = "user_selected_full_translation"
    log_event(task="full_translation", action="next_chunk", status="pending", message=f"Chunk {task.get('chunk_id')} ready: {item['title']}", public_details={"title": item["title"], "chunk": task.get("chunk_id")})
    return task


def complete(request_id: str, chunk: str, result: str) -> dict:
    queue = load(QUEUE)
    item = next((x for x in queue.get("requests", []) if x.get("request_id") == request_id), None)
    if not item:
        raise SystemExit(f"request not found: {request_id}")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "source_pipeline.py"), "complete", "--work-dir", item["workspace"], "--work", item["work_id"], "--chunk", chunk, "--result", str(Path(result).expanduser().resolve())],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    payload = json.loads(proc.stdout)
    item["chunks_done"] = payload.get("done", item.get("chunks_done", 0))
    item["chunks_total"] = payload.get("total", item.get("chunks_total", 0))
    item["updated_at"] = now()
    save_queue(queue)
    log_event(task="full_translation", action="complete_chunk", status="done", message=f"Chunk {chunk} translated: {item['title']}", public_details={"title": item["title"], "chunk": chunk, "done": item["chunks_done"], "total": item["chunks_total"]})
    if item["chunks_done"] >= item["chunks_total"] > 0:
        finalize(request_id)
    return payload


def finalize(request_id: str) -> dict:
    queue = load(QUEUE)
    item = next((x for x in queue.get("requests", []) if x.get("request_id") == request_id), None)
    if not item:
        raise SystemExit(f"request not found: {request_id}")
    wdir = ROOT / item["workspace"]
    manifest = load(wdir / "translation" / "manifest.json")
    pending = [c for c in manifest.get("chunks", []) if c.get("status") != "done"]
    if pending:
        return {"status": "translation_pending", "missing_chunk": pending[0].get("chunk_id")}
    package = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "source_pipeline.py"), "build-output", "--work-dir", item["workspace"], "--work", item["work_id"]],
        cwd=ROOT, check=True, text=True, capture_output=True,
    )
    output = json.loads(package.stdout)
    if output.get("status") != "complete":
        return output
    subprocess.run([sys.executable, str(ROOT / "scripts" / "source_pipeline.py"), "build-parallel", "--work-dir", item["workspace"], "--work", item["work_id"]], cwd=ROOT, check=True, text=True, capture_output=True)
    item.update({
        "status": "complete", "updated_at": now(), "completed_at": now(),
        "chunks_done": len(manifest.get("chunks", [])), "chunks_total": len(manifest.get("chunks", [])),
        "artifacts": output.get("artifacts", []),
    })
    save_queue(queue)
    log_event(task="full_translation", action="finalize", status="done", message=f"Full translation complete: {item['title']}", public_details={"title": item["title"], "chunks": item["chunks_total"]})
    return item


def main() -> int:
    p = argparse.ArgumentParser(description="User-selected full-work translation queue")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("request"); q.add_argument("--key", required=True)
    sub.add_parser("run-next")
    sub.add_parser("next-task")
    q = sub.add_parser("complete"); q.add_argument("--request", required=True); q.add_argument("--chunk", required=True); q.add_argument("--result", required=True)
    q = sub.add_parser("finalize"); q.add_argument("--request", required=True)
    sub.add_parser("status")
    args = p.parse_args()
    if args.cmd == "request": result = request(args.key)
    elif args.cmd == "run-next": result = run_next()
    elif args.cmd == "next-task": result = next_task()
    elif args.cmd == "complete": result = complete(args.request, args.chunk, args.result)
    elif args.cmd == "finalize": result = finalize(args.request)
    else: result = load(QUEUE)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
