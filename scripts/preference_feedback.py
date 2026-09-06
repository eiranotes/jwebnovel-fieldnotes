#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDBACK = ROOT / 'workspace' / 'preference-feedback.json'
MODEL = ROOT / 'workspace' / 'preference-model.json'
PROFILES = ROOT / 'config' / 'search-profiles.json'
SCORES = {'love': 3, 'like': 1, 'neutral': 0, 'dislike': -1, 'exclude': -3}
ALLOWED_REASONS = {
    'premise','tone','prose','pacing','protagonist','characters','relationships','romance',
    'worldbuilding','system_rules','strategy','comedy','darkness','slice_of_life','length',
    'freshness','ending','genre_mix','other'
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path, fallback: dict) -> dict:
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else fallback


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def record(*, canonical_key: str, verdict: str, reasons: list[str], tags: list[str] | None = None, note: str = '', profile_id: str | None = None, source: str = 'manual', external_id: str | None = None) -> dict:
    if verdict not in SCORES:
        raise ValueError(f'unsupported verdict: {verdict}')
    reasons = [x for x in dict.fromkeys(reasons) if x in ALLOWED_REASONS]
    tags = [str(x).strip()[:80] for x in dict.fromkeys(tags or []) if str(x).strip()]
    data = load(FEEDBACK, {'schema_version':'1.0','updated_at':None,'events':[]})
    event = {
        'timestamp': now(), 'canonical_key': canonical_key, 'profile_id': profile_id,
        'verdict': verdict, 'score': SCORES[verdict], 'reasons': reasons, 'tags': tags,
        'note': note.strip(), 'source': source, 'external_id': external_id,
    }
    events = data.setdefault('events', [])
    if external_id:
        events[:] = [x for x in events if x.get('external_id') != external_id]
    events.append(event)
    data['updated_at'] = event['timestamp']
    save(FEEDBACK, data)
    rebuild()
    return event


def rebuild() -> dict:
    feedback = load(FEEDBACK, {'events':[]})
    profiles = load(PROFILES, {'profiles':[]})
    profile_ids = [p.get('profile_id') for p in profiles.get('profiles', []) if p.get('profile_id')]
    profile_map = {p.get('profile_id'): p for p in profiles.get('profiles', []) if p.get('profile_id')}
    buckets: dict[str, list[dict]] = defaultdict(list)
    for event in feedback.get('events', []):
        pid = event.get('profile_id') or '__global__'
        buckets[pid].append(event)

    models = {}
    global_events = buckets.get('__global__', [])
    for pid in ['__global__', *profile_ids]:
        events = global_events if pid == '__global__' else global_events + buckets.get(pid, [])
        reason_score = defaultdict(float)
        reason_count = defaultdict(int)
        verdict_counts = defaultdict(int)
        for e in events:
            score = float(e.get('score', 0))
            verdict_counts[str(e.get('verdict'))] += 1
            for reason in e.get('reasons') or []:
                signal = f'aspect:{reason}'
                reason_score[signal] += score
                reason_count[signal] += 1
            for tag in e.get('tags') or []:
                signal = f'tag:{tag}'
                reason_score[signal] += score
                reason_count[signal] += 1
        signals = []
        suggestions = []
        for reason in sorted(reason_count):
            count = reason_count[reason]
            total = reason_score[reason]
            avg = total / count if count else 0
            confidence = min(1.0, count / 5.0)
            signals.append({'reason':reason,'count':count,'score':round(total,2),'average':round(avg,2),'confidence':round(confidence,2)})
            if count >= 2 and abs(avg) >= 1.0:
                direction = 'prefer' if avg > 0 else 'avoid'
                learned = (profile_map.get(pid) or {}).get('learned_preferences') or {}
                already_applied = reason in (learned.get(direction) or [])
                if pid != '__global__' and not already_applied:
                    suggestions.append({
                        'suggestion_id': f'{pid}:{reason}:{direction}', 'reason': reason, 'direction': direction,
                        'evidence_count': count, 'average_score': round(avg,2), 'confidence': round(confidence,2),
                        'target': 'soft_preference',
                        'status': 'proposed',
                    })
        work_scores = defaultdict(float)
        for e in events:
            work_scores[str(e.get('canonical_key'))] += float(e.get('score', 0))
        models[pid] = {
            'event_count': len(events), 'verdict_counts': dict(verdict_counts),
            'positive_examples': [k for k,v in sorted(work_scores.items(), key=lambda kv:-kv[1]) if v > 0][:20],
            'negative_examples': [k for k,v in sorted(work_scores.items(), key=lambda kv:kv[1]) if v < 0][:20],
            'signals': sorted(signals, key=lambda x: (-abs(x['score']), x['reason'])),
            'suggestions': sorted(suggestions, key=lambda x: (-x['confidence'], -abs(x['average_score']), x['reason'])),
        }
    model = {'schema_version':'1.0','updated_at':now(),'policy':{
        'hard_filters_auto_mutate':False,
        'learned_signals_use':'secondary_ranking_after_hard_filters',
        'suggestions_require_user_approval':True,
        'implicit_full_translation_signal':'love',
    },'profiles':models}
    save(MODEL, model)
    return model


def apply_suggestion(profile_id: str, reason: str, direction: str) -> dict:
    if direction not in {'prefer','avoid'}:
        raise ValueError('direction must be prefer or avoid')
    data = load(PROFILES, {})
    profile = next((p for p in data.get('profiles', []) if p.get('profile_id') == profile_id), None)
    if not profile:
        raise ValueError(f'profile not found: {profile_id}')
    learned = profile.setdefault('learned_preferences', {'prefer':[], 'avoid':[], 'updated_at':None})
    target = learned.setdefault(direction, [])
    if reason not in target:
        target.append(reason)
    opposite = 'avoid' if direction == 'prefer' else 'prefer'
    learned[opposite] = [x for x in learned.setdefault(opposite, []) if x != reason]
    learned['updated_at'] = now()
    save(PROFILES, data)
    model = rebuild()
    return {'profile_id':profile_id,'learned_preferences':learned,'model':model.get('profiles',{}).get(profile_id,{})}


def main() -> int:
    p=argparse.ArgumentParser()
    sp=p.add_subparsers(dest='cmd',required=True)
    q=sp.add_parser('record'); q.add_argument('--key',required=True); q.add_argument('--verdict',required=True); q.add_argument('--reasons',default=''); q.add_argument('--tags',default=''); q.add_argument('--note',default=''); q.add_argument('--profile'); q.add_argument('--source',default='manual'); q.add_argument('--external-id')
    sp.add_parser('rebuild')
    q=sp.add_parser('apply'); q.add_argument('--profile',required=True); q.add_argument('--reason',required=True); q.add_argument('--direction',required=True)
    sp.add_parser('status')
    a=p.parse_args()
    if a.cmd=='record': result=record(canonical_key=a.key,verdict=a.verdict,reasons=[x.strip() for x in a.reasons.split(',') if x.strip()],tags=[x.strip() for x in a.tags.split(',') if x.strip()],note=a.note,profile_id=a.profile,source=a.source,external_id=a.external_id)
    elif a.cmd=='rebuild': result=rebuild()
    elif a.cmd=='apply': result=apply_suggestion(a.profile,a.reason,a.direction)
    else: result={'feedback':load(FEEDBACK,{'events':[]}), 'model':load(MODEL,{'profiles':{}})}
    print(json.dumps(result,ensure_ascii=False,indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
