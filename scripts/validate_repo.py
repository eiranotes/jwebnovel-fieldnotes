#!/usr/bin/env python3
from pathlib import Path
import json
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parent.parent
for p in ROOT.rglob('*.json'):
    if '/.git/' in str(p) or '/workspace/' in str(p): continue
    json.loads(p.read_text(encoding='utf-8'))
class P(HTMLParser): pass
for p in [ROOT/'index.html', *sorted((ROOT/'entries').glob('*.html'))]: P().feed(p.read_text(encoding='utf-8'))
print('ok')
