"""A resumable Project-only client of the local Steroids bridge, not an OpenAI API client."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from automation_store import AutomationError, atomic_json, digest, locked, now, read_json
from local_translation_task import validate_local_source_task
from learning_store import safe_observe


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
        # The Steroids loopback bridge has its own all-route rolling-minute limiter. A 429 from
        # that limiter is emitted before the requested route performs any action, so retrying the
        # same local request is safe (unlike an ambiguous network failure after a write). Two
        # active browser recorders can briefly consume most of that allowance; back off across a
        # full minute rather than turning a local bookkeeping throttle into a model-operation
        # failure or launching replacement chats.
        local_429_delays = (1.0, 2.0, 4.0, 8.0, 16.0, 30.0)
        for attempt in range(len(local_429_delays) + 1):
            request = urllib.request.Request(self.base + route, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                try:
                    detail = json.load(error)
                except (ValueError, OSError):
                    detail = {}
                code = str(detail.get("error", f"BRIDGE_HTTP_{error.code}"))
                if error.code == 429 and code == "rate_limited" and attempt < len(local_429_delays):
                    time.sleep(local_429_delays[attempt])
                    continue
                # Do not echo server prose into public status; it can contain worker source text.
                raise AutomationError(code) from error
            except (OSError, ValueError) as error:
                raise AutomationError("BRIDGE_TRANSPORT_UNCERTAIN") from error
        raise AutomationError("rate_limited")


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
    def __init__(self, root: Path, bridge=None, *, timeout=600, poll_interval=3.0) -> None:
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
        base = "Return only a JSON object matching response_contract, not a stringified object. Use the exact named Project Sources."
        if payload.get("kind") != "translate_chunk":
            return base + " Do not use local tools or agents."
        validate_local_source_task(self.root, work_id, payload)
        return (
            base
            + " For this translate_chunk task only, use Chat On Steroids Core `read` to read exactly task.local_source_task.path before translating."
            + " Do not read any other local path and do not use any other local tool, including exec, apply_patch, write_stdin, or agents."
            + " Never modify local files."
        )

    def execute(self, work_id: str, role: str, payload: dict, *, alias="fieldnotes", operation_id: str | None = None):
        if role not in ("translator", "reviewer", "discovery"):
            raise AutomationError("INVALID_WORKER_ROLE")
        if not isinstance(work_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", work_id):
            raise AutomationError("INVALID_WORK_ID")
        conversation_title=payload.get('conversation_title')
        if conversation_title is not None and (
            not isinstance(conversation_title,str) or not conversation_title.strip() or
            len(conversation_title)>200 or any(ord(ch)<32 for ch in conversation_title)
        ):
            raise AutomationError('INVALID_CONVERSATION_TITLE')
        worker_instructions = self._worker_instructions(work_id, payload)
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
            project = self._project(alias)
            target = {**project, "workId":work_id,"role":role}
            if previous.get("state") == "submitting":
                raise AutomationError("OPERATION_SUBMISSION_UNCERTAIN", "inspect the accepted worker before retrying")
            if previous.get("state") == "uncertain":
                # A lost spawn reply is normally untouchable: the browser may already have the
                # task, so retrying could duplicate model work.  There is one provably pre-send
                # shape, however: the local submission never learned any worker identity and a
                # successful broker status read contains no generation for this exact Project
                # target.  The broker retains failed/sleeping generations, so exact absence is
                # positive evidence that no worker/chat survived the spawn transaction.  Only
                # that shape may be reclassified as a bootstrap failure and retried.
                no_local_worker = not any(previous.get(k) for k in ("worker_id", "created_at", "conversation_id"))
                if no_local_worker:
                    try:
                        uncertain_status = self.bridge.request("/automation-agents/status")
                        exact_uncertain = [w for w in uncertain_status.get("workers", []) if w.get("projectTarget") == target]
                    except AutomationError:
                        exact_uncertain = None
                    if exact_uncertain == []:
                        safe_observe(
                            "translation", "identityless_uncertain_spawn", "confirmed",
                            scope="durability", note="exact broker target absent; safe pre-send recovery", root=self.root,
                        )
                        previous.update(
                            state="failed",
                            error="PROJECT_WORKER_BOOTSTRAP_FAILED",
                            recovered_at=now(),
                            recovery="broker_exact_target_absent_after_identityless_uncertain",
                        )
                        atomic_json(state_path, previous)
                        previous = {}
                    else:
                        raise AutomationError("OPERATION_SUBMISSION_UNCERTAIN", "inspect the accepted worker before retrying")
                else:
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
                exact = [w for w in workers if w.get("projectTarget") == target]
                sleeping = [w for w in exact if w.get("state") == "sleeping" and w.get("revivable") is True]
                worker = mapped_worker if mapped_worker in sleeping else (max(sleeping, key=lambda w: int(w.get("createdAt") or 0)) if sleeping else None)
                reusable = worker is not None
                if not reusable and any(w.get("state") in ("active","invited","waking","detached") for w in exact):
                    raise AutomationError("WORKER_BUSY")
                prompt = json.dumps({"operation_id":operation_id,"work_id":work_id,
                    "transport_marker":"(Fieldnotes Project worker: generated automation task; not user-authored draft)","task":payload,
                    "response_contract":{"operation_id":operation_id,"work_id":work_id,"payload":"the task's requested JSON result"},
                    "instructions":worker_instructions}, ensure_ascii=False)
                if len(prompt) > 250_000:
                    raise AutomationError("TASK_TOO_LARGE")
                state = {"version":1,"operation_id":operation_id,"fingerprint":fingerprint,"target":target,
                         "conversation_title":conversation_title,
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
                            "label":conversation_title or f"{work_id[:40]}-{role}","task":prompt,
                            "target":{"type":"chatgpt_project","project":alias,"workId":work_id,"role":role}}]}, method="POST")
                        selected = response["workers"][0]
                    if not selected.get("createdAt") or selected.get("projectTarget") != target:
                        raise AutomationError("WORKER_TARGET_NOT_VERIFIED")
                    state.update(state="accepted",worker_id=selected["id"],created_at=selected["createdAt"])
                    atomic_json(state_path,state)
                    atomic_json(mapping_path,{"worker_id":selected["id"],"created_at":selected["createdAt"],"target":target,
                                              "conversation_title":conversation_title})
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
                    broker = str(worker.get('brokerResult') or worker.get('result') or '')
                    if 'CHATGPT_CONVERSATION_RATE_LIMITED_AFTER_SEND' in broker:
                        safe_observe(
                            "translation", "CHATGPT_CONVERSATION_RATE_LIMITED", "observed",
                            scope="scheduler", note="after-send provider rate limit", root=self.root,
                        )
                        # The submit click already crossed the irreversible boundary. Do not
                        # classify this as a safe bootstrap retry: the server may still have the
                        # message even though conversation hydration was throttled.
                        state.update(state='uncertain',last_error='CHATGPT_CONVERSATION_RATE_LIMITED',
                                     last_error_detail=broker[-500:],ended_at=now())
                        atomic_json(state_path,state)
                        raise AutomationError('CHATGPT_CONVERSATION_RATE_LIMITED')
                    if 'CHATGPT_CONVERSATION_RATE_LIMITED' in broker:
                        safe_observe(
                            "translation", "CHATGPT_CONVERSATION_RATE_LIMITED", "confirmed",
                            scope="scheduler", note="pre-send provider rate limit; stop new launches", root=self.root,
                        )
                        # Pre-send throttle is safe to retry later after a cooldown. Persist it as
                        # the existing retryable bootstrap class, while surfacing a specific code
                        # to the scheduler so it stops launching more work now.
                        state.update(state='failed',error='PROJECT_WORKER_BOOTSTRAP_FAILED',
                                     last_error='CHATGPT_CONVERSATION_RATE_LIMITED',
                                     last_error_detail=broker[-500:],ended_at=now())
                        atomic_json(state_path,state)
                        raise AutomationError('CHATGPT_CONVERSATION_RATE_LIMITED')
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
                        if error.code == "INVALID_MODEL_JSON":
                            bad_hash = digest(answer)
                            repair_state = state.get("json_repair_state")
                            repair_source = state.get("json_repair_source_sha256")
                            if repair_state == "uncertain":
                                raise AutomationError(
                                    "OPERATION_SUBMISSION_UNCERTAIN",
                                    "JSON repair delivery is uncertain; do not repeat it automatically",
                                )
                            if repair_state == "accepted" and repair_source == bad_hash:
                                # The repair wake has been accepted but the broker still exposes
                                # the malformed prior answer. Wait for the same conversation to
                                # finish its correction rather than sending the repair twice.
                                time.sleep(self.poll_interval)
                                continue
                            if not repair_state:
                                repair_prompt = json.dumps({
                                    "kind":"fieldnotes_json_repair",
                                    "operation_id":operation_id,
                                    "work_id":work_id,
                                    "instructions":(
                                        "Your immediately previous answer for this exact operation was not valid JSON. "
                                        "Do not reread source, use tools, retranslate, summarize, or change translation choices. "
                                        "Return only the same required JSON envelope again with JSON syntax corrected. "
                                        "Preserve every segment id/order, Korean translation, local_source_proof, "
                                        "project_source_proof, and glossary_update from that answer."
                                    ),
                                }, ensure_ascii=False)
                                state.update(
                                    json_repair_state="submitting",
                                    json_repair_source_sha256=bad_hash,
                                    json_repair_requested_at=now(),
                                )
                                atomic_json(state_path,state)
                                try:
                                    self.bridge.request("/automation-agents/message", {
                                        "to":worker["id"],"expectedCreatedAt":worker["createdAt"],"text":repair_prompt,
                                    },method="POST")
                                    state["json_repair_state"]="accepted"
                                    atomic_json(state_path,state)
                                except Exception:
                                    state["json_repair_state"]="uncertain"
                                    atomic_json(state_path,state)
                                    raise
                                time.sleep(self.poll_interval)
                                continue
                            # One accepted repair returned a different answer that is still
                            # malformed. Escalate to the configured fallback rather than looping.
                            raise
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
                    if state.get("json_repair_state") == "accepted":
                        safe_observe(
                            "translation", "INVALID_MODEL_JSON", "confirmed",
                            scope="model_output", note="same-work JSON repair returned a valid envelope", root=self.root,
                        )
                    mapping = read_json(mapping_path, {})
                    mapping.update({
                        "worker_id": state["worker_id"],
                        "created_at": state["created_at"],
                        "target": target,
                        "conversation_title": conversation_title,
                        "conversation_id": worker.get("conversationId"),
                    })
                    atomic_json(mapping_path, mapping)
                    return result
                time.sleep(self.poll_interval)
            # Accepted work is retained for result polling on resume; never auto-resubmitted.
            state.update(last_error="WORKER_RESULT_TIMEOUT",last_wait_at=now())
            atomic_json(state_path,state)
            raise AutomationError("WORKER_RESULT_TIMEOUT")
