"""A resumable Project-only client of the local Steroids bridge, not an OpenAI API client."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from automation_store import AutomationError, atomic_json, digest, locked, now, read_json


class BridgeClient:
    def __init__(self, timeout: float = 20) -> None:
        self.timeout = timeout
        self.base = ""
        self._token = ""
        self.headers = {"x-extension-protocol": "8", "x-extension-version": "2.0.2"}
        for port in range(8765, 8770):
            base = f"http://127.0.0.1:{port}"
            try:
                request = urllib.request.Request(base + "/hello", headers=self.headers)
                with urllib.request.urlopen(request, timeout=2) as response:
                    hello = json.load(response)
                if hello.get("app") == "chat-on-steroids" and hello.get("bridge") == 8 and hello.get("compatible") is not False and "project-target-v1" in hello.get("features", []):
                    self.base = base
                    break
            except (OSError, ValueError):
                continue
        if not self.base:
            raise AutomationError("PROJECT_BRIDGE_UNAVAILABLE")
        credentials = self.request("/automation-agents/recovery-pair", method="POST", authenticated=False)
        self._token = credentials.get("token", "")
        if not isinstance(self._token, str) or not self._token:
            raise AutomationError("AUTOMATION_CAPABILITY_UNAVAILABLE")

    def request(self, route: str, body=None, *, method="GET", authenticated=True):
        if not route.startswith(("/automation-agents/", "/automation-projects/")):
            raise AutomationError("UNSUPPORTED_BRIDGE_ROUTE")
        headers = dict(self.headers)
        if authenticated:
            headers["authorization"] = "Bearer " + self._token
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        if data is not None:
            headers["content-type"] = "application/json"
        request = urllib.request.Request(self.base + route, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                detail = json.load(error)
            except (ValueError, OSError):
                detail = {}
            # Do not echo server prose into public status; it can contain worker source text.
            raise AutomationError(str(detail.get("error", f"BRIDGE_HTTP_{error.code}"))) from error
        except (OSError, ValueError) as error:
            raise AutomationError("BRIDGE_TRANSPORT_UNCERTAIN") from error


def parse_envelope(answer: str, operation_id: str, work_id: str):
    raw = answer.strip()
    if raw.startswith("```json\n") and raw.endswith("\n```"):
        raw = raw[8:-4]
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise AutomationError("INVALID_MODEL_JSON") from error
    if not isinstance(value, dict) or value.get("operation_id") != operation_id or value.get("work_id") != work_id or "payload" not in value:
        raise AutomationError("RESULT_OPERATION_MISMATCH")
    return value["payload"]


class ProjectBackend:
    def __init__(self, root: Path, bridge=None, *, timeout=600, poll_interval=1.0) -> None:
        self.root = root
        self.bridge = bridge or BridgeClient()
        self.timeout = timeout
        self.poll_interval = poll_interval

    def _project(self, alias: str) -> dict:
        registry = self.bridge.request("/automation-projects/registry")
        project = registry.get("entries", {}).get(alias)
        if not isinstance(project, dict) or not project.get("url"):
            raise AutomationError("PROJECT_TARGET_NOT_VERIFIED")
        return {key: project[key] for key in ("alias", "name", "url")}

    def execute(self, work_id: str, role: str, payload: dict, *, alias="fieldnotes", operation_id: str | None = None):
        if role not in ("translator", "reviewer", "discovery"):
            raise AutomationError("INVALID_WORKER_ROLE")
        if not isinstance(work_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", work_id):
            raise AutomationError("INVALID_WORK_ID")
        operation_id = operation_id or digest({"work":work_id,"role":role,"alias":alias,"payload":payload})
        if not re.fullmatch(r"[a-zA-Z0-9_-]{12,128}", operation_id):
            raise AutomationError("INVALID_OPERATION_ID")
        directory = self.root / "workspace" / "automation-runs" / "backend" / work_id / role
        state_path = directory / f"{operation_id}.json"
        mapping_path = directory / "worker.json"
        with locked(directory / ".lock"):
            previous = read_json(state_path, {})
            fingerprint = digest({"work":work_id,"role":role,"alias":alias,"payload":payload})
            if previous and previous.get("fingerprint") != fingerprint:
                raise AutomationError("OPERATION_REQUEST_CONFLICT")
            if previous.get("state") == "complete":
                result_path = directory / previous["result_file"]
                result = read_json(result_path)
                if digest(result) != previous.get("result_sha256"):
                    raise AutomationError("RESULT_CACHE_TAMPERED")
                return result
            if previous.get("state") in ("submitting", "uncertain"):
                raise AutomationError("OPERATION_SUBMISSION_UNCERTAIN", "inspect the accepted worker before retrying")
            if previous.get("state") == "failed":
                raise AutomationError(previous.get("error", "WORKER_FAILED"))
            project = self._project(alias)
            target = {**project, "workId":work_id,"role":role}
            if previous.get("state") == "accepted":
                if previous.get("target") != target:
                    raise AutomationError("PROJECT_TARGET_CHANGED")
                state = previous
            else:
                try:
                    status = self.bridge.request("/automation-agents/status")
                except AutomationError as error:
                    if error.code != "no_automation_run":
                        raise
                    status = {"workers":[]}
                mapping = read_json(mapping_path, {})
                worker = next((w for w in status.get("workers", []) if w.get("id") == mapping.get("worker_id") and w.get("createdAt") == mapping.get("created_at")), None)
                reusable = worker and worker.get("projectTarget") == target and worker.get("state") == "sleeping" and worker.get("revivable") is True
                if worker and worker.get("state") in ("active","invited","waking","detached"):
                    raise AutomationError("WORKER_BUSY")
                prompt = json.dumps({"operation_id":operation_id,"work_id":work_id,"task":payload,
                    "response_contract":{"operation_id":operation_id,"work_id":work_id,"payload":"the task's requested JSON result"},
                    "instructions":"Return only a JSON object matching response_contract, not a stringified object. Use the exact named Project Sources. Do not use local tools or agents."}, ensure_ascii=False)
                if len(prompt) > 250_000:
                    raise AutomationError("TASK_TOO_LARGE")
                state = {"version":1,"operation_id":operation_id,"fingerprint":fingerprint,"target":target,
                         "state":"submitting","submitted_at":now(),"reused":bool(reusable)}
                atomic_json(state_path,state)
                try:
                    if reusable:
                        self.bridge.request("/automation-agents/message", {
                            "to":worker["id"],"expectedCreatedAt":worker["createdAt"],"text":prompt},method="POST")
                        selected = worker
                    else:
                        response = self.bridge.request("/automation-agents/spawn", {"workers":[{
                            "label":f"{work_id[:40]}-{role}","task":prompt,
                            "target":{"type":"chatgpt_project","project":alias,"workId":work_id,"role":role}}]}, method="POST")
                        selected = response["workers"][0]
                    if not selected.get("createdAt") or selected.get("projectTarget") != target:
                        raise AutomationError("WORKER_TARGET_NOT_VERIFIED")
                    state.update(state="accepted",worker_id=selected["id"],created_at=selected["createdAt"])
                    atomic_json(state_path,state)
                    atomic_json(mapping_path,{"worker_id":selected["id"],"created_at":selected["createdAt"],"target":target})
                except Exception:
                    # Even a lost successful HTTP response can leave an actual chat. Do not
                    # send twice, create another chat, or call a non-Project backend silently.
                    state["state"] = "uncertain"
                    atomic_json(state_path,state)
                    raise
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                status = self.bridge.request("/automation-agents/status")
                worker = next((w for w in status.get("workers",[]) if w.get("id") == state["worker_id"] and w.get("createdAt") == state["created_at"]), None)
                if not worker or worker.get("projectTarget") != target:
                    raise AutomationError("WORKER_TARGET_NOT_VERIFIED")
                if worker.get("state") == "failed":
                    state.update(state="failed",error="PROJECT_WORKER_FAILED",ended_at=now())
                    atomic_json(state_path,state)
                    raise AutomationError("PROJECT_WORKER_FAILED")
                if worker.get("state") in ("sleeping","finished") and worker.get("complete") is True and isinstance(worker.get("answer"),str):
                    result = parse_envelope(worker["answer"],operation_id,work_id)
                    result_file = f"{operation_id}.result.json"
                    atomic_json(directory / result_file,result)
                    state.update(state="complete",result_file=result_file,result_sha256=digest(result),
                                 conversation_id=worker.get("conversationId"),ended_at=now())
                    atomic_json(state_path,state)
                    return result
                time.sleep(self.poll_interval)
            # Accepted work is retained for result polling on resume; never auto-resubmitted.
            state.update(last_error="WORKER_RESULT_TIMEOUT",last_wait_at=now())
            atomic_json(state_path,state)
            raise AutomationError("WORKER_RESULT_TIMEOUT")
