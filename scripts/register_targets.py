#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, re
from pathlib import Path
from datetime import datetime, timezone
from learning_store import safe_observe

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / 'data' / 'work-registry.json'


def safe_id(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r'[^0-9a-zA-Z\u3040-\u30ff\u3400-\u9fff_-]+', '-', value)
    return value.strip('-')[:80] or 'work'


def id_from_candidate(candidate: dict) -> str:
    url = candidate.get('url') or ''
    m = re.search(r'ncode\.syosetu\.com/([^/]+)/?', url)
    if m:
        return f'narou-{m.group(1).lower()}'
    m = re.search(r'kakuyomu\.jp/works/([^/?#]+)', url)
    if m:
        return f'kakuyomu-{m.group(1)}'
    return safe_id(f"{candidate.get('platform','work')}-{candidate.get('title','untitled')}")


def load_registry() -> dict:
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text(encoding='utf-8'))
    return {'schema_version':'1.0','updated_at':None,'works':[]}


def canonical_key(item: dict) -> str:
    return f"{item.get('title','').strip().lower()}|{item.get('author','').strip().lower()}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--entry', required=True)
    p.add_argument('--top-n', type=int, default=5)
    args = p.parse_args()

    entry_path = ROOT / 'data' / 'entries' / f'{args.entry}.json'
    entry = json.loads(entry_path.read_text(encoding='utf-8'))
    date = entry.get('date') or args.entry[:10]
    results = entry.get('results') or {}
    pool = list(results.get('shortlist') or []) + list(results.get('length_exceptions') or [])
    selected = pool[:args.top_n]

    registry = load_registry()
    existing = {canonical_key(x): x for x in registry.get('works', [])}
    created = []
    for candidate in selected:
        url = str(candidate.get('url') or '').strip()
        if not re.match(r'^https://', url):
            safe_observe(
                'discovery', 'candidate_missing_url_in_json', 'observed',
                scope='persistence', note=f"entry={args.entry}; title={str(candidate.get('title') or '')[:120]}", root=ROOT,
            )
            raise SystemExit(f"Selected candidate is missing canonical https URL in entry JSON: {candidate.get('title')}")
        key = canonical_key(candidate)
        if key in existing:
            existing[key]['latest_entry_id'] = args.entry
            existing[key]['latest_rank'] = candidate.get('rank')
            existing[key]['status'] = existing[key].get('status') or 'waiting_for_source'
            continue
        wid = id_from_candidate(candidate)
        rel = Path('workspace') / date / args.entry / wid
        wdir = ROOT / rel
        wdir.mkdir(parents=True, exist_ok=True)
        meta = {
            'schema_version':'1.0', 'entry_id':args.entry, 'work_id':wid,
            'rank':candidate.get('rank'), 'title':candidate.get('title'),
            'author':candidate.get('author'), 'platform':candidate.get('platform'),
            'url':candidate.get('url'), 'length_chars':candidate.get('length_chars'),
            'source_policy':'user_supplied_or_lawfully_acquired_only',
            'workspace':str(rel)
        }
        state = {
            'status':'waiting_for_source','source_files':0,'merged_chars':0,
            'chunks_total':0,'chunks_done':0,'source_inbox':str(rel/'source_inbox'),
            'updated_at':datetime.now(timezone.utc).isoformat()
        }
        (wdir/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (wdir/'state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        reg = {**meta,'status':'waiting_for_source','latest_entry_id':args.entry,'latest_rank':candidate.get('rank'),'paths':{
            'metadata':str(rel/'metadata.json'),'state':str(rel/'state.json'),'source_inbox':str(rel/'source_inbox'),
            'merged':str(rel/'merged/ja.txt'),'glossary':str(rel/'glossary.json'),
            'translation_manifest':str(rel/'translation/manifest.json'),'parallel_view':str(rel/'translation/parallel/index.html')}}
        registry.setdefault('works', []).append(reg); existing[key]=reg; created.append(reg)

    registry['updated_at']=datetime.now(timezone.utc).isoformat()
    registry['works'].sort(key=lambda x:(x.get('entry_id',''),x.get('rank',''),x.get('title','')))
    REGISTRY.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'entry':args.entry,'selected':len(selected),'created':len(created),'targets':[x.get('title') for x in selected]},ensure_ascii=False,indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
