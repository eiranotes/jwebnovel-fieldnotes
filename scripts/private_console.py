#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from automation_log import log_event


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
SAFE_STATIC_FILES = {"/", "/index.html", "/console.html", "/styles.css", "/archive.js", "/console.js", "/.nojekyll"}
SAFE_STATIC_ROOTS = ("entries", "docs", "data")


def load(path: Path, fallback):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def atomic_write(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


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
        for kind, rel in (
            ("merged_original", work.get("paths", {}).get("merged")),
            ("parallel_view", work.get("paths", {}).get("parallel_view")),
        ):
            if not rel:
                continue
            target = (ROOT / rel).resolve()
            if target.is_file():
                rows.append({
                    "kind": kind,
                    "title": work.get("title"),
                    "work_id": work.get("work_id"),
                    "path": str(target.relative_to(ROOT)),
                    "filename": target.name,
                    "size": target.stat().st_size,
                })
        workspace = work.get("workspace")
        if workspace:
            output_dir = (ROOT / workspace / "translation" / "output").resolve()
            if output_dir.is_dir():
                for target in sorted(output_dir.iterdir()):
                    if not target.is_file() or target.suffix.lower() not in {".txt", ".md", ".zip"}:
                        continue
                    rows.append({
                        "kind": "standard_translation",
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
            if target.is_file():
                rows.append({
                    "kind": "full_translation",
                    "title": request.get("title"),
                    "work_id": request.get("work_id"),
                    "path": str(target.relative_to(ROOT)),
                    "filename": target.name,
                    "size": target.stat().st_size,
                })
    unique = {row["path"]: row for row in rows}
    return sorted(unique.values(), key=lambda x: (str(x.get("title") or ""), x["kind"], x["filename"]))


def state_payload() -> dict:
    return {
        "profiles": load(PROFILES, {}),
        "automation": load(AUTOMATION, {}),
        "work_index": load(WORK_INDEX, {"works": []}),
        "full_translation": load(FULL_QUEUE, {"requests": []}),
        "logs": load(LOGS, {"entries": []}),
        "rotation": load(ROTATION, {}),
        "artifacts": artifact_inventory(),
        "preference_feedback": load(PREFERENCE_FEEDBACK, {"events": []}),
        "preference_model": load(PREFERENCE_MODEL, {"profiles": {}}),
        "console": {"writable": True, "root": str(ROOT)},
    }


def refresh_index() -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "rebuild_work_index.py")], cwd=ROOT, check=True, text=True, capture_output=True)


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
            self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        safe_path = safe_static_request_path(path)
        if not safe_path:
            return json_response(self, 404, {"error": "not available from private console"})
        self.path = safe_path
        return super().do_GET()

    def do_POST(self):
        parsed, path = self._parsed_route()
        try:
            body = self._body()
            if path == "/api/profiles":
                data = validate_profiles(body)
                atomic_write(PROFILES, data)
                log_event(task="private_console", action="save_profiles", status="done", message=f"Saved {len(data.get('profiles', []))} profiles", public_details={"profiles": len(data.get("profiles", []))})
                return json_response(self, 200, data)
            if path == "/api/selection":
                data = load(PROFILES, {})
                selection = data.setdefault("selection", {})
                selected = body.get("selected_profile_ids") or []
                valid = {p.get("profile_id") for p in data.get("profiles", []) if p.get("enabled")}
                selection["selected_profile_ids"] = [x for x in selected if x in valid]
                if body.get("explicit_selection_mode") in {"once", "sticky"}:
                    selection["explicit_selection_mode"] = body["explicit_selection_mode"]
                if body.get("when_none") in {"round_robin", "least_recently_run", "random_daily", "all_enabled"}:
                    selection["when_none"] = body["when_none"]
                if body.get("rotation_batch_size") is not None:
                    selection["rotation_batch_size"] = max(1, int(body["rotation_batch_size"]))
                atomic_write(PROFILES, data)
                log_event(task="private_console", action="save_selection", status="done", message="Search profile selection updated", public_details={"selected": len(selection["selected_profile_ids"]), "fallback": selection.get("when_none")})
                return json_response(self, 200, selection)
            if path == "/api/feedback":
                key = str(body.get("canonical_key") or "").strip()
                verdict = str(body.get("verdict") or "").strip()
                reasons = [str(x).strip() for x in (body.get("reasons") or []) if str(x).strip()]
                tags = [str(x).strip() for x in (body.get("tags") or []) if str(x).strip()]
                profile_id = str(body.get("profile_id") or "").strip() or None
                note = str(body.get("note") or "")
                cmd = [
                    sys.executable,
                    str(ROOT / "scripts" / "preference_feedback.py"),
                    "record",
                    "--key", key,
                    "--verdict", verdict,
                    "--reasons", ",".join(reasons),
                    "--tags", ",".join(tags),
                    "--note", note,
                    "--source", "private_console",
                ]
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
