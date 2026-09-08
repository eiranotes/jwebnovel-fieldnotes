#!/usr/bin/env python3
from pathlib import Path
import json
import subprocess
from preference_contract import validate_entry
from preference_state import load
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parent.parent
for p in ROOT.rglob('*.json'):
    if '/.git/' in str(p) or '/workspace/' in str(p) or '/.tmp/' in str(p): continue
    json.loads(p.read_text(encoding='utf-8'))
for p in sorted((ROOT/'data'/'entries').glob('*.json')):
    entry=json.loads(p.read_text(encoding='utf-8'))
    results=entry.get('results') or {}
    legacy=load(ROOT/'config/preference-policy.json',{}).get('legacy_entry_ids',[])
    if entry.get('status') != 'draft' and entry.get('entry_id') not in legacy and not str(entry.get('schema_version','')).startswith('2'):
        raise SystemExit(f'{p.name}: new completed entries require schema 2 ranking evidence')
    if entry.get('status') != 'draft':
        validate_entry(entry, load(ROOT/'workspace/preference-ranking-traces.json', {}))
    for rows in results.values():
        if not isinstance(rows,list):continue
        for row in rows:
            if isinstance(row,dict) and set(row)&{'preference_features','preference_learning','atoms','score_weights','model_snapshot'}:
                raise SystemExit(f'{p.name}: private preference evidence in public entry')
    for bucket in ('shortlist','length_exceptions'):
        for row in results.get(bucket) or []:
            if not isinstance(row,dict):
                raise SystemExit(f'{p.name}:{bucket}: actionable candidate must be an object')
            url=str(row.get('url') or '')
            if not url.startswith('https://'):
                raise SystemExit(f'{p.name}:{bucket}: missing canonical https URL for {row.get("title")}')
class P(HTMLParser): pass
for p in [ROOT/'index.html', ROOT/'console.html', *sorted((ROOT/'entries').glob('*.html'))]: P().feed(p.read_text(encoding='utf-8'))
# The canonical public repository must never track private preference evidence.
if (ROOT/'.git').exists():
    tracked=subprocess.run(['git','ls-files','workspace'],cwd=ROOT,text=True,capture_output=True,check=True).stdout.splitlines()
    forbidden=[x for x in tracked if x.startswith(('workspace/preference-','workspace/daily-taste-state','workspace/.preference'))]
    if forbidden:raise SystemExit('Private preference files tracked: '+', '.join(forbidden))
print('ok')
