#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, html, json, re, shutil, sys, zipfile
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT / 'workspace'

TEXT_SUFFIXES = {'.txt', '.md'}


def read_text_guess(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ('utf-8-sig', 'utf-8', 'cp932', 'shift_jis'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode('utf-8', errors='replace')


def normalize_text(text: str) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text.strip() + '\n'


def safe_id(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r'[^0-9a-zA-Z\u3040-\u30ff\u3400-\u9fff_-]+', '-', value)
    return value.strip('-')[:80] or 'work'


def work_dir(entry_id: str, work_id: str) -> Path:
    date = entry_id[:10]
    return WORKSPACE / date / entry_id / safe_id(work_id)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_inbox(wdir: Path) -> list[Path]:
    inbox = wdir / 'source_inbox'
    source = wdir / 'source'
    source.mkdir(parents=True, exist_ok=True)
    if not inbox.exists():
        return []
    copied = []
    for item in sorted(inbox.iterdir()):
        if item.is_dir():
            continue
        if item.suffix.lower() == '.zip':
            with zipfile.ZipFile(item) as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    name = Path(member.filename).name
                    if Path(name).suffix.lower() not in TEXT_SUFFIXES:
                        continue
                    out = source / name
                    out.write_bytes(zf.read(member))
                    copied.append(out)
        elif item.suffix.lower() in TEXT_SUFFIXES:
            out = source / item.name
            shutil.copy2(item, out)
            copied.append(out)
    return sorted(set(copied))


def order_key(path: Path):
    nums = re.findall(r'\d+', path.stem)
    return (int(nums[0]) if nums else 10**9, path.name)


def merge_sources(wdir: Path) -> tuple[Path, dict]:
    files = sorted([p for p in (wdir / 'source').glob('*') if p.suffix.lower() in TEXT_SUFFIXES], key=order_key)
    if not files:
        raise SystemExit('No source text files found. Put lawful/user-supplied TXT/ZIP files in source_inbox first.')
    parts, inventory = [], []
    for i, path in enumerate(files, 1):
        text = normalize_text(read_text_guess(path))
        parts.append(f'\n\n===== SOURCE {i:04d} · {path.name} =====\n\n{text}')
        inventory.append({'order': i, 'file': path.name, 'chars': len(text), 'sha256': sha256_bytes(path.read_bytes())})
    merged = normalize_text(''.join(parts))
    outdir = wdir / 'merged'
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / 'ja.txt'
    out.write_text(merged, encoding='utf-8')
    return out, {'files': inventory, 'merged_chars': len(merged), 'merged_sha256': sha256_bytes(merged.encode())}



def extract_ruby_notes(text: str) -> dict[str, str]:
    notes = {}
    patterns = [
        r'\|?([一-龯々〆ヵヶぁ-んァ-ヶー]{1,40})《([^》\n]{1,40})》',
        r'｜([^《\n]{1,40})《([^》\n]{1,40})》',
    ]
    for pat in patterns:
        for base, reading in re.findall(pat, text):
            base, reading = base.strip(), reading.strip()
            if not base or not reading:
                continue
            if set(reading) <= {'・', '･', '.', '·'}:
                continue
            if not re.search(r'[一-龯々〆ヵヶぁ-んァ-ヶーA-Za-z0-9]', base):
                continue
            if base not in notes:
                notes[base] = reading
    return notes


def seed_glossary_ruby(wdir: Path, text: str) -> dict:
    glossary = wdir / 'glossary.json'
    if glossary.exists():
        glossary_data = json.loads(glossary.read_text(encoding='utf-8'))
    else:
        glossary_data = {'schema_version':'1.0','people':{},'places':{},'terms':{},'ruby_notes':{},'decisions':[]}

    acquisition = wdir / 'source_inbox' / 'acquisition_manifest.json'
    source = 'merged/ja.txt'
    if acquisition.exists():
        try:
            manifest = json.loads(acquisition.read_text(encoding='utf-8'))
            ruby_notes = {
                str(k): str(v)
                for k, v in (manifest.get('ruby_notes') or {}).items()
                if k and v and not set(str(v)) <= {'・', '･', '.', '·'}
            }
            source = 'source_inbox/acquisition_manifest.json'
            glossary_data['ruby_notes'] = ruby_notes
        except Exception:
            ruby_notes = extract_ruby_notes(text)
            glossary_data.setdefault('ruby_notes', {}).update({k:v for k,v in ruby_notes.items() if k not in glossary_data.get('ruby_notes', {})})
    else:
        ruby_notes = extract_ruby_notes(text)
        glossary_data.setdefault('ruby_notes', {}).update({k:v for k,v in ruby_notes.items() if k not in glossary_data.get('ruby_notes', {})})

    decisions = [x for x in glossary_data.setdefault('decisions', []) if x.get('type') != 'ruby_scan']
    decisions.append({'type':'ruby_scan','count':len(ruby_notes),'source':source})
    glossary_data['decisions'] = decisions
    glossary.write_text(json.dumps(glossary_data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return glossary_data

def split_paragraphs(text: str, target: int, hard_max: int) -> list[str]:
    paras = re.split(r'(?<=\n)\n+', text)
    chunks, cur = [], ''
    for para in paras:
        if not para:
            continue
        if len(para) > hard_max:
            if cur.strip(): chunks.append(cur.strip() + '\n'); cur = ''
            for start in range(0, len(para), hard_max):
                chunks.append(para[start:start+hard_max].strip() + '\n')
            continue
        if cur and len(cur) + len(para) > target:
            chunks.append(cur.strip() + '\n')
            cur = para
        else:
            cur += para
    if cur.strip(): chunks.append(cur.strip() + '\n')
    return chunks


def init_translation(wdir: Path, merged: Path, target: int, hard_max: int) -> dict:
    text = merged.read_text(encoding='utf-8')
    seed_glossary_ruby(wdir, text)
    source_sha256 = sha256_bytes(text.encode('utf-8'))
    existing_manifest_path = wdir / 'translation' / 'manifest.json'
    if existing_manifest_path.exists():
        try:
            existing = json.loads(existing_manifest_path.read_text(encoding='utf-8'))
            if (
                existing.get('source_sha256') == source_sha256
                and int(existing.get('target_chunk_chars', target)) == target
                and int(existing.get('hard_max_chunk_chars', hard_max)) == hard_max
            ):
                return existing
        except Exception:
            pass
    chunks = split_paragraphs(text, target, hard_max)
    tdir = wdir / 'translation'
    croot = tdir / 'chunks'
    croot.mkdir(parents=True, exist_ok=True)
    manifest_chunks = []
    offset = 0
    for i, chunk in enumerate(chunks, 1):
        cid = f'{i:04d}'
        cdir = croot / cid
        cdir.mkdir(parents=True, exist_ok=True)
        ja = cdir / 'ja.txt'
        ja.write_text(chunk, encoding='utf-8')
        meta = {
            'chunk_id': cid, 'order': i, 'status': 'pending',
            'source_start_char': offset, 'source_end_char': offset + len(chunk),
            'ja_chars': len(chunk), 'ko_chars': 0,
            'translated_at': None, 'review_status': 'pending',
            'terms_added': []
        }
        (cdir / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        manifest_chunks.append(meta.copy())
        offset += len(chunk)
    manifest = {
        'schema_version': '1.0', 'source': str(merged.relative_to(ROOT)),
        'source_sha256': source_sha256,
        'target_chunk_chars': target, 'hard_max_chunk_chars': hard_max,
        'chunk_count': len(chunks), 'chunks': manifest_chunks,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    (tdir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return manifest


def prepare(args):
    wdir = work_dir(args.entry, args.work)
    wdir.mkdir(parents=True, exist_ok=True)
    meta_path = wdir / 'metadata.json'
    if not meta_path.exists():
        meta_path.write_text(json.dumps({'entry_id': args.entry,'work_id': safe_id(args.work),'title': args.title or args.work,'platform': args.platform,'source_policy':'user_supplied_or_lawfully_acquired_only'}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    extracted = extract_inbox(wdir)
    merged, inventory = merge_sources(wdir)
    manifest = init_translation(wdir, merged, args.target, args.hard_max)
    chunks_done = sum(1 for c in manifest.get('chunks', []) if c.get('status') == 'done')
    state = {'status':'translation_complete' if chunks_done == manifest['chunk_count'] else 'translation_pending','source_files':len(inventory['files']),'merged_chars':inventory['merged_chars'],'chunks_total':manifest['chunk_count'],'chunks_done':chunks_done,'updated_at':datetime.now(timezone.utc).isoformat()}
    (wdir/'state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'work_dir':str(wdir),'extracted':len(extracted),'merged':str(merged),'chunks':manifest['chunk_count']}, ensure_ascii=False, indent=2))


def next_task(args):
    wdir = work_dir(args.entry, args.work)
    manifest = json.loads((wdir/'translation/manifest.json').read_text(encoding='utf-8'))
    chunks = manifest['chunks']
    pending = next((c for c in chunks if c.get('status') != 'done'), None)
    if not pending:
        print(json.dumps({'status':'complete'}, ensure_ascii=False)); return
    idx = pending['order'] - 1
    cid = pending['chunk_id']
    cdir = wdir/'translation/chunks'/cid
    ja = (cdir/'ja.txt').read_text(encoding='utf-8')
    glossary = json.loads((wdir/'glossary.json').read_text(encoding='utf-8'))
    prev_tail = ''
    next_head = ''
    if idx > 0:
        p = wdir/'translation/chunks'/chunks[idx-1]['chunk_id']/'ja.txt'
        prev_tail = p.read_text(encoding='utf-8')[-args.context_tail:]
    if idx+1 < len(chunks):
        p = wdir/'translation/chunks'/chunks[idx+1]['chunk_id']/'ja.txt'
        next_head = p.read_text(encoding='utf-8')[:args.context_head]
    task = {
        'status':'pending','entry_id':args.entry,'work_id':safe_id(args.work),'chunk_id':cid,
        'source_ja':ja,'previous_source_tail':prev_tail,'next_source_head':next_head,
        'glossary':glossary,
        'instructions':[
            'Translate the full source_ja from Japanese to natural Korean without omissions.',
            'Preserve paragraph boundaries unless Korean readability clearly requires a split.',
            'For person/place/proper names, consult glossary first; if absent, infer from metadata and ruby/furigana in the source before choosing Korean spelling.',
            'Do not translate a proper name differently across chunks. Add new uncertain/name decisions to glossary_update.',
            'Preserve ===== SOURCE ... ===== boundary markers unchanged; translate only the novel text around them.',
            'Return Korean translation only in ko_text plus structured glossary_update; do not summarize.'
        ],
        'output_contract':{'ko_text':'string','glossary_update':{'people':{},'places':{},'terms':{},'ruby_notes':{},'decisions':[]}}
    }
    outdir = wdir/'translation/tasks'; outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir/f'{cid}.json'; outfile.write_text(json.dumps(task, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(str(outfile))


def deep_merge_glossary(base: dict, update: dict):
    for bucket in ('people','places','terms','ruby_notes'):
        base.setdefault(bucket,{})
        for k,v in (update.get(bucket) or {}).items():
            if k in base[bucket] and base[bucket][k] != v:
                base.setdefault('decisions',[]).append({'type':'conflict','key':k,'kept':base[bucket][k],'proposed':v})
            else:
                base[bucket][k]=v
    base.setdefault('decisions',[]).extend(update.get('decisions') or [])
    return base


def complete(args):
    wdir = work_dir(args.entry, args.work)
    result = json.loads(Path(args.result).read_text(encoding='utf-8'))
    cid = args.chunk
    cdir = wdir/'translation/chunks'/cid
    ko = result.get('ko_text','').strip()
    if not ko: raise SystemExit('ko_text is empty')
    (cdir/'ko.txt').write_text(ko+'\n', encoding='utf-8')
    meta = json.loads((cdir/'meta.json').read_text(encoding='utf-8'))
    meta.update({'status':'done','ko_chars':len(ko),'translated_at':datetime.now(timezone.utc).isoformat(),'review_status':'auto_pending'})
    (cdir/'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    glossary_path = wdir/'glossary.json'; glossary = json.loads(glossary_path.read_text(encoding='utf-8'))
    glossary = deep_merge_glossary(glossary, result.get('glossary_update') or {})
    glossary_path.write_text(json.dumps(glossary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    mpath = wdir/'translation/manifest.json'; manifest=json.loads(mpath.read_text(encoding='utf-8'))
    for c in manifest['chunks']:
        if c['chunk_id']==cid: c.update(meta)
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    done=sum(1 for c in manifest['chunks'] if c.get('status')=='done')
    state_path=wdir/'state.json'; state=json.loads(state_path.read_text(encoding='utf-8'))
    state.update({'chunks_done':done,'status':'translation_complete' if done==manifest['chunk_count'] else 'translation_pending','updated_at':datetime.now(timezone.utc).isoformat()})
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'chunk':cid,'done':done,'total':manifest['chunk_count']}, ensure_ascii=False))


def build_parallel(args):
    wdir=work_dir(args.entry,args.work); manifest=json.loads((wdir/'translation/manifest.json').read_text(encoding='utf-8'))
    rows=[]
    for c in manifest['chunks']:
        cdir=wdir/'translation/chunks'/c['chunk_id']; ja=(cdir/'ja.txt').read_text(encoding='utf-8')
        ko=(cdir/'ko.txt').read_text(encoding='utf-8') if (cdir/'ko.txt').exists() else '[번역 대기]'
        rows.append(f'<section><header>{c["chunk_id"]}</header><div class="ja"><h2>原文</h2><pre>{html.escape(ja)}</pre></div><div class="ko"><h2>번역</h2><pre>{html.escape(ko)}</pre></div></section>')
    doc='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Private parallel translation</title><style>body{margin:0;font:15px/1.7 system-ui;background:#eee;color:#171717}main{max-width:1400px;margin:auto;padding:32px}section{display:grid;grid-template-columns:70px 1fr 1fr;border-top:1px solid #777}header{padding:16px 8px;font:12px monospace}.ja,.ko{padding:16px;border-left:1px solid #aaa}h2{font:12px monospace;margin:0 0 12px;color:#666}pre{white-space:pre-wrap;font:inherit;margin:0}@media(max-width:800px){section{grid-template-columns:40px 1fr}.ko{grid-column:2}.ja,.ko{border-bottom:1px solid #aaa}}</style><main>'''+''.join(rows)+'</main></html>'
    out=wdir/'translation/parallel'; out.mkdir(parents=True, exist_ok=True); path=out/'index.html'; path.write_text(doc, encoding='utf-8'); print(path)


def main():
    p=argparse.ArgumentParser(); sp=p.add_subparsers(dest='cmd', required=True)
    q=sp.add_parser('prepare'); q.add_argument('--entry',required=True); q.add_argument('--work',required=True); q.add_argument('--title'); q.add_argument('--platform'); q.add_argument('--target',type=int,default=9000); q.add_argument('--hard-max',type=int,default=12000); q.set_defaults(fn=prepare)
    q=sp.add_parser('next-task'); q.add_argument('--entry',required=True); q.add_argument('--work',required=True); q.add_argument('--context-tail',type=int,default=700); q.add_argument('--context-head',type=int,default=500); q.set_defaults(fn=next_task)
    q=sp.add_parser('complete'); q.add_argument('--entry',required=True); q.add_argument('--work',required=True); q.add_argument('--chunk',required=True); q.add_argument('--result',required=True); q.set_defaults(fn=complete)
    q=sp.add_parser('build-parallel'); q.add_argument('--entry',required=True); q.add_argument('--work',required=True); q.set_defaults(fn=build_parallel)
    args=p.parse_args(); args.fn(args)
if __name__=='__main__': main()
