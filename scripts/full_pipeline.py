#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "data" / "work-registry.json"
STATUS = ROOT / "data" / "automation-status.json"
AUTOMATION = ROOT / "config" / "automation.json"
WORKER_DEFAULT = Path("/Volumes/DevDrive/Projects/novel-daily-pipeline")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def worker_python(worker_root: Path) -> Path:
    candidates = [worker_root / ".venv" / "bin" / "python", Path(sys.executable)]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No Python runtime found for worker: {worker_root}")


def ensure_target_registered(entry_id: str, top_n: int) -> None:
    run(
        [sys.executable, str(ROOT / "scripts" / "register_targets.py"), "--entry", entry_id, "--top-n", str(top_n)],
        cwd=ROOT,
    )


def target_rows(entry_id: str) -> list[dict]:
    registry = load_json(REGISTRY)
    rows = [row for row in registry.get("works", []) if row.get("latest_entry_id") == entry_id]
    by_url = {str(row.get("url") or ""): row for row in rows}
    entry = load_json(ROOT / "data" / "entries" / f"{entry_id}.json")
    results = entry.get("results") or {}
    candidates = list(results.get("shortlist") or []) + list(results.get("length_exceptions") or [])
    ordered = []
    seen = set()
    for candidate in candidates:
        row = by_url.get(str(candidate.get("url") or ""))
        if row and row.get("work_id") not in seen:
            ordered.append(row)
            seen.add(row.get("work_id"))
    ordered.extend(row for row in rows if row.get("work_id") not in seen)
    return ordered


def update_registry(row: dict, **changes) -> None:
    registry = load_json(REGISTRY)
    for item in registry.get("works", []):
        if item.get("work_id") == row.get("work_id") and item.get("workspace") == row.get("workspace"):
            item.update(changes)
            break
    registry["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(REGISTRY, registry)


def acquire(row: dict, worker_root: Path, episodes: int, force: bool) -> dict:
    workspace = ROOT / row["workspace"]
    inbox = workspace / "source_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(worker_python(worker_root)),
        "-m",
        "novelpipeline",
        "fetch-work",
        "--url",
        row["url"],
        "--output-dir",
        str(inbox),
        "--episodes",
        str(episodes),
    ]
    if force:
        cmd.append("--force")
    proc = run(cmd, cwd=worker_root)
    manifest = json.loads(proc.stdout)
    update_registry(
        row,
        status="source_acquired",
        source_policy="public_reader_first_n_private_local",
        acquired_episodes=manifest.get("acquired_episodes", 0),
        acquisition_manifest=str(Path(row["workspace"]) / "source_inbox" / "acquisition_manifest.json"),
        acquisition_updated_at=manifest.get("acquired_at"),
    )
    return manifest


def prepare(row: dict, automation: dict) -> dict:
    translation = automation.get("translation", {})
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "source_pipeline.py"),
        "prepare",
        "--entry",
        row["latest_entry_id"],
        "--work",
        row["work_id"],
        "--title",
        row.get("title") or row["work_id"],
        "--platform",
        row.get("platform") or "",
        "--target",
        str(int(translation.get("target_chunk_chars", 9000))),
        "--hard-max",
        str(int(translation.get("hard_max_chunk_chars", 12000))),
    ]
    proc = run(cmd, cwd=ROOT)
    payload = json.loads(proc.stdout)
    update_registry(row, status="translation_pending", prepared_at=datetime.now(timezone.utc).isoformat())
    return payload


def build_parallel_if_ready(row: dict) -> None:
    wdir = ROOT / row["workspace"]
    if not (wdir / "translation" / "manifest.json").exists():
        return
    run(
        [
            sys.executable,
            str(ROOT / "scripts" / "source_pipeline.py"),
            "build-parallel",
            "--entry",
            row["latest_entry_id"],
            "--work",
            row["work_id"],
        ],
        cwd=ROOT,
    )


def refresh_status(last_run: dict, worker_root: Path) -> None:
    run([sys.executable, str(ROOT / "scripts" / "refresh_automation_status.py")], cwd=ROOT)
    status = load_json(STATUS)
    status["last_run"] = last_run
    status.setdefault("source_acquisition", {}).update(
        {
            "status": "automatic_first_n_private_local",
            "worker": str(worker_root),
            "public_fulltext": False,
        }
    )
    write_json(STATUS, status)


def pipeline(entry_id: str, top_n: int, episodes: int, worker_root: Path, force: bool) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    ensure_target_registered(entry_id, top_n)
    automation = load_json(AUTOMATION)
    rows = target_rows(entry_id)[:top_n]
    results = []
    errors = []
    for row in rows:
        item = {"work_id": row.get("work_id"), "title": row.get("title"), "url": row.get("url")}
        try:
            item["acquisition"] = acquire(row, worker_root, episodes, force)
            refreshed = next(x for x in target_rows(entry_id) if x.get("work_id") == row.get("work_id"))
            item["prepare"] = prepare(refreshed, automation)
            refreshed = next(x for x in target_rows(entry_id) if x.get("work_id") == row.get("work_id"))
            build_parallel_if_ready(refreshed)
            item["status"] = "translation_pending"
        except Exception as exc:
            item["status"] = "error"
            item["error"] = str(exc)
            errors.append({"work_id": row.get("work_id"), "error": str(exc)})
            update_registry(row, status="error", last_error=str(exc), error_at=datetime.now(timezone.utc).isoformat())
        results.append(item)

    last_run = {
        "entry_id": entry_id,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "top_n": top_n,
        "episodes_per_work": episodes,
        "processed": len(results),
        "errors": errors,
    }
    refresh_status(last_run, worker_root)
    run([sys.executable, str(ROOT / "scripts" / "validate_repo.py")], cwd=ROOT)
    return {"last_run": last_run, "works": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge fieldnotes discovery targets into acquisition/chunk pipeline")
    parser.add_argument("--entry", required=True)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--worker-root", default=os.environ.get("NOVEL_PIPELINE_ROOT", str(WORKER_DEFAULT)))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = pipeline(
        args.entry,
        max(1, args.top_n),
        max(1, args.episodes),
        Path(args.worker_root).expanduser().resolve(),
        args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["last_run"]["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
