#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PRIVATE_ROOT = ROOT / "workspace" / "automation-logs"
PUBLIC_PATH = ROOT / "data" / "automation-logs.json"
PUBLIC_LIMIT = 500


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id(prefix: str = "run") -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _json_safe(value):
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return str(value)


def log_event(
    *,
    task: str,
    action: str,
    status: str,
    message: str = "",
    run_id: str | None = None,
    details: dict | None = None,
    public_details: dict | None = None,
) -> dict:
    run_id = run_id or new_run_id(task.replace("_", "-"))
    timestamp = now()
    event = {
        "timestamp": timestamp,
        "run_id": run_id,
        "task": task,
        "action": action,
        "status": status,
        "message": message,
        "details": {k: _json_safe(v) for k, v in (details or {}).items()},
    }
    day = timestamp[:10]
    PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
    with (PRIVATE_ROOT / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    if PUBLIC_PATH.exists():
        public = json.loads(PUBLIC_PATH.read_text(encoding="utf-8"))
    else:
        public = {"schema_version": "1.0", "updated_at": None, "entries": []}
    summary = {
        "timestamp": timestamp,
        "run_id": run_id,
        "task": task,
        "action": action,
        "status": status,
        "message": message,
        "details": {k: _json_safe(v) for k, v in (public_details or {}).items()},
    }
    entries = public.setdefault("entries", [])
    entries.append(summary)
    public["entries"] = entries[-PUBLIC_LIMIT:]
    public["updated_at"] = timestamp
    tmp = PUBLIC_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(PUBLIC_PATH)
    return event


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a fieldnotes automation event")
    parser.add_argument("--task", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--message", default="")
    parser.add_argument("--run-id")
    parser.add_argument("--details-json", default="{}")
    args = parser.parse_args()
    details = json.loads(args.details_json)
    event = log_event(
        task=args.task,
        action=args.action,
        status=args.status,
        message=args.message,
        run_id=args.run_id,
        details=details,
        public_details=details,
    )
    print(json.dumps(event, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
