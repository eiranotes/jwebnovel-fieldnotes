#!/usr/bin/env python3
from __future__ import annotations

import argparse, copy, hashlib, html, json, re, secrets, shutil, sys, zipfile
from automation_store import AutomationError, atomic_bytes, atomic_json, digest, locked, now, read_json
from pathlib import Path

from artifact_naming import alternating_translation_filename
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


def resolve_work_dir(args) -> Path:
    explicit = getattr(args, 'work_dir', None)
    if explicit:
        path = Path(explicit).expanduser()
        return path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    if not getattr(args, 'entry', None) or not getattr(args, 'work', None):
        raise SystemExit('Either --work-dir or both --entry and --work are required')
    return work_dir(args.entry, args.work)


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
            long_cur = ''
            for sentence in split_sentence_line(para.strip()):
                if len(sentence) > hard_max:
                    if long_cur.strip():
                        chunks.append(long_cur.strip() + '\n')
                        long_cur = ''
                    # Last-resort guard for pathological single sentences that
                    # exceed the model hard limit. Ordinary Japanese prose is
                    # split only at sentence boundaries.
                    for start in range(0, len(sentence), hard_max):
                        chunks.append(sentence[start:start+hard_max].strip() + '\n')
                    continue
                if long_cur and len(long_cur) + len(sentence) > hard_max:
                    chunks.append(long_cur.strip() + '\n')
                    long_cur = sentence
                else:
                    long_cur += sentence
            if long_cur.strip():
                chunks.append(long_cur.strip() + '\n')
            continue
        if cur and len(cur) + len(para) > target:
            chunks.append(cur.strip() + '\n')
            cur = para
        else:
            cur += para
    if cur.strip(): chunks.append(cur.strip() + '\n')
    return chunks


SENTENCE_END = set('。！？!?')
SENTENCE_CLOSERS = set('」』）】〕〉》”’\"\'')


def split_sentence_line(line: str) -> list[str]:
    line = line.strip()
    if not line:
        return []
    parts: list[str] = []
    start = 0
    i = 0
    while i < len(line):
        if line[i] in SENTENCE_END:
            j = i + 1
            while j < len(line) and line[j] in SENTENCE_CLOSERS:
                j += 1
            piece = line[start:j].strip()
            if piece:
                parts.append(piece)
            start = j
            i = j
            continue
        i += 1
    tail = line[start:].strip()
    if tail:
        parts.append(tail)
    return parts or [line]


def sentence_segments(text: str) -> list[dict]:
    segments: list[dict] = []
    paragraph = 0
    serial = 1
    for raw in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        line = raw.strip()
        if not line:
            paragraph += 1
            continue
        if line.startswith('===== SOURCE ') or line.startswith('URL:'):
            segments.append({'id': f'm{serial:06d}', 'kind': 'meta', 'paragraph': paragraph, 'ja': line})
            serial += 1
            continue
        for sentence in split_sentence_line(line):
            segments.append({'id': f's{serial:06d}', 'kind': 'sentence', 'paragraph': paragraph, 'ja': sentence})
            serial += 1
        paragraph += 1
    return segments


def validate_segment_translations(source_segments: list[dict], translations) -> list[dict]:
    required = [x for x in source_segments if x.get('kind') == 'sentence']
    if not isinstance(translations, list) or len(translations) != len(required):
        raise AutomationError('SEGMENT_COUNT_MISMATCH')
    pairs = []
    seen = set()
    for source, row in zip(required, translations):
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not isinstance(row.get('ko'), str):
            raise AutomationError('INVALID_SEGMENT_ROW')
        sid, ko = row['id'], row['ko'].strip()
        if sid in seen or sid != source['id'] or not ko:
            raise AutomationError('SEGMENT_ID_ORDER_OR_EMPTY')
        seen.add(sid)
        pairs.append({'id': sid, 'paragraph': source['paragraph'], 'ja': source['ja'], 'ko': ko})
    return pairs


def korean_text_from_pairs(pairs: list[dict]) -> str:
    paragraphs: list[str] = []
    current_para = None
    current: list[str] = []
    for row in pairs:
        para = row.get('paragraph')
        if current_para is None:
            current_para = para
        if para != current_para:
            if current:
                paragraphs.append(' '.join(current).strip())
            current = []
            current_para = para
        current.append(str(row.get('ko') or '').strip())
    if current:
        paragraphs.append(' '.join(current).strip())
    return '\n\n'.join(x for x in paragraphs if x).strip()


def alternating_text_from_pairs(pairs: list[dict]) -> str:
    rows = []
    last_para = None
    for row in pairs:
        if last_para is not None and row.get('paragraph') != last_para:
            rows.append('')
        rows.append(f"원문: {row['ja']}")
        rows.append(f"번역: {row['ko']}")
        rows.append('')
        last_para = row.get('paragraph')
    return '\n'.join(rows).rstrip() + '\n'


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
    wdir = resolve_work_dir(args)
    wdir.mkdir(parents=True, exist_ok=True)
    meta_path = wdir / 'metadata.json'
    if not meta_path.exists():
        meta_path.write_text(json.dumps({'entry_id': args.entry,'work_id': safe_id(args.work or wdir.name),'title': args.title or args.work or wdir.name,'platform': args.platform,'source_policy':'user_supplied_or_lawfully_acquired_only'}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    extracted = extract_inbox(wdir)
    merged, inventory = merge_sources(wdir)
    manifest = init_translation(wdir, merged, args.target, args.hard_max)
    chunks_done = sum(1 for c in manifest.get('chunks', []) if c.get('status') == 'done')
    state = {'status':'translation_complete' if chunks_done == manifest['chunk_count'] else 'translation_pending','source_files':len(inventory['files']),'merged_chars':inventory['merged_chars'],'chunks_total':manifest['chunk_count'],'chunks_done':chunks_done,'updated_at':datetime.now(timezone.utc).isoformat()}
    (wdir/'state.json').write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'work_dir':str(wdir),'extracted':len(extracted),'merged':str(merged),'chunks':manifest['chunk_count']}, ensure_ascii=False, indent=2))


def next_task(args):
    wdir = resolve_work_dir(args)
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
    metadata_path = wdir / 'metadata.json'
    metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else {}
    segments = sentence_segments(ja)
    chunk_hash = sha256_bytes(ja.encode('utf-8'))
    outdir = wdir/'translation/tasks'; outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir/f'{cid}.json'
    # This value is deliberately absent from the chat payload. A worker can return it only after
    # reading this private local task, which lets the driver distinguish a real local read from a
    # model merely claiming that it used Core. Keep it stable while the canonical chunk is stable
    # so retries/resume retain one operation identity.
    local_source_probe = ''
    if outfile.exists():
        try:
            previous = json.loads(outfile.read_text(encoding='utf-8'))
            candidate = previous.get('local_source_probe','')
            if previous.get('chunk_sha256') == chunk_hash and isinstance(candidate,str) and re.fullmatch(r'[a-f0-9]{32}',candidate):
                local_source_probe = candidate
        except Exception:
            pass
    if not local_source_probe:
        local_source_probe = secrets.token_hex(16)
    task = {
        'status':'pending','entry_id':args.entry or metadata.get('entry_id'),'work_id':safe_id(args.work or metadata.get('work_id') or wdir.name),'work_dir':str(wdir.relative_to(ROOT)) if wdir.is_relative_to(ROOT) else str(wdir),'chunk_id':cid,
        'source_sha256':manifest.get('source_sha256'),'chunk_sha256':chunk_hash,'local_source_probe':local_source_probe,
        'source_ja':ja,'source_segments':segments,'previous_source_tail':prev_tail,'next_source_head':next_head,
        'metadata':metadata,'glossary':glossary,
        'instructions':[
            'Translate every source_segments item whose kind is sentence from Japanese to natural Korean without omissions.',
            'Return exactly one segment_translations item for every sentence id, preserving the same ids and order. Do not merge, split, skip, or invent ids.',
            'Meta segments such as SOURCE boundaries and URL lines are context only and must not appear in segment_translations.',
            'For person/place/proper names, consult glossary first; if absent, infer from metadata and ruby/furigana in the source before choosing Korean spelling.',
            'Do not translate a proper name differently across chunks. Add new uncertain/name decisions to glossary_update.',
            'The sentence mapping is used to build an alternating original/translation TXT, so one-to-one alignment is mandatory.',
            'Do not summarize.'
        ],
        'output_contract':{'local_source_proof':'copy local_source_probe from this local task','segment_translations':[{'id':'s000001','ko':'string'}],'glossary_update':{'people':{},'places':{},'terms':{},'ruby_notes':{},'decisions':[]}}
    }
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


def validate_glossary_update(base: dict, update) -> dict:
    if not isinstance(update, dict):
        raise AutomationError('INVALID_GLOSSARY_UPDATE')
    for bucket in ('people', 'places', 'terms', 'ruby_notes'):
        values = update.get(bucket, {})
        if not isinstance(values, dict):
            raise AutomationError('INVALID_GLOSSARY_BUCKET')
        for key, value in values.items():
            if not isinstance(key, str) or not key or not isinstance(value, (str, dict)):
                raise AutomationError('INVALID_GLOSSARY_ENTRY')
            if key in base.get(bucket, {}) and base[bucket][key] != value:
                raise AutomationError('GLOSSARY_CONFLICT', f'{bucket}:{key}')
    if not isinstance(update.get('decisions', []), list):
        raise AutomationError('INVALID_GLOSSARY_DECISIONS')
    return deep_merge_glossary(copy.deepcopy(base), update)


def complete_chunk(wdir: Path, cid: str, result: dict) -> dict:
    if not re.fullmatch(r'[0-9]{4,8}', cid) or not isinstance(result, dict):
        raise AutomationError('INVALID_COMPLETION')
    with locked(wdir / 'translation' / '.complete.lock'):
        cdir = wdir / 'translation/chunks' / cid
        manifest_path = wdir / 'translation/manifest.json'
        manifest = read_json(manifest_path)
        chunk = next((c for c in manifest['chunks'] if c['chunk_id'] == cid), None)
        if chunk is None:
            raise AutomationError('UNKNOWN_CHUNK')
        ja = (cdir / 'ja.txt').read_text(encoding='utf-8')
        source_hash = digest(ja.encode('utf-8'))
        if result.get('chunk_id', cid) != cid or result.get('chunk_sha256', source_hash) != source_hash:
            raise AutomationError('SOURCE_CHANGED')
        metadata = read_json(wdir / 'metadata.json', {})
        if 'work_id' in result and result['work_id'] != metadata.get('work_id'):
            raise AutomationError('WORK_ID_MISMATCH')
        pairs = validate_segment_translations(sentence_segments(ja), result.get('segment_translations'))
        ko = korean_text_from_pairs(pairs)
        if not ko:
            raise AutomationError('EMPTY_TRANSLATION')
        result_hash = digest(result)
        journal_path = wdir / 'translation/commits' / f'{cid}.json'
        journal = read_json(journal_path, {})
        for other in journal_path.parent.glob('*.json'):
            if other != journal_path and read_json(other).get('state') != 'committed':
                raise AutomationError('PENDING_COMMIT_REQUIRES_RECOVERY', other.stem)
        if journal:
            if journal.get('result_hash') != result_hash or journal.get('source_hash') != source_hash:
                raise AutomationError('COMPLETION_CONFLICT')
            if journal.get('state') == 'committed':
                done = sum(c.get('status') == 'done' for c in manifest['chunks'])
                return {'chunk':cid,'done':done,'total':manifest['chunk_count'],'repeated':True}
        elif chunk.get('status') == 'done':
            previous = read_json(cdir / 'pairs.json', {}).get('pairs')
            if previous != pairs:
                raise AutomationError('ALREADY_COMPLETED_DIFFERENT_RESULT')
            done = sum(c.get('status') == 'done' for c in manifest['chunks'])
            return {'chunk':cid,'done':done,'total':manifest['chunk_count'],'repeated':True}
        else:
            glossary = read_json(wdir / 'glossary.json')
            updated = validate_glossary_update(glossary, result.get('glossary_update') or {})
            meta = read_json(cdir / 'meta.json')
            meta.update(status='done',ko_chars=len(ko),translated_at=now(),review_status='auto_pending')
            journal = {'version':1,'state':'prepared','result_hash':result_hash,'source_hash':source_hash,
                       'result':result,'pairs':pairs,'ko':ko,'meta':meta,
                       'previous_glossary_hash':digest(glossary),'glossary':updated}
            atomic_json(journal_path,journal)
        # Resume an interrupted commit without duplicating glossary decisions. Other chunks
        # cannot commit while this intent is pending, and independent edits are not overwritten.
        current_glossary = read_json(wdir / 'glossary.json')
        if digest(current_glossary) not in (journal['previous_glossary_hash'], digest(journal['glossary'])):
            raise AutomationError('GLOSSARY_CHANGED_DURING_COMMIT')
        atomic_bytes(cdir / 'ko.txt',(journal['ko']+'\n').encode('utf-8'))
        atomic_json(cdir / 'pairs.json',{'schema_version':'1.0','chunk_id':cid,'pairs':journal['pairs']})
        atomic_bytes(cdir / 'pairs.txt',alternating_text_from_pairs(journal['pairs']).encode('utf-8'))
        atomic_json(cdir / 'meta.json',journal['meta'])
        atomic_json(wdir / 'glossary.json',journal['glossary'])
        chunk.update(journal['meta'])
        atomic_json(manifest_path,manifest)
        done = sum(c.get('status') == 'done' for c in manifest['chunks'])
        state = read_json(wdir / 'state.json',{})
        state.update(chunks_done=done,status='translation_complete' if done == manifest['chunk_count'] else 'translation_pending',updated_at=now())
        atomic_json(wdir / 'state.json',state)
        journal.update(state='committed',committed_at=now())
        atomic_json(journal_path,journal)
        return {'chunk':cid,'done':done,'total':manifest['chunk_count']}


def complete(args):
    result = read_json(Path(args.result))
    print(json.dumps(complete_chunk(resolve_work_dir(args), args.chunk, result), ensure_ascii=False))


def build_parallel(args):
    wdir=resolve_work_dir(args); manifest=json.loads((wdir/'translation/manifest.json').read_text(encoding='utf-8'))
    rows=[]
    for c in manifest['chunks']:
        cdir=wdir/'translation/chunks'/c['chunk_id']; ja=(cdir/'ja.txt').read_text(encoding='utf-8')
        ko=(cdir/'ko.txt').read_text(encoding='utf-8') if (cdir/'ko.txt').exists() else '[번역 대기]'
        rows.append(f'<section><header>{c["chunk_id"]}</header><div class="ja"><h2>原文</h2><pre>{html.escape(ja)}</pre></div><div class="ko"><h2>번역</h2><pre>{html.escape(ko)}</pre></div></section>')
    doc='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Private parallel translation</title><style>body{margin:0;font:15px/1.7 system-ui;background:#eee;color:#171717}main{max-width:1400px;margin:auto;padding:32px}section{display:grid;grid-template-columns:70px 1fr 1fr;border-top:1px solid #777}header{padding:16px 8px;font:12px monospace}.ja,.ko{padding:16px;border-left:1px solid #aaa}h2{font:12px monospace;margin:0 0 12px;color:#666}pre{white-space:pre-wrap;font:inherit;margin:0}@media(max-width:800px){section{grid-template-columns:40px 1fr}.ko{grid-column:2}.ja,.ko{border-bottom:1px solid #aaa}}</style><main>'''+''.join(rows)+'</main></html>'
    out=wdir/'translation/parallel'; out.mkdir(parents=True, exist_ok=True); path=out/'index.html'; path.write_text(doc, encoding='utf-8'); print(path)


def build_output(args):
    wdir = resolve_work_dir(args)
    manifest = json.loads((wdir/'translation/manifest.json').read_text(encoding='utf-8'))
    ko_parts, bilingual, alternating_parts = [], [], []
    for c in manifest.get('chunks', []):
        cdir = wdir/'translation/chunks'/c['chunk_id']
        ja_path, ko_path, pairs_path = cdir/'ja.txt', cdir/'ko.txt', cdir/'pairs.json'
        if not ko_path.exists():
            print(json.dumps({'status':'translation_pending','missing_chunk':c['chunk_id']}, ensure_ascii=False))
            return
        if not pairs_path.exists():
            print(json.dumps({'status':'sentence_alignment_missing','missing_chunk':c['chunk_id']}, ensure_ascii=False))
            return
        ja = ja_path.read_text(encoding='utf-8').rstrip()
        ko = ko_path.read_text(encoding='utf-8').rstrip()
        pairs = json.loads(pairs_path.read_text(encoding='utf-8')).get('pairs') or []
        ko_parts.append(ko)
        bilingual.append(f"## Chunk {c['chunk_id']}\n\n### 원문\n\n{ja}\n\n### 번역\n\n{ko}")
        alternating_parts.append(alternating_text_from_pairs(pairs).rstrip())
    out = wdir/'translation/output'
    out.mkdir(parents=True, exist_ok=True)
    metadata_path = wdir/'metadata.json'
    metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else {}
    work_id = safe_id(getattr(args, 'work', None) or metadata.get('work_id') or wdir.name)
    title = str(metadata.get('title') or work_id)
    ko_file = out/'ko.txt'
    bi_file = out/'ja-ko.md'
    alt_file = out/alternating_translation_filename(title)
    ko_file.write_text('\n\n'.join(ko_parts).rstrip()+'\n', encoding='utf-8')
    bi_file.write_text('\n\n---\n\n'.join(bilingual).rstrip()+'\n', encoding='utf-8')
    alt_file.write_text('\n\n'.join(alternating_parts).rstrip()+'\n', encoding='utf-8')
    zip_file = out/f'{work_id}-translation.zip'
    with zipfile.ZipFile(zip_file, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(ko_file, 'ko.txt')
        zf.write(bi_file, 'ja-ko.md')
        zf.write(alt_file, alt_file.name)
        glossary = wdir/'glossary.json'
        if glossary.exists(): zf.write(glossary, 'glossary.json')
    artifacts = [ko_file, bi_file, alt_file, zip_file]
    print(json.dumps({'status':'complete','artifacts':[str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p) for p in artifacts]}, ensure_ascii=False, indent=2))


def main():
    p=argparse.ArgumentParser(); sp=p.add_subparsers(dest='cmd', required=True)
    q=sp.add_parser('prepare'); q.add_argument('--entry'); q.add_argument('--work'); q.add_argument('--work-dir'); q.add_argument('--title'); q.add_argument('--platform'); q.add_argument('--target',type=int,default=9000); q.add_argument('--hard-max',type=int,default=12000); q.set_defaults(fn=prepare)
    q=sp.add_parser('next-task'); q.add_argument('--entry'); q.add_argument('--work'); q.add_argument('--work-dir'); q.add_argument('--context-tail',type=int,default=700); q.add_argument('--context-head',type=int,default=500); q.set_defaults(fn=next_task)
    q=sp.add_parser('complete'); q.add_argument('--entry'); q.add_argument('--work'); q.add_argument('--work-dir'); q.add_argument('--chunk',required=True); q.add_argument('--result',required=True); q.set_defaults(fn=complete)
    q=sp.add_parser('build-parallel'); q.add_argument('--entry'); q.add_argument('--work'); q.add_argument('--work-dir'); q.set_defaults(fn=build_parallel)
    q=sp.add_parser('build-output'); q.add_argument('--entry'); q.add_argument('--work'); q.add_argument('--work-dir'); q.set_defaults(fn=build_output)
    args=p.parse_args(); args.fn(args)
if __name__=='__main__': main()
