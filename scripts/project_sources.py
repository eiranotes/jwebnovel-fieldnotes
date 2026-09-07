#!/usr/bin/env python3
"""Synchronize immutable context packs through the verified Project Sources UI."""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from urllib.parse import quote
from automation_store import AutomationError, atomic_json, digest, locked, now, read_json, within
from project_backend import BridgeClient
from project_context import build_common, build_work, public_pack
ROOT=Path(__file__).resolve().parent.parent


def synchronize(packs: list[dict], *, root: Path=ROOT, bridge=None, alias='fieldnotes', instructions=False, timeout=150, poll_interval=1.0) -> dict:
    bridge=bridge or BridgeClient()
    registry=bridge.request('/automation-projects/registry')
    target=registry.get('entries',{}).get(alias)
    if not target: raise AutomationError('PROJECT_TARGET_NOT_VERIFIED')
    files=[]
    for pack in packs:
        path=within(root/'workspace',root/pack['path'])
        body=path.read_bytes()
        if digest(body)!=pack['file_sha256']: raise AutomationError('CONTEXT_CACHE_TAMPERED')
        files.append({'filename':pack['filename'],'sha256':pack['file_sha256'],'text':body.decode('utf-8')})
    if len(files)>8 or len({f['filename'] for f in files})!=len(files):raise AutomationError('INVALID_CONTEXT_BATCH')
    body={'name':target['name'],'projectAlias':alias,'sourceFiles':files}
    if instructions:
        body['projectInstructions']=(root/'templates/project-context/PROJECT_INSTRUCTIONS.md').read_text(encoding='utf-8')
    fingerprint=digest({'target':target['url'],'body':body})
    directory=root/'workspace/project-context/sync'/alias
    state_path=directory/f'{fingerprint}.json'
    with locked(directory/'.lock'):
        state=read_json(state_path,{})
        if state.get('state')=='complete':return state
        if state.get('state') in ('submitting','uncertain'):
            raise AutomationError('PROJECT_SYNC_OUTCOME_UNCERTAIN')
        if state.get('state')=='failed':raise AutomationError('PROJECT_SYNC_FAILED')
        if state.get('state')!='accepted':
            state={'version':1,'fingerprint':fingerprint,'target':{k:target[k] for k in ('alias','name','url')},'state':'submitting','started_at':now(),'sources':[public_pack(p) for p in packs]}
            atomic_json(state_path,state)
            try:
                receipt=bridge.request('/automation-projects/inspect',body,method='POST')
                command_id=receipt.get('commandId')
                if not command_id:raise AutomationError('PROJECT_SYNC_RECEIPT_MISSING')
                state.update(state='accepted',command_id=command_id)
                atomic_json(state_path,state)
            except Exception:
                state['state']='uncertain';atomic_json(state_path,state);raise
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            response=bridge.request('/automation-projects/result?id='+quote(state['command_id'],safe=''))
            if response.get('state')=='failed':
                state.update(state='failed',error='PROJECT_SOURCE_UI_FAILED',ended_at=now());atomic_json(state_path,state)
                raise AutomationError('PROJECT_SOURCE_UI_FAILED')
            if response.get('state')=='complete':
                report=response.get('result') or {}
                sync=report.get('sourceSync') or {}
                if sync.get('state')!='listed' or set(sync.get('filenames',[]))!={f['filename'] for f in files}:
                    raise AutomationError('PROJECT_SOURCE_RECEIPT_MISMATCH')
                if instructions and sync.get('instructionsSaved') is not True:
                    raise AutomationError('PROJECT_INSTRUCTIONS_NOT_SAVED')
                state.update(state='complete',ended_at=now(),ui_receipt=sync,source_retrieval_verified=False)
                atomic_json(state_path,state)
                # A list receipt proves UI handoff only. translate_project separately requires
                # the model to retrieve source-only random probes before accepting translation.
                return state
            time.sleep(poll_interval)
        raise AutomationError('PROJECT_SYNC_PENDING')


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work-dir',required=True);parser.add_argument('--with-instructions',action='store_true')
    args=parser.parse_args()
    work=within(ROOT/'workspace',ROOT/args.work_dir)
    try:
        result=synchronize([build_common(),build_work(work)],instructions=args.with_instructions)
        print(json.dumps({'status':result['state'],'command_id':result['command_id'],'sources':result['sources'],'retrieval_verified':False},ensure_ascii=False,indent=2));return 0
    except AutomationError as error:
        print(json.dumps({'status':'blocked','error':error.code}));return 1
if __name__=='__main__':raise SystemExit(main())
