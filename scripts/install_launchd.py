#!/usr/bin/env python3
from __future__ import annotations
import json, os, plistlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
cfg=json.loads((ROOT/'config/automation.json').read_text())
time=cfg.get('time')
if not time:
    raise SystemExit('config/automation.json: set time as HH:MM first')
hour,minute=map(int,time.split(':'))
runner=ROOT/'scripts/daily_local_stage.sh'
plist={
 'Label':'com.eiranotes.jwebnovel-fieldnotes.daily',
 'ProgramArguments':['/bin/zsh',str(runner)],
 'WorkingDirectory':str(ROOT),
 'StartCalendarInterval':{'Hour':hour,'Minute':minute},
 'StandardOutPath':str(ROOT/'workspace/automation.out.log'),
 'StandardErrorPath':str(ROOT/'workspace/automation.err.log'),
 'RunAtLoad':False
}
out=Path.home()/'Library/LaunchAgents/com.eiranotes.jwebnovel-fieldnotes.daily.plist'; out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(plistlib.dumps(plist)); print(out)
