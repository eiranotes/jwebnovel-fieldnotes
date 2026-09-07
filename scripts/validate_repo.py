#!/usr/bin/env python3
from pathlib import Path
import json
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parent.parent
for p in ROOT.rglob('*.json'):
    if '/.git/' in str(p) or '/workspace/' in str(p) or '/.tmp/' in str(p): continue
    json.loads(p.read_text(encoding='utf-8'))
for p in sorted((ROOT/'data'/'entries').glob('*.json')):
    entry=json.loads(p.read_text(encoding='utf-8'))
    results=entry.get('results') or {}
    for bucket in ('shortlist','length_exceptions'):
        for row in results.get(bucket) or []:
            if not isinstance(row,dict):
                raise SystemExit(f'{p.name}:{bucket}: actionable candidate must be an object')
            url=str(row.get('url') or '')
            if not url.startswith('https://'):
                raise SystemExit(f'{p.name}:{bucket}: missing canonical https URL for {row.get("title")}')
class P(HTMLParser): pass
for p in [ROOT/'index.html', ROOT/'console.html', *sorted((ROOT/'entries').glob('*.html'))]: P().feed(p.read_text(encoding='utf-8'))
print('ok')
