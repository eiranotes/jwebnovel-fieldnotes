#!/usr/bin/env python3
"""Process the existing translation queue through a verified Project worker, without fallback."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from automation_store import AutomationError, atomic_json, digest, locked, now, read_json, within
from project_backend import ProjectBackend
from project_context import build_common, build_work, public_pack, source_probe_task, verify_source_probe
from project_sources import synchronize as synchronize_project_sources
from source_pipeline import sentence_segments, validate_segment_translations, validate_glossary_update

ROOT = Path(__file__).resolve().parent.parent


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
           ROOT/'templates/project-context/PROJECT_INSTRUCTIONS.md',ROOT/'templates/project-context/GLOBAL_CONTEXT.md']
    return digest({str(path.name):digest(path.read_bytes()) for path in files if path.exists()})


def prove_project_sources(backend, work_id: str, chunk_id: str, common: dict, work: dict, *, alias: str,
                          max_attempts: int, retry_seconds: float) -> dict:
    if not 1 <= max_attempts <= 20 or not 0 <= retry_seconds <= 120:
        raise AutomationError('PROJECT_POLICY_INVALID')
    task=source_probe_task(work_id,common,work)
    for attempt in range(1,max_attempts+1):
        # Negative source availability is safe to retry: this operation reads Project Sources and
        # has no queue/state mutation. Each bounded attempt has its own stable id, so a process
        # restart resumes an accepted attempt instead of duplicating it, while a completed
        # source_unavailable response does not poison every future probe forever.
        operation_id=digest({'kind':'probe','work':work_id,'chunk':chunk_id,
                             'sources':[public_pack(common),public_pack(work)],'attempt':attempt})
        answer=backend.execute(work_id,'translator',task,alias=alias,operation_id=operation_id)
        if isinstance(answer,dict) and answer.get('status')=='source_unavailable' and answer.get('work_id')==work_id:
            if attempt == max_attempts: raise AutomationError('PROJECT_SOURCE_UNAVAILABLE')
            time.sleep(retry_seconds)
            continue
        return verify_source_probe(answer,work_id,[common,work])
    raise AutomationError('PROJECT_SOURCE_UNAVAILABLE')


def process_task(task: dict, backend=None, source_sync=None) -> dict:
    work_dir = within(ROOT.resolve(), task['work_dir'])
    if not work_dir.is_relative_to(ROOT.resolve()/'workspace'):
        raise AutomationError('PATH_OUTSIDE_WORKSPACE')
    work_id, chunk_id = task['work_id'], task['chunk_id']
    config = read_json(ROOT/'config/project-translation.json')
    if (config.get('backend') != 'webgpt_project' or config.get('allow_fallback') is not False or
            config.get('activation') != 'verified_live'):
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
        backend = backend or ProjectBackend(ROOT,timeout=int(config.get('worker_timeout_seconds',600)))
        context_path = work_dir/'translation/project-context.json'
        pinned = read_json(context_path,{})
        revision=guide_revision(work_dir)
        if pinned and pinned.get('guide_revision') == revision:
            common, work = pinned['packs']
            for pack in (common, work):
                if digest((ROOT/pack['path']).read_bytes()) != pack['file_sha256']:
                    raise AutomationError('CONTEXT_CACHE_TAMPERED')
        else:
            common, work = build_common(), build_work(work_dir)
        source_sync = source_sync or synchronize_project_sources
        # Every context revision must be provider-listed before any worker is allowed to prove
        # retrieval or translate. synchronize() is exact-filename idempotent and persists an
        # accepted/uncertain operation instead of guessing after transport loss, so running this
        # on every chunk safely becomes a no-op for an unchanged revision and uploads a new WORK
        # snapshot after glossary/guide changes.
        source_sync([common,work],root=ROOT,alias=config['project_alias'],instructions=True)
        # Repeat the probe in this worker/operation before using cached context. Do not count a
        # successful old worker probe as proof that a replacement chat inherited the sources.
        proof_task=source_probe_task(work_id,common,work)
        verification=prove_project_sources(backend,work_id,chunk_id,common,work,alias=config['project_alias'],
            max_attempts=int(config.get('source_probe_max_attempts',6)),
            retry_seconds=float(config.get('source_probe_retry_seconds',10)))
        atomic_json(context_path,{'guide_revision':revision,'packs':[common,work],'proof':verification})
        # Copyrighted chapter text and sentence rows stay local. The WebGPT worker gets only an
        # immutable reference to the already-generated private task JSON, then reads that exact
        # artifact through Core. This removes source duplication from the chat transport while
        # preserving the existing sentence-id/alignment contract in one canonical local file.
        payload={
            'kind':'translate_chunk','entry_id':task.get('entry_id'),'work_id':work_id,'chunk_id':chunk_id,
            'chunk_sha256':source_hash,'local_source_task':local_source_task,
            'project_sources':[public_pack(common),public_pack(work)],
            'source_policy':'Pinned Project Sources plus one exact read-only local translation task; do not claim a new upload.',
            'translation_instruction':'Read local_source_task.path with Chat On Steroids Core read. The JSON contains the private chapter text, sentence-id map, adjacent-source context, glossary, instructions, output contract, and a local read probe. Translate every sentence segment from that file and preserve its exact ids/order.',
            'output_contract':{'local_source_proof':'value read from the local task JSON',
                               'segment_translations':[{'id':'exact sentence id from local task','ko':'string'}],
                               'glossary_update':{'people':{},'places':{},'terms':{},'ruby_notes':{},'decisions':[]},
                               'project_source_proof':'fresh proof required below'},
            'project_source_proof_contract':proof_task['output_contract'],
            'source_proof_instruction':'In this translation result include project_source_proof containing a fresh ready/work_id/sources proof read from the exact named Project Sources. Do not copy expected values from the task (they are not provided).',
        }
        result=backend.execute(work_id,'translator',payload,alias=config['project_alias'])
        if not isinstance(result,dict):raise AutomationError('INVALID_TRANSLATION_RESULT')
        # A rollover between preflight and translation must not inherit an old chat's proof.
        verify_source_probe(result.get('project_source_proof'),work_id,[common,work])
        if result.get('local_source_proof') != local_source_probe:
            raise AutomationError('LOCAL_SOURCE_PROOF_MISMATCH')
        validate_segment_translations(task['source_segments'],result.get('segment_translations'))
        validate_glossary_update(read_json(work_dir/'glossary.json'),result.get('glossary_update') or {})
        result={**result,'work_id':work_id,'chunk_id':chunk_id,'chunk_sha256':source_hash}
        result_path=work_dir/'translation'/f'project-result-{chunk_id}.json'
        atomic_json(result_path,result)
        args=['complete','--chunk',chunk_id,'--result',str(result_path)]
        if task.get('full_translation_request_id'):
            args += ['--request',task['full_translation_request_id']]
        else:
            args += ['--entry',task['entry_id'],'--work',work_id]
        outcome=script_json('translation_queue.py',args)
        return {'status':'complete','backend':'webgpt_project','work_id':work_id,'chunk':chunk_id,
                'context_versions':[p['context_version'] for p in (common,work)],'completion':outcome}


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
        print(json.dumps({'status':'blocked','error':error.code,'completed':outcomes},ensure_ascii=False))
        return 1

if __name__=='__main__':raise SystemExit(main())
