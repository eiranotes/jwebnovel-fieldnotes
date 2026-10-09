#!/usr/bin/env python3
"""Read-only Fieldnotes pipeline health and Eira translation-worker diagnostics.

Never calls translation_queue next/complete, submits a model operation, changes
the canonical repository, or assumes that a queue-inspection worker can translate.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


TRANSLATOR_CAPABILITY = "fieldnotes.karu.project.translate"
EXPECTED_WORKSPACE = "shared-automation"
MAX_INPUT_BYTES = 16 * 1024 * 1024


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def age_hours(value, now):
    date = parse_time(value)
    if date is None:
        return None
    return max(0.0, (now - date).total_seconds() / 3600)


def read_json(path: Path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("UNSAFE_OR_MISSING_JSON")
    return json.loads(path.read_text(encoding="utf-8"))


def safe_work_dir(root: Path, relative) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts or rel.parts[0] != "workspace" or ".." in rel.parts:
        return None
    full = root / rel
    try:
        if not full.resolve().is_relative_to((root / "workspace").resolve()):
            return None
    except (ValueError, OSError):
        return None
    return full


def model_worker_status(worker_snapshot, now, max_age_minutes=5):
    """Status is evidence-based. A routing/inspection worker is NOT a translator."""
    if worker_snapshot is None:
        return {"status": "unknown", "reason": "MODEL_WORKER_OBSERVER_MISSING"}
    age = age_hours(worker_snapshot.get("observed_at"), now)
    if age is None or age * 60 > max_age_minutes:
        return {"status": "unavailable", "reason": "MODEL_WORKER_HEARTBEAT_STALE"}
    if (worker_snapshot.get("workspace") != EXPECTED_WORKSPACE or
            TRANSLATOR_CAPABILITY not in (worker_snapshot.get("capabilities") or []) or
            worker_snapshot.get("status") != "ready"):
        return {"status": "unavailable", "reason": "MODEL_WORKER_CAPABILITY_OR_STATE_MISMATCH"}
    return {"status": "ready", "reason": None, "heartbeat_age_minutes": round(age * 60, 1)}


def examine_work(root: Path, work: dict, now, stall_hours: float, worker: dict):
    work_id = str(work.get("work_id") or "")
    if not work_id or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,150}", work_id):
        return {"work_id": "invalid", "state": "invalid_work_id"}
    where = safe_work_dir(root, work.get("workspace"))
    if where is None:
        return {"work_id": work_id, "state": "invalid_workspace_path"}
    manifest_file = where / "translation" / "manifest.json"
    if not manifest_file.exists():
        return {"work_id": work_id,
                "state": "source_or_manifest_missing" if work.get("status") == "translation_pending" else "not_prepared",
                "pending_chunks": 0}
    try:
        manifest = read_json(manifest_file)
    except (OSError, ValueError, json.JSONDecodeError):
        return {"work_id": work_id, "state": "invalid_manifest"}
    chunks = manifest.get("chunks")
    if not isinstance(chunks, list):
        return {"work_id": work_id, "state": "invalid_manifest"}
    pending = sum(1 for c in chunks if isinstance(c, dict) and c.get("status") != "done")
    if not pending:
        return {"work_id": work_id, "state": "completed", "pending_chunks": 0}
    state_file = where / "state.json"
    try:
        state = read_json(state_file) if state_file.is_file() else {}
    except (OSError, ValueError, json.JSONDecodeError):
        state = {}
    if state.get("status") == "translation_skipped":
        return {"work_id": work_id, "state": "skipped", "pending_chunks": pending}
    candidates = [age_hours(value, now) for value in (
        state.get("updated_at"), work.get("translation_updated_at"),
        manifest.get("updated_at"), work.get("prepared_at"),
    )]
    ages = [v for v in candidates if v is not None]
    # Most recent trustworthy timestamp rather than an old registry entry.
    idle = min(ages) if ages else None
    if worker["status"] == "unknown":
        classification = "awaiting_worker_observation"
    elif worker["status"] != "ready":
        classification = "worker_unavailable"
    elif idle is not None and idle > stall_hours:
        classification = "stalled"
    else:
        classification = "queued"
    return {"work_id": work_id, "state": classification,
            "pending_chunks": pending,
            "idle_hours": round(idle, 1) if idle is not None else None}


def audit(root: Path, now=None, worker_snapshot_path=None, stall_hours=3.0,
          heartbeat_minutes=5.0):
    root = root.resolve()
    now = now or now_utc()
    if stall_hours <= 0 or heartbeat_minutes <= 0:
        raise ValueError("HEALTH_THRESHOLDS_MUST_BE_POSITIVE")
    registry = read_json(root / "data/work-registry.json")
    if not isinstance(registry.get("works"), list):
        raise ValueError("WORK_REGISTRY_SCHEMA_INVALID")
    config = read_json(root / "config/automation.json")
    snapshot = None
    if worker_snapshot_path is not None:
        try:
            snapshot = read_json(worker_snapshot_path)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    worker = model_worker_status(snapshot, now, heartbeat_minutes)
    works = [
        examine_work(root, item, now, stall_hours, worker)
        for item in registry["works"] if isinstance(item, dict)
    ]
    states = {}
    for item in works:
        states[item["state"]] = states.get(item["state"], 0) + 1
    pending = sum(item.get("pending_chunks", 0) for item in works
                  if item["state"] not in ("skipped", "completed"))
    try:
        public_status = read_json(root / "data/automation-status.json")
        projection_age = age_hours(public_status.get("updated_at"), now)
    except (OSError, ValueError, json.JSONDecodeError):
        projection_age = None
    return {
        "schema_version": 1,
        "observed_at": now.isoformat(),
        "read_only": True,
        "configured_enabled": config.get("enabled") is True,
        "model_worker": worker,
        "pending_chunks": pending,
        "work_state_counts": states,
        "status_projection_age_hours": round(projection_age, 1) if projection_age is not None else None,
        "works_needing_attention": [
            item for item in works if item["state"] in {
                "worker_unavailable", "stalled", "invalid_manifest",
                "invalid_workspace_path", "source_or_manifest_missing",
            }
        ],
        # Preserve a distinction between an unavailable model worker and a
        # stale public status projection; neither is a reason to resubmit work.
        "auto_translation_submitted": False,
        "safe_to_resubmit_uncertain_translation": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only Fieldnotes queue/worker health")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--worker-status", type=Path, default=None,
                        help="Optional trusted Fabric translator heartbeat JSON, not the queue inspector")
    parser.add_argument("--stall-hours", type=float, default=3.0)
    parser.add_argument("--heartbeat-minutes", type=float, default=5.0)
    args = parser.parse_args()
    print(json.dumps(audit(args.root, worker_snapshot_path=args.worker_status,
                           stall_hours=args.stall_hours,
                           heartbeat_minutes=args.heartbeat_minutes),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
