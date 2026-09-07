#!/usr/bin/env python3
"""Translate the durable queue through a work-specific Project chat with a verified fallback lane."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path

from learning_store import safe_observe
from types import SimpleNamespace

from automation_store import AutomationError, atomic_json, digest, locked, now, read_json, within
from codex_webgpt_backend import CodexWebGptBackend
from project_backend import ProjectBackend
from project_context import build_common_packs, public_pack, source_probe_task, verify_source_probe
from project_sources import synchronize as synchronize_project_sources
from source_pipeline import sentence_segments, validate_segment_translations, validate_glossary_update

ROOT = Path(__file__).resolve().parent.parent


def close_project_worker_tabs(work_id: str, role: str = 'translator') -> dict:
    """Close Chrome views for one exact Project conversation while preserving worker mapping.

    A sleeping Fieldnotes worker is intentionally revivable from its conversation id.  Closing
    its browser tab after the *work* is complete therefore frees Chrome without deleting or
    replacing the conversation.  The exact id fence prevents unrelated ChatGPT tabs from being
    touched.  This is best-effort presentation cleanup; translation completion never depends on
    AppleScript being available.
    """
    mapping_path = ROOT/'workspace'/'automation-runs'/'backend'/work_id/role/'worker.json'
    mapping = read_json(mapping_path, {})
    conversation_id = mapping.get('conversation_id')
    if not isinstance(conversation_id, str) or not conversation_id:
        return {'status':'skipped','reason':'conversation_id_unavailable','closed':0}
    # Conversation ids are server-issued UUID-like values. Keep this exact and fail closed.
    if not all(ch in '0123456789abcdefABCDEF-' for ch in conversation_id) or len(conversation_id) < 8:
        return {'status':'skipped','reason':'invalid_conversation_id','closed':0}
    script = r'''
on run argv
set cid to item 1 of argv
set closedCount to 0
tell application "Google Chrome"
    repeat with w in windows
        repeat with i from (count of tabs of w) to 1 by -1
            set t to tab i of w
            set u to URL of t
            if (u starts with "https://chatgpt.com/") and (u contains ("/c/" & cid)) then
                close t
                set closedCount to closedCount + 1
            end if
        end repeat
    end repeat
end tell
return closedCount as text
end run
'''
    try:
        proc = subprocess.run(['osascript','-e',script,conversation_id],capture_output=True,text=True,timeout=15)
        if proc.returncode != 0:
            return {'status':'unconfirmed','reason':proc.stderr.strip()[:200],'closed':0,'conversation_id':conversation_id}
        try:
            closed = int(proc.stdout.strip() or '0')
        except ValueError:
            closed = 0
        return {'status':'complete','closed':closed,'conversation_id':conversation_id}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'status':'unconfirmed','reason':type(error).__name__,'closed':0,'conversation_id':conversation_id}


def script_json(script: str, arguments: list[str]) -> dict:
    process = subprocess.run([sys.executable, str(ROOT/'scripts'/script), *arguments], cwd=ROOT, capture_output=True, text=True)
    if process.returncode:
        raise AutomationError('PIPELINE_SUBPROCESS_FAILED', script)
    try:
        return json.loads(process.stdout)
    except ValueError as error:
        raise AutomationError('PIPELINE_INVALID_JSON', script) from error


def guide_revision(work_dir: Path) -> str:
    files=[work_dir/'metadata.json',work_dir/'glossary.json',*(work_dir/name for name in ('translation-guide.md','character-guide.md','style-guide.md')),
           ROOT/'templates/project-context/PROJECT_INSTRUCTIONS.md',ROOT/'templates/project-context/GLOBAL_CONTEXT.md',
           ROOT/'templates/project-context/TRANSLATION_RULES.md',ROOT/'templates/project-context/USER_INSTRUCTIONS.md']
    return digest({str(path.name):digest(path.read_bytes()) for path in files if path.exists()})


def conversation_title(work_dir: Path, task: dict) -> str:
    """Stable human title for the one Project conversation owned by this novel."""
    metadata=read_json(work_dir/'metadata.json',{})
    regex=__import__('re').compile(r'^(\d{4})-(\d{2})-(\d{2})')
    match=None
    for candidate in (task.get('entry_id'),metadata.get('entry_id'),*work_dir.parts):
        match=regex.match(str(candidate or ''))
        if match:break
    if not match:
        raise AutomationError('ENTRY_DATE_UNAVAILABLE')
    stamp=match.group(1)[2:]+match.group(2)+match.group(3)
    title=' '.join(str(metadata.get('title') or '').split()).strip()
    if not title:
        raise AutomationError('WORK_TITLE_UNAVAILABLE')
    # ChatGPT accepts long human titles, but cap pathological metadata before it enters browser UI.
    return f'{stamp}-{title}'[:200]


def prove_project_sources(backend, work_id: str, chunk_id: str, packs: list[dict], *, alias: str,
                          max_attempts: int, retry_seconds: float, conversation_title: str | None = None) -> dict:
    if not 1 <= max_attempts <= 20 or not 0 <= retry_seconds <= 120:
        raise AutomationError('PROJECT_POLICY_INVALID')
    task=source_probe_task(work_id,*packs,conversation_title=conversation_title)
    for attempt in range(1,max_attempts+1):
        # Negative source availability is safe to retry: this operation reads Project Sources and
        # has no queue/state mutation. Each bounded attempt has its own stable id, so a process
        # restart resumes an accepted attempt instead of duplicating it, while a completed
        # source_unavailable response does not poison every future probe forever.
        operation_id=digest({'kind':'probe','work':work_id,'chunk':chunk_id,
                             'sources':[public_pack(pack) for pack in packs],'attempt':attempt})
        try:
            answer=backend.execute(work_id,'translator',task,alias=alias,operation_id=operation_id)
        except AutomationError as error:
            # A fresh Project chat that failed before receiving a conversation id executed no
            # model work. Treat that definitive browser/bootstrap failure like source indexing
            # unavailability: bounded retry is safe and cannot duplicate a probe or translation.
            if error.code == 'PROJECT_WORKER_BOOTSTRAP_FAILED':
                if attempt == max_attempts: raise
                time.sleep(min(retry_seconds,3))
                continue
            raise
        if isinstance(answer,dict) and answer.get('status')=='source_unavailable' and answer.get('work_id')==work_id:
            if attempt == max_attempts: raise AutomationError('PROJECT_SOURCE_UNAVAILABLE')
            time.sleep(retry_seconds)
            continue
        return verify_source_probe(answer,work_id,packs)
    raise AutomationError('PROJECT_SOURCE_UNAVAILABLE')


def fallback_allowed(config: dict, error: AutomationError) -> bool:
    fallback=config.get('fallback') if isinstance(config.get('fallback'),dict) else {}
    return bool(
        fallback.get('enabled') is True
        and fallback.get('backend') == 'codex_webgpt'
        and error.code in set(fallback.get('trigger_codes') or [])
    )


def validate_translation_result(result: dict, task: dict, work_dir: Path, local_source_probe: str,
                                *, work_id: str, project_packs: list[dict] | None = None) -> dict:
    if not isinstance(result,dict):
        raise AutomationError('INVALID_TRANSLATION_RESULT')
    if project_packs is not None:
        verify_source_probe(result.get('project_source_proof'),work_id,project_packs)
    if result.get('local_source_proof') != local_source_probe:
        raise AutomationError('LOCAL_SOURCE_PROOF_MISMATCH')
    validate_segment_translations(task['source_segments'],result.get('segment_translations'))
    validate_glossary_update(read_json(work_dir/'glossary.json'),result.get('glossary_update') or {})
    return result


def process_task(task: dict, backend=None, source_sync=None, fallback_backend=None) -> dict:
    work_dir = within(ROOT.resolve(), task['work_dir'])
    if not work_dir.is_relative_to(ROOT.resolve()/'workspace'):
        raise AutomationError('PATH_OUTSIDE_WORKSPACE')
    work_id, chunk_id = task['work_id'], task['chunk_id']
    config = read_json(ROOT/'config/project-translation.json')
    fallback_cfg=config.get('fallback') if isinstance(config.get('fallback'),dict) else {}
    if (config.get('backend') != 'webgpt_project' or config.get('activation') != 'verified_live' or
            (fallback_cfg.get('enabled') is True and fallback_cfg.get('backend') != 'codex_webgpt')):
        raise AutomationError('PROJECT_POLICY_INVALID')
    with locked(work_dir/'translation/project-run.lock'):
        source_path = (work_dir/'translation/chunks'/chunk_id/'ja.txt').resolve()
        source = source_path.read_text(encoding='utf-8')
        source_hash = digest(source.encode())
        local_task_path = (work_dir/'translation/tasks'/f'{chunk_id}.json').resolve()
        local_task = read_json(local_task_path)
        expected_segments = sentence_segments(source)
        local_source_probe = local_task.get('local_source_probe') if isinstance(local_task,dict) else None
        if (source != task.get('source_ja') or source_hash != task.get('chunk_sha256',source_hash) or
                local_task.get('work_id') != work_id or local_task.get('chunk_id') != chunk_id or
                local_task.get('source_ja') != source or local_task.get('chunk_sha256') != source_hash or
                local_task.get('source_segments') != expected_segments or task.get('source_segments') != expected_segments or
                not isinstance(local_source_probe,str) or len(local_source_probe) != 32 or any(c not in '0123456789abcdef' for c in local_source_probe)):
            raise AutomationError('SOURCE_CHANGED')
        local_source_task = {
            'path': str(local_task_path),
            'sha256': digest(local_task_path.read_bytes()),
            'encoding': 'utf-8',
            'format': 'fieldnotes_translation_task_json_v1',
        }
        primary_backend = backend
        context_path = work_dir/'translation/project-context.json'
        pinned = read_json(context_path,{})
        revision=guide_revision(work_dir)
        if pinned and pinned.get('guide_revision') == revision and len(pinned.get('packs') or []) == 3:
            project_packs = pinned['packs']
            for pack in project_packs:
                if digest((ROOT/pack['path']).read_bytes()) != pack['file_sha256']:
                    raise AutomationError('CONTEXT_CACHE_TAMPERED')
        else:
            project_packs = build_common_packs()
        source_sync = source_sync or synchronize_project_sources
        chat_title=conversation_title(work_dir,task)
        # All novels share these three immutable Project-wide sources. Work metadata, glossary,
        # adjacent context and chapter text stay in the exact local task JSON, while conversation
        # ownership supplies the novel-specific long-lived model context.
        proof_task=source_probe_task(work_id,*project_packs,conversation_title=chat_title)
        base_payload={
            'kind':'translate_chunk','entry_id':task.get('entry_id'),'work_id':work_id,'chunk_id':chunk_id,
            'conversation_title':chat_title,
            'chunk_sha256':source_hash,'local_source_task':local_source_task,
            'translation_instruction':'Read the exact local task JSON. It contains the private chapter text, sentence-id map, adjacent-source context, glossary, instructions, output contract, and a local read probe. Translate every sentence segment and preserve its exact ids/order.',
            'output_contract':{'local_source_proof':'value read from the local task JSON',
                               'segment_translations':[{'id':'exact sentence id from local task','ko':'string'}],
                               'glossary_update':{'people':{},'places':{},'terms':{},'ruby_notes':{},'decisions':[]}},
        }
        primary_payload={
            **base_payload,
            'project_sources':[public_pack(pack) for pack in project_packs],
            'source_policy':'Pinned Project Sources plus one exact read-only local translation task; do not claim a new upload.',
            'output_contract':{**base_payload['output_contract'],'project_source_proof':'fresh proof required below'},
            'project_source_proof_contract':proof_task['output_contract'],
            'source_proof_instruction':'In this translation result include project_source_proof containing a fresh ready/work_id/sources proof read from the exact named Project Sources. Do not copy expected values from the task (they are not provided).',
        }
        selected_backend='webgpt_project';fallback_reason=None
        try:
            if primary_backend is None:
                primary_backend=ProjectBackend(ROOT,timeout=int(config.get('worker_timeout_seconds',600)))
            source_sync(project_packs,root=ROOT,alias=config['project_alias'],instructions=False)
            # One model turn per chunk. The translation result itself must return the exact
            # Project-source probes, so a separate probe conversation turn only doubles request
            # pressure without adding a stronger proof. UI source sync remains idempotent/cached.
            result=primary_backend.execute(work_id,'translator',primary_payload,alias=config['project_alias'])
            validate_translation_result(result,task,work_dir,local_source_probe,work_id=work_id,project_packs=project_packs)
            atomic_json(context_path,{'guide_revision':revision,'packs':project_packs,
                                      'proof':result.get('project_source_proof'),'backend':'webgpt_project',
                                      'conversation_title':chat_title})
        except AutomationError as primary_error:
            if not fallback_allowed(config,primary_error):
                raise
            selected_backend='codex_webgpt';fallback_reason=primary_error.code
            fallback_backend = fallback_backend or CodexWebGptBackend(
                ROOT,timeout=int(fallback_cfg.get('timeout_seconds',900)))
            fallback_operation_id='fallback-'+digest({'work':work_id,'chunk':chunk_id,'source':source_hash,'reason':primary_error.code})
            result=fallback_backend.execute(work_id,base_payload,operation_id=fallback_operation_id)
            validate_translation_result(result,task,work_dir,local_source_probe,work_id=work_id)
            atomic_json(context_path,{'guide_revision':revision,'packs':project_packs,'proof':None,
                                      'backend':'codex_webgpt','primary_error':primary_error.code,
                                      'conversation_title':chat_title})
        result={**result,'work_id':work_id,'chunk_id':chunk_id,'chunk_sha256':source_hash}
        result_path=work_dir/'translation'/f'translation-result-{chunk_id}.json'
        atomic_json(result_path,result)
        args=['complete','--chunk',chunk_id,'--result',str(result_path)]
        if task.get('full_translation_request_id'):
            args += ['--request',task['full_translation_request_id']]
        else:
            args += ['--entry',task['entry_id'],'--work',work_id]
        outcome=script_json('translation_queue.py',args)
        cleanup = None
        if (selected_backend == 'webgpt_project' and isinstance(primary_backend, ProjectBackend)
                and int(outcome.get('done', 0)) >= int(outcome.get('total', 0)) > 0):
            cleanup = close_project_worker_tabs(work_id)
        return {'status':'complete','backend':selected_backend,'fallback_reason':fallback_reason,'work_id':work_id,'chunk':chunk_id,
                'conversation_title':chat_title,
                'context_versions':[p['context_version'] for p in project_packs],'completion':outcome,
                'tab_cleanup':cleanup}


def next_task(work_id=None,entry=None):
    if work_id:
        if not entry:raise AutomationError('ENTRY_REQUIRED')
        import source_pipeline
        capture=io.StringIO()
        with contextlib.redirect_stdout(capture):
            source_pipeline.next_task(SimpleNamespace(work_dir=None,entry=entry,work=work_id,context_tail=700,context_head=500))
        value=capture.getvalue().strip()
        if value.startswith('{'):return json.loads(value)
        return read_json(Path(value))
    return script_json('translation_queue.py',['next'])


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work');parser.add_argument('--entry');parser.add_argument('--max-chunks',type=int,default=1)
    args=parser.parse_args()
    if not 1 <= args.max_chunks <= 100:raise SystemExit('--max-chunks must be 1..100')
    outcomes=[]
    try:
        for _ in range(args.max_chunks):
            task=next_task(args.work,args.entry)
            if task.get('status')=='complete':break
            outcomes.append(process_task(task))
        print(json.dumps({'status':'complete','results':outcomes},ensure_ascii=False,indent=2))
        return 0
    except AutomationError as error:
        safe_observe('translation', error.code, 'observed', scope='pipeline', note='translate_project blocked', root=ROOT)
        print(json.dumps({'status':'blocked','error':error.code,'completed':outcomes},ensure_ascii=False))
        return 1

if __name__=='__main__':raise SystemExit(main())
