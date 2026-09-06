#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from automation_log import log_event, new_run_id


ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "work-registry.json"
AUTOMATION = ROOT / "config" / "automation.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pending_works() -> list[dict]:
    registry = load_json(REGISTRY)
    rows = []
    for row in registry.get("works", []):
        wdir = ROOT / row.get("workspace", "")
        manifest_path = wdir / "translation" / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = load_json(manifest_path)
        except Exception:
            continue
        pending = [c for c in manifest.get("chunks", []) if c.get("status") != "done"]
        if not pending:
            continue
        state_path = wdir / "state.json"
        state = load_json(state_path) if state_path.exists() else {}
        rows.append(
            {
                "row": row,
                "pending": pending,
                "manifest": manifest,
                "updated_at": state.get("updated_at") or row.get("prepared_at") or row.get("entry_id") or "",
            }
        )
    rows.sort(key=lambda x: (x["updated_at"], x["row"].get("entry_id", ""), x["row"].get("work_id", "")))
    return rows


def command_next(args) -> int:
    run_id = new_run_id("translate-next")
    queue = pending_works()
    if not queue:
        log_event(task="translation_queue", action="next", status="complete", run_id=run_id, message="No pending standard translation chunks")
        print(json.dumps({"status": "complete"}, ensure_ascii=False))
        return 0
    selected = queue[0]["row"]
    cfg = load_json(AUTOMATION).get("translation", {})
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "source_pipeline.py"),
        "next-task",
        "--entry",
        selected["latest_entry_id"],
        "--work",
        selected["work_id"],
        "--context-tail",
        str(int(cfg.get("context_tail_chars", 700))),
        "--context-head",
        str(int(cfg.get("context_head_chars", 500))),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    task_path = Path(proc.stdout.strip())
    task = load_json(task_path)
    task["queue"] = {
        "selected_by": "oldest_pending_first",
        "pending_works": len(queue),
        "pending_chunks_total": sum(len(x["pending"]) for x in queue),
        "task_path": str(task_path),
    }
    log_event(task="translation_queue", action="next", status="pending", run_id=run_id, message=f"Selected {selected.get('title')} / {task.get('chunk_id')}", details={"work_id": selected.get("work_id"), "chunk": task.get("chunk_id"), "pending_works": len(queue)}, public_details={"title": selected.get("title"), "chunk": task.get("chunk_id")})
    print(json.dumps(task, ensure_ascii=False, indent=2))
    return 0


def command_complete(args) -> int:
    run_id = new_run_id("translate-complete")
    result_path = Path(args.result).expanduser().resolve()
    if not result_path.exists():
        raise SystemExit(f"result not found: {result_path}")
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "source_pipeline.py"),
        "complete",
        "--entry",
        args.entry,
        "--work",
        args.work,
        "--chunk",
        args.chunk,
        "--result",
        str(result_path),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "source_pipeline.py"),
            "build-parallel",
            "--entry",
            args.entry,
            "--work",
            args.work,
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    subprocess.run([sys.executable, str(ROOT / "scripts" / "refresh_automation_status.py")], cwd=ROOT, check=True)
    payload = json.loads(proc.stdout)
    payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    log_event(task="translation_queue", action="complete", status="done", run_id=run_id, message=f"Completed {args.work} / {args.chunk}", details=payload, public_details={"work_id": args.work, "chunk": args.chunk, "done": payload.get("done"), "total": payload.get("total")})
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_status(args) -> int:
    queue = pending_works()
    print(
        json.dumps(
            {
                "pending_works": len(queue),
                "pending_chunks_total": sum(len(x["pending"]) for x in queue),
                "works": [
                    {
                        "work_id": x["row"].get("work_id"),
                        "title": x["row"].get("title"),
                        "entry_id": x["row"].get("latest_entry_id"),
                        "pending_chunks": len(x["pending"]),
                        "next_chunk": x["pending"][0].get("chunk_id"),
                    }
                    for x in queue
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Global resumable translation queue")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("next")
    p.set_defaults(func=command_next)
    p = sub.add_parser("complete")
    p.add_argument("--entry", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--chunk", required=True)
    p.add_argument("--result", required=True)
    p.set_defaults(func=command_complete)
    p = sub.add_parser("status")
    p.set_defaults(func=command_status)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
