#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from automation_store import atomic_json, read_json

ROOT=Path(__file__).resolve().parent.parent


def _safe_workspace(root: Path, value: str) -> Path | None:
    try:
        candidate=(root/value).resolve()
        workspace=(root/'workspace').resolve()
        return candidate if candidate.is_relative_to(workspace) else None
    except (OSError, ValueError):
        return None


def sync_registry_progress(root: Path=ROOT) -> bool:
    """Project canonical workspace translation state back into the public work registry."""
    path=root/'data/work-registry.json'
    if not path.exists(): return False
    registry=read_json(path,{'works':[]}); changed=False
    for row in registry.get('works',[]):
        wdir=_safe_workspace(root,str(row.get('workspace') or ''))
        if not wdir: continue
        state=read_json(wdir/'state.json',{})
        status=state.get('status')
        if status not in {'translation_pending','translation_complete'}: continue
        projection={
            'status':status,
            'chunks_done':int(state.get('chunks_done',0)),
            'chunks_total':int(state.get('chunks_total',0)),
            'translation_updated_at':state.get('updated_at')
        }
        for key,value in projection.items():
            if row.get(key)!=value:
                row[key]=value;changed=True
    if changed:
        registry['updated_at']=datetime.now(timezone.utc).isoformat()
        atomic_json(path,registry)
    return changed


def refresh(root: Path=ROOT) -> dict:
    status_path=root/'data/automation-status.json'; cfg=read_json(root/'config/automation.json'); profiles=read_json(root/'config/search-profiles.json')
    project_cfg=read_json(root/'config/project-translation.json',{})
    status=read_json(status_path)
    fullq=read_json(root/'data/full-translation-queue.json',{'requests':[]})
    sync_registry_progress(root)
    pending=done=waiting=ready=acquired=0
    for state_path in (root/'workspace').glob('*/*/*/state.json'):
        try: s=read_json(state_path)
        except Exception: continue
        pending += max(0, int(s.get('chunks_total',0))-int(s.get('chunks_done',0)))
        done += int(s.get('chunks_done',0))
        if state_path.parent.joinpath('translation/manifest.json').exists(): ready += 1
    for meta in (root/'workspace').glob('*/*/*/metadata.json'):
        if meta.parent.joinpath('source_inbox/acquisition_manifest.json').exists(): acquired += 1
        if not meta.parent.joinpath('translation/manifest.json').exists(): waiting += 1
    status['updated_at']=datetime.now(timezone.utc).isoformat(); status['schedule'].update({'time':cfg.get('time'),'status':'ready' if cfg.get('time') and cfg.get('enabled') else 'awaiting_user_time'})
    enabled_profiles=[x for x in profiles.get('profiles',[]) if x.get('enabled')]
    status['criteria'].update({'status':'ready' if profiles.get('criteria_ready') and enabled_profiles else 'awaiting_user_answers','profile_count':len(enabled_profiles)})
    status['translation'].update({'pending_chunks':pending,'completed_chunks':done,'works_waiting_for_source':waiting,'works_ready':ready,
     'backend':{'name':project_cfg.get('backend'),'activation':project_cfg.get('activation'),'project_alias':project_cfg.get('project_alias'),
                'require_source_probe':project_cfg.get('require_source_probe') is True,'allow_fallback':project_cfg.get('allow_fallback')}})
    status['translation']['full_requests']={
     'queued':sum(1 for x in fullq.get('requests',[]) if x.get('status') in {'queued','acquiring','acquisition_error'}),
     'translating':sum(1 for x in fullq.get('requests',[]) if x.get('status')=='translation_pending'),
     'complete':sum(1 for x in fullq.get('requests',[]) if x.get('status')=='complete')}
    status.setdefault('source_acquisition',{}).update({'acquired_works':acquired})
    status['phase']='ready_for_schedule' if cfg.get('time') and profiles.get('criteria_ready') else 'pipeline_ready_configuration_pending'
    status['next_action']='enable daily schedule' if status['phase']=='ready_for_schedule' else 'collect search criteria and exact daily time'
    atomic_json(status_path,status)
    return status


if __name__=='__main__':
    print(json.dumps(refresh(),ensure_ascii=False,indent=2))
