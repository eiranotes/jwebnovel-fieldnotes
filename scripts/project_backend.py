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
        # Models occasionally emit an otherwise complete JSON object followed by one or more
        # unmatched closing braces. Recover only that syntactically unambiguous tail: the first
        # raw-decoded value must consume the whole meaningful answer and the remainder may contain
        # only `}` plus whitespace. Prose, a second object, or an incomplete JSON value still fails.
        try:
            value, end = json.JSONDecoder().raw_decode(raw)
            remainder = raw[end:].strip()
            if not remainder or any(ch != '}' for ch in remainder) or len(remainder) > 3:
                raise ValueError('unsafe trailing data')
        except (TypeError, ValueError, json.JSONDecodeError) as repair_error:
            raise AutomationError("INVALID_MODEL_JSON") from repair_error
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

    def _worker_instructions(self, work_id: str, payload: dict) -> str:
        base = (
            "Return only a JSON object matching response_contract, not a stringified object. "
            "Use the exact named Project Sources. The response_contract work_id and task.work_id "
            "are authoritative for this turn; ignore any older work_id from prior turns in this reused Project chat."
        )
        if payload.get("kind") != "translate_chunk":
            return base + " Do not use local tools or agents."

        reference = payload.get("local_source_task")
        if not isinstance(reference, dict):
            raise AutomationError("LOCAL_SOURCE_REFERENCE_INVALID")
        raw_path = reference.get("path")
        expected_sha256 = reference.get("sha256")
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute() or not isinstance(expected_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise AutomationError("LOCAL_SOURCE_REFERENCE_INVALID")
        path = Path(raw_path).expanduser().resolve()
        workspace = (self.root / "workspace").resolve()
        if (str(path) != raw_path or not path.is_relative_to(workspace) or path.parent.name != "tasks" or
                path.parent.parent.name != "translation" or not re.fullmatch(r"[0-9]{4,8}\.json", path.name)):
            raise AutomationError("LOCAL_SOURCE_REFERENCE_INVALID")
        if not path.is_file() or digest(path.read_bytes()) != expected_sha256:
            raise AutomationError("LOCAL_SOURCE_CHANGED")
        document = read_json(path)
        probe = document.get("local_source_probe") if isinstance(document, dict) else None
        if (not isinstance(document, dict) or document.get("work_id") != work_id or document.get("chunk_id") != path.stem or
                payload.get("chunk_id") != path.stem or not isinstance(probe, str) or not re.fullmatch(r"[a-f0-9]{32}", probe)):
            raise AutomationError("LOCAL_SOURCE_REFERENCE_INVALID")
        return (
            base
            + " For this translate_chunk task only, use Chat On Steroids Core `read` to read exactly task.local_source_task.path before translating."
            + " Do not read any other local path and do not use any other local tool, including exec, apply_patch, write_stdin, or agents."
            + " Never modify local files."
        )

    @staticmethod
    def _worker_matches_project_role(worker: dict, project: dict, role: str) -> bool:
        target = worker.get("projectTarget") if isinstance(worker, dict) else None
        return bool(
            isinstance(target, dict)
            and target.get("alias") == project.get("alias")
            and target.get("name") == project.get("name")
            and target.get("url") == project.get("url")
            and target.get("role") == role
        )

    def execute(self, work_id: str, role: str, payload: dict, *, alias="fieldnotes", operation_id: str | None = None):
        if role not in ("translator", "reviewer", "discovery"):
            raise AutomationError("INVALID_WORKER_ROLE")
        if not isinstance(work_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", work_id):
            raise AutomationError("INVALID_WORK_ID")
        worker_instructions = self._worker_instructions(work_id, payload)
        operation_id = operation_id or digest({"work":work_id,"role":role,"alias":alias,"payload":payload})
        if not re.fullmatch(r"[a-zA-Z0-9_-]{12,128}", operation_id):
            raise AutomationError("INVALID_OPERATION_ID")
        directory = self.root / "workspace" / "automation-runs" / "backend" / work_id / role
        pool_directory = self.root / "workspace" / "automation-runs" / "backend" / "_shared" / alias / role
        state_path = directory / f"{operation_id}.json"
        mapping_path = directory / "worker.json"
        # Project translator chats are now a role-level pool rather than permanently bound to
        # one novel. The task-local JSON already contains the work-specific glossary, source,
        # neighboring context and hidden read proof, while Project Sources are global policy.
        # Serializing the role-level claim avoids two independent works racing to wake the same
        # sleeping Project chat.
        with locked(pool_directory / ".lock"), locked(directory / ".lock"):
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
                # A worker that failed before ChatGPT ever assigned a conversation did not
                # execute the operation. That terminal browser/bootstrap failure is therefore
                # safe to retry without risking duplicate model work. Any failure after a chat
                # exists remains terminal and must be inspected explicitly.
                retryable_bootstrap = previous.get("error") == "PROJECT_WORKER_BOOTSTRAP_FAILED"
                if previous.get("error") == "PROJECT_WORKER_FAILED" and previous.get("worker_id") and previous.get("created_at"):
                    # Backward compatibility for states written before the dedicated bootstrap
                    # error code existed. Ask the broker for the exact failed generation; only a
                    # failed worker with no conversation id is reclassified as pre-send.
                    try:
                        old_status = self.bridge.request("/automation-agents/status")
                        old_worker = next((w for w in old_status.get("workers", [])
                            if w.get("id") == previous.get("worker_id") and w.get("createdAt") == previous.get("created_at")), None)
                        retryable_bootstrap = bool(old_worker and old_worker.get("state") == "failed" and not old_worker.get("conversationId"))
                    except AutomationError:
                        retryable_bootstrap = False
                if retryable_bootstrap:
                    previous = {}
                else:
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
                workers = status.get("workers", [])
                mapped_worker = next((w for w in workers if w.get("id") == mapping.get("worker_id") and w.get("createdAt") == mapping.get("created_at")), None)
                compatible = [w for w in workers if self._worker_matches_project_role(w, project, role)]
                sleeping = [w for w in compatible if w.get("state") == "sleeping" and w.get("revivable") is True]
                worker = mapped_worker if mapped_worker in sleeping else (max(sleeping, key=lambda w: int(w.get("createdAt") or 0)) if sleeping else None)
                reusable = worker is not None
                if not reusable and any(w.get("state") in ("active","invited","waking","detached") for w in compatible):
                    raise AutomationError("WORKER_BUSY")
                prompt = json.dumps({"operation_id":operation_id,"work_id":work_id,"task":payload,
                    "response_contract":{"operation_id":operation_id,"work_id":work_id,"payload":"the task's requested JSON result"},
                    "instructions":worker_instructions}, ensure_ascii=False)
                if len(prompt) > 250_000:
                    raise AutomationError("TASK_TOO_LARGE")
                state = {"version":1,"operation_id":operation_id,"fingerprint":fingerprint,"target":target,
                         "state":"submitting","submitted_at":now(),"reused":bool(reusable),
                         "answer_before_submit_sha256":digest(worker.get("answer")) if reusable and isinstance(worker.get("answer"),str) else None}
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
                    if not selected.get("createdAt") or not self._worker_matches_project_role(selected, project, role):
                        raise AutomationError("WORKER_TARGET_NOT_VERIFIED")
                    state.update(state="accepted",worker_id=selected["id"],created_at=selected["createdAt"])
                    atomic_json(state_path,state)
                    atomic_json(mapping_path,{"worker_id":selected["id"],"created_at":selected["createdAt"],"target":target,
                                              "worker_target":selected.get("projectTarget")})
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
                if not worker or not self._worker_matches_project_role(worker, project, role):
                    raise AutomationError("WORKER_TARGET_NOT_VERIFIED")
                if worker.get("state") == "failed":
                    error_code = "PROJECT_WORKER_BOOTSTRAP_FAILED" if not worker.get("conversationId") else "PROJECT_WORKER_FAILED"
                    state.update(state="failed",error=error_code,ended_at=now())
                    atomic_json(state_path,state)
                    raise AutomationError(error_code)
                if worker.get("state") in ("sleeping","finished") and worker.get("complete") is True and isinstance(worker.get("answer"),str):
                    answer = worker["answer"]
                    # A reused sleeping Project worker still exposes its previous completed answer
                    # until the browser has actually delivered and completed the newly queued turn.
                    # Treat that exact pre-submit answer as "not new yet", not as a malformed reply.
                    # Persisting the hash makes the same fence survive a driver restart.
                    previous_hash = state.get("answer_before_submit_sha256")
                    if state.get("reused") and previous_hash and digest(answer) == previous_hash:
                        time.sleep(self.poll_interval)
                        continue
                    try:
                        result = parse_envelope(answer,operation_id,work_id)
                    except AutomationError as error:
                        # Backward-compatible recovery for an already-accepted reused operation
                        # created before answer_before_submit_sha256 existed: an answer explicitly
                        # naming another operation is necessarily historical, so keep waiting.
                        if state.get("reused") and error.code == "RESULT_OPERATION_MISMATCH":
                            time.sleep(self.poll_interval)
                            continue
                        raise
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
