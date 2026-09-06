#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parent.parent
status_path=ROOT/'data/automation-status.json'; cfg=json.loads((ROOT/'config/automation.json').read_text()); profiles=json.loads((ROOT/'config/search-profiles.json').read_text())
status=json.loads(status_path.read_text())
pending=done=waiting=ready=acquired=0
for state_path in (ROOT/'workspace').glob('*/*/*/state.json'):
    try: s=json.loads(state_path.read_text())
    except Exception: continue
    pending += max(0, int(s.get('chunks_total',0))-int(s.get('chunks_done',0)))
    done += int(s.get('chunks_done',0))
    if state_path.parent.joinpath('translation/manifest.json').exists(): ready += 1
for meta in (ROOT/'workspace').glob('*/*/*/metadata.json'):
    if meta.parent.joinpath('source_inbox/acquisition_manifest.json').exists(): acquired += 1
    if not meta.parent.joinpath('translation/manifest.json').exists(): waiting += 1
status['updated_at']=datetime.now(timezone.utc).isoformat(); status['schedule'].update({'time':cfg.get('time'),'status':'ready' if cfg.get('time') and cfg.get('enabled') else 'awaiting_user_time'})
enabled_profiles=[x for x in profiles.get('profiles',[]) if x.get('enabled')]
status['criteria'].update({'status':'ready' if profiles.get('criteria_ready') and enabled_profiles else 'awaiting_user_answers','profile_count':len(enabled_profiles)})
status['translation'].update({'pending_chunks':pending,'completed_chunks':done,'works_waiting_for_source':waiting,'works_ready':ready})
status.setdefault('source_acquisition',{}).update({'acquired_works':acquired})
status['phase']='ready_for_schedule' if cfg.get('time') and profiles.get('criteria_ready') else 'pipeline_ready_configuration_pending'
status['next_action']='enable daily schedule' if status['phase']=='ready_for_schedule' else 'collect search criteria and exact daily time'
status_path.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(status,ensure_ascii=False,indent=2))
