"""Fail-closed fallback: local Codex prepares the instruction, Oracle WebGPT performs translation."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from automation_store import AutomationError, atomic_json, digest, locked, now, read_json
from local_translation_task import validate_local_source_task
from project_backend import parse_envelope


class CodexWebGptBackend:
    """A separate, durable fallback lane that never commits translation itself."""

    def __init__(self, root: Path, *, timeout: int = 900, runner=subprocess.run,
                 codex_command: str | None = None, oracle_command: str | None = None,
                 chrome_profile_root: str | Path | None = None) -> None:
        self.root = root.resolve()
        self.timeout = timeout
        self.runner = runner
        self.codex_command = codex_command or shutil.which("codex") or ""
        self.oracle_command = oracle_command or shutil.which("oracle") or ""
        configured_profile = chrome_profile_root or os.environ.get("FIELDNOTES_ORACLE_COPY_PROFILE")
        self.chrome_profile_root = Path(configured_profile).expanduser() if configured_profile else (
            Path.home()/"Library/Application Support/Google/Chrome"
        )

    def execute(self, work_id: str, payload: dict, *, operation_id: str | None = None) -> dict:
        if not self.codex_command:
            raise AutomationError("CODEX_FALLBACK_UNAVAILABLE")
        if not self.oracle_command:
            raise AutomationError("WEBGPT_FALLBACK_UNAVAILABLE")
        if not self.chrome_profile_root.is_dir():
            raise AutomationError("WEBGPT_FALLBACK_PROFILE_UNAVAILABLE")
        if payload.get("kind") != "translate_chunk":
            raise AutomationError("FALLBACK_TASK_UNSUPPORTED")

        task_path, local_task, _ = validate_local_source_task(self.root, work_id, payload)
        operation_id = operation_id or digest({"backend":"codex_webgpt","work":work_id,"payload":payload})
        if not re.fullmatch(r"[a-zA-Z0-9_-]{12,128}", operation_id):
            raise AutomationError("INVALID_OPERATION_ID")
        directory = self.root / "workspace" / "automation-runs" / "fallback" / work_id
        state_path = directory / f"{operation_id}.json"
        result_path = directory / f"{operation_id}.result.json"
        planner_path = directory / f"{operation_id}.planner.txt"
        oracle_path = directory / f"{operation_id}.oracle.txt"
        fingerprint = digest({"work":work_id,"payload":payload})

        with locked(directory / ".lock"):
            previous = read_json(state_path, {})
            if previous and previous.get("fingerprint") != fingerprint:
                raise AutomationError("OPERATION_REQUEST_CONFLICT")
            if previous.get("state") == "complete":
                result = read_json(result_path)
                if digest(result) != previous.get("result_sha256"):
                    raise AutomationError("RESULT_CACHE_TAMPERED")
                return result
            if previous.get("state") in {"oracle_submitting", "oracle_uncertain"}:
                raise AutomationError("FALLBACK_SUBMISSION_UNCERTAIN")
            if previous.get("state") == "failed":
                raise AutomationError(str(previous.get("error") or "FALLBACK_FAILED"))

            directory.mkdir(parents=True, exist_ok=True)
            state = {
                "version":1,"operation_id":operation_id,"fingerprint":fingerprint,
                "work_id":work_id,"chunk_id":payload.get("chunk_id"),"state":"planning",
                "created_at":now()
            }
            atomic_json(state_path,state)

            planner_prompt = (
                "You are the local orchestration planner for a Japanese-to-Korean web-novel translation fallback. "
                "Do NOT translate the novel and do not reproduce its source text. Read the exact local task JSON at "
                f"{task_path}. Produce only a concise instruction for a separate WebGPT translator. The instruction must "
                "require every sentence id in original order, natural Korean prose, glossary/ruby consistency, no omissions, "
                "the exact local_source_probe from the task, and JSON-only output. Do not add commentary."
            )
            planner = self.runner(
                [self.codex_command,"-a","never","exec","--ephemeral","--sandbox","read-only",
                 "-C",str(self.root),"-o",str(planner_path),planner_prompt],
                cwd=self.root,capture_output=True,text=True,timeout=min(self.timeout,300)
            )
            if planner.returncode != 0 or not planner_path.is_file():
                state.update(state="failed",error="CODEX_FALLBACK_PLANNER_FAILED",ended_at=now())
                atomic_json(state_path,state)
                raise AutomationError("CODEX_FALLBACK_PLANNER_FAILED")
            planner_text = planner_path.read_text(encoding="utf-8").strip()
            if not planner_text or len(planner_text) > 24_000:
                state.update(state="failed",error="CODEX_FALLBACK_PLANNER_INVALID",ended_at=now())
                atomic_json(state_path,state)
                raise AutomationError("CODEX_FALLBACK_PLANNER_INVALID")

            # Codex contributes orchestration guidance only. The fixed controller contract is
            # authoritative so a poor planner response cannot weaken the alignment/proof boundary.
            oracle_prompt = (
                "Translate the attached Fieldnotes task JSON from Japanese to natural Korean. "
                "The attachment is the only source of chapter text. Follow its source_segments, glossary, adjacent context, "
                "ruby and instructions. Return exactly one JSON object and no markdown/prose. Required envelope:\n"
                f'{{"operation_id":"{operation_id}","work_id":"{work_id}","payload":'
                '{"local_source_proof":"copy local_source_probe from attachment",'
                '"segment_translations":[{"id":"exact sentence id","ko":"Korean translation"}],'
                '"glossary_update":{"people":{},"places":{},"terms":{},"ruby_notes":{},"decisions":[]}}}\n'
                "Every sentence segment must appear exactly once in the original order. Never merge, split, omit, add, or summarize. "
                "Do not include project_source_proof because this is the explicit fallback lane.\n\n"
                "Codex orchestration note (subordinate to the fixed contract above):\n" + planner_text
            )
            slug = f"fieldnotes-{work_id[:24]}-{str(payload.get('chunk_id') or 'chunk')}"
            state.update(state="oracle_submitting",planner_sha256=digest(planner_text),oracle_session=slug,
                         oracle_started_at=now())
            atomic_json(state_path,state)
            try:
                oracle = self.runner(
                    [self.oracle_command,"--engine","browser","--copy-profile",str(self.chrome_profile_root),"--model","gpt-5.6-sol",
                     "--chatgpt-url","https://chatgpt.com/","--browser-thinking-time","extra-high","--browser-archive","auto",
                     "--wait","--timeout",str(self.timeout),
                     "--slug",slug,"--write-output",str(oracle_path),"--file",str(task_path),"-p",oracle_prompt],
                    cwd=self.root,capture_output=True,text=True,timeout=self.timeout + 60
                )
            except subprocess.TimeoutExpired as error:
                state.update(state="oracle_uncertain",error="FALLBACK_SUBMISSION_UNCERTAIN",ended_at=now())
                atomic_json(state_path,state)
                raise AutomationError("FALLBACK_SUBMISSION_UNCERTAIN") from error
            if oracle.returncode != 0 or not oracle_path.is_file() or not oracle_path.read_text(encoding="utf-8").strip():
                state.update(state="oracle_uncertain",error="FALLBACK_SUBMISSION_UNCERTAIN",ended_at=now())
                atomic_json(state_path,state)
                raise AutomationError("FALLBACK_SUBMISSION_UNCERTAIN")

            try:
                result = parse_envelope(oracle_path.read_text(encoding="utf-8"),operation_id,work_id)
            except AutomationError as error:
                state.update(state="failed",error=error.code,ended_at=now())
                atomic_json(state_path,state)
                raise
            # Preserve no source text in durable fallback metadata/results beyond the model's
            # translation payload. The canonical private task remains the sole source artifact.
            atomic_json(result_path,result)
            state.update(state="complete",result_sha256=digest(result),ended_at=now(),
                         local_task_sha256=digest(task_path.read_bytes()),source_probe_present=bool(local_task.get("local_source_probe")))
            atomic_json(state_path,state)
            return result
