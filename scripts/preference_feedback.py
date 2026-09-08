#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from preference_atoms import ATOMIZER_VERSION, extract_note_atoms, analyze_note
from preference_state import load, save, state_lock, digest, code_revision, SCORING_COHORT_ID
from preference_contract import prospective_trace, PreparedTraces, trace_cohort

ROOT = Path(__file__).resolve().parent.parent
FEEDBACK = ROOT / 'workspace' / 'preference-feedback.json'
MODEL = ROOT / 'workspace' / 'preference-model.json'
PROFILES = ROOT / 'config' / 'search-profiles.json'
DAILY_TASTE = ROOT / 'workspace' / 'daily-taste-state.json'
WORK_INDEX = ROOT / 'data' / 'work-index.json'
RANKING_TRACES = ROOT / 'workspace' / 'preference-ranking-traces.json'
LEARNING_HISTORY = ROOT / 'workspace' / 'preference-learning-history.json'
SCORES = {'love': 3, 'like': 1, 'neutral': 0, 'dislike': -1, 'exclude': -3}
RATINGS = {'exclude': 1, 'dislike': 2, 'neutral': 3, 'like': 4, 'love': 5}
PAIRWISE_L2 = 0.06
QUALITY_GATE_MIN_PAIRS = 60
ALLOWED_REASONS = {
    'premise','tone','prose','pacing','protagonist','characters','relationships','romance',
    'worldbuilding','system_rules','strategy','comedy','darkness','slice_of_life','length',
    'freshness','ending','genre_mix','other'
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def review_id(key: str, profile_id: str | None, context_id: str | None, source: str = "manual") -> str:
    return ('action:' if source == 'full_translation' else 'review:') + digest(
        [context_id or 'unscoped', key, profile_id or '__global__'])[:24]


def _normalize_event(original: dict, daily_lookup: dict) -> dict:
    event = dict(original)
    event['context_id'] = _event_context(event, daily_lookup)
    event['review_id'] = review_id(str(event.get('canonical_key') or ''), event.get('profile_id'),
                                   event['context_id'], str(event.get('source') or 'manual'))
    event['event_type'] = 'action' if event.get('source') == 'full_translation' else 'review'
    event['timestamp'] = event.get('timestamp') or '1970-01-01T00:00:00+00:00'
    event['created_at'] = event.get('created_at') or event['timestamp']
    event['revision'] = int(event.get('revision') or 1)
    return event


def _journal(data: dict) -> list[dict]:
    if 'operations' in data:
        return data['operations']
    lookup = _historical_context_lookup()
    # Keep every historical revision in the source journal; latest identity is the projection.
    operations = []
    for original in sorted(data.get('events', []), key=lambda x: str(x.get('timestamp') or '')):
        event = _normalize_event(original, lookup)
        event['sequence'] = len(operations) + 1
        previous = next((x for x in reversed(operations) if x['review_id'] == event['review_id']), None)
        if previous:
            event['created_at'] = previous['created_at']
            event['revision'] = previous['revision'] + 1
        operations.append(event)
    data['operations'] = operations
    return operations


def _effective_events(operations: list[dict]) -> list[dict]:
    latest = {}
    for operation in operations:
        latest[operation['review_id']] = operation
    return [dict(x) for x in latest.values() if not x.get('deleted')]


def record(*, canonical_key: str, verdict: str, reasons: list[str], tags: list[str] | None = None,
           note: str = '', profile_id: str | None = None, source: str = 'manual',
           external_id: str | None = None, context_id: str | None = None,
           recommended_rank: str | None = None, read_chars: int | None = None) -> dict:
    if not canonical_key or verdict not in SCORES:
        raise ValueError('canonical_key and a supported verdict are required')
    context_id = str(context_id or '').strip() or None
    profile_id = str(profile_id or '').strip() or None
    ident = review_id(canonical_key, profile_id, context_id, source)
    with state_lock(FEEDBACK.parent):
        data = load(FEEDBACK, {'events': []})
        operations = _journal(data)
        previous = next((x for x in reversed(operations) if x['review_id'] == ident), None)
        payload = {
            'canonical_key': canonical_key, 'profile_id': profile_id, 'context_id': context_id,
            'verdict': verdict, 'rating': RATINGS[verdict], 'score': SCORES[verdict],
            'reasons': sorted(set(x for x in reasons if x in ALLOWED_REASONS)),
            'tags': sorted(set(str(x).strip()[:80] for x in (tags if tags is not None else (previous or {}).get('tags', [])) if str(x).strip())),
            'note': note.strip(), 'recommended_rank': recommended_rank or (previous or {}).get('recommended_rank'),
            'event_type': 'action' if source == 'full_translation' else 'review',
        }
        if previous and all(previous.get(k) == v for k, v in payload.items()) and not previous.get('deleted'):
            # Replay repairs a derived-write failure without another learning operation.
            rebuild()
            return next(x for x in load(FEEDBACK, {})['events'] if x['review_id'] == ident)
        stamp = now()
        event = {**payload, 'review_id': ident, 'external_id': external_id, 'source': source,
                 'timestamp': stamp, 'created_at': (previous or {}).get('created_at') or stamp,
                 'revision': int((previous or {}).get('revision') or 0) + 1,
                 'sequence': len(operations) + 1,
                 'read_chars': max(0, int(read_chars if read_chars is not None else (previous or {}).get('read_chars') or 0))}
        operations.append(event)
        data.update(schema_version='2.0', updated_at=stamp, events=_effective_events(operations))
        save(FEEDBACK, data)  # Commit boundary; projections are repairable by deterministic replay.
        rebuild()
        return next(x for x in load(FEEDBACK, {})['events'] if x['review_id'] == ident)


def _historical_context_lookup() -> dict[tuple[str, str], dict]:
    result: dict[tuple[str, str], dict] = {}
    for row in load(DAILY_TASTE, {'responses':[]}).get('responses', []):
        date = str(row.get('date') or '')
        key = str(row.get('canonical_key') or '')
        if date and key:
            result[(date, key)] = row
    return result


def _historical_rank_lookup() -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for work in load(WORK_INDEX, {'works':[]}).get('works', []):
        key = str(work.get('canonical_key') or '')
        if not key:
            continue
        for classification in work.get('classifications') or []:
            entry_id = str(classification.get('entry_id') or '')
            rank = str(classification.get('rank') or '')
            if entry_id and rank:
                result[(entry_id, key)] = rank
    return result


def _event_context(event: dict, daily_lookup: dict[tuple[str, str], dict]) -> str | None:
    context = str(event.get('context_id') or '').strip()
    if context:
        return context
    external_id = str(event.get('external_id') or '')
    if external_id.startswith('daily_taste:'):
        parts = external_id.split(':', 2)
        if len(parts) == 3:
            row = daily_lookup.get((parts[1], str(event.get('canonical_key') or '')))
            if row and row.get('entry_id'):
                return str(row['entry_id'])
    return None


def _rank_value(rank: str | None) -> float | None:
    value = str(rank or '').strip().upper()
    if not value:
        return None
    group = {'A':0, 'B':100, 'Q':200, 'D':300, 'X':400}.get(value[:1], 500)
    digits = ''.join(ch for ch in value if ch.isdigit())
    within = int(digits or 99)
    if '-LE' in value:
        within += 50
    return float(group + within)


def _ndcg(rows: list[dict], k: int = 5) -> float | None:
    ranked = [row for row in rows if _rank_value(row.get('recommended_rank')) is not None]
    if len(ranked) < 2:
        return None
    ranked.sort(key=lambda row: _rank_value(row.get('recommended_rank')))
    ideal = sorted(ranked, key=lambda row: int(row.get('rating') or RATINGS.get(str(row.get('verdict')), 3)), reverse=True)

    def dcg(items: list[dict]) -> float:
        total = 0.0
        for index, row in enumerate(items[:k]):
            rating = int(row.get('rating') or RATINGS.get(str(row.get('verdict')), 3))
            relevance = max(0, rating - 1)
            total += (2 ** relevance - 1) / math.log2(index + 2)
        return total

    ideal_score = dcg(ideal)
    return dcg(ranked) / ideal_score if ideal_score else None


def _pairwise(events: list[dict]) -> tuple[list[dict], dict]:
    by_context: dict[str, dict[str, dict]] = defaultdict(dict)
    for event in sorted(events, key=lambda e: str(e.get('timestamp') or '')):
        context = event.get('_context_id') or event.get('context_id')
        key = str(event.get('canonical_key') or '')
        if context and key:
            by_context[(str(context), event.get('profile_id'))][key] = event

    pairs: list[dict] = []
    compared = correct = 0
    ndcgs = []
    for (context, profile_id), rows_by_key in by_context.items():
        rows = list(rows_by_key.values())
        ndcg = _ndcg(rows)
        if ndcg is not None:
            ndcgs.append(ndcg)
        for left, right in combinations(rows, 2):
            left_rating = int(left.get('rating') or RATINGS.get(str(left.get('verdict')), 3))
            right_rating = int(right.get('rating') or RATINGS.get(str(right.get('verdict')), 3))
            if left_rating == right_rating:
                continue
            winner, loser = (left, right) if left_rating > right_rating else (right, left)
            winner_rating = max(left_rating, right_rating)
            loser_rating = min(left_rating, right_rating)
            winner_rank = _rank_value(winner.get('recommended_rank'))
            loser_rank = _rank_value(loser.get('recommended_rank'))
            order_correct = None
            if winner_rank is not None and loser_rank is not None and winner_rank != loser_rank:
                compared += 1
                order_correct = winner_rank < loser_rank
                if order_correct:
                    correct += 1
            pairs.append({
                'context_id': context, 'profile_id': profile_id,
                'winner_created_at': winner.get('created_at') or winner.get('timestamp'),
                'loser_created_at': loser.get('created_at') or loser.get('timestamp'),
                'winner': winner.get('canonical_key'),
                'loser': loser.get('canonical_key'),
                'winner_rating': winner_rating,
                'loser_rating': loser_rating,
                'rating_margin': winner_rating - loser_rating,
                'winner_rank': winner.get('recommended_rank'),
                'loser_rank': loser.get('recommended_rank'),
                'system_order_correct': order_correct,
            })
    pairs.sort(key=lambda row: (-int(row['rating_margin']), str(row['context_id']), str(row['winner'])))
    metrics = {
        'pairwise_count': len(pairs),
        'pairwise_compared_to_initial_rank': compared,
        'pairwise_accuracy': round(correct / compared, 4) if compared else None,
        'ndcg_at_5': round(sum(ndcgs) / len(ndcgs), 4) if ndcgs else None,
        'ranked_context_count': len(ndcgs),
    }
    return pairs, metrics


def _trace_feature_vector(traces: dict, context_id: str, canonical_key: str) -> dict[str, float]:
    row = (((traces.get('contexts') or {}).get(str(context_id)) or {}).get('candidates') or {}).get(str(canonical_key)) or {}
    vector: dict[str, float] = {}
    for feature in row.get('preference_features') or []:
        atom = str(feature.get('atom') or '').strip()
        if not atom:
            continue
        value = max(-1.0, min(1.0, float(feature.get('value') or 0)))
        confidence = max(0.0, min(1.0, float(feature.get('confidence') or 0)))
        vector[atom] = value * confidence
    return vector


def _pairwise_atom_model(pairs: list[dict], traces: dict | None = None) -> tuple[list[dict], int]:
    traces = traces if traces is not None else PreparedTraces(load(RANKING_TRACES, {'contexts': {}}))
    grouped = defaultdict(dict)
    feature_contexts = defaultdict(set)
    for pair in pairs:
        trace = prospective_trace(traces, pair)
        if not trace: continue
        winner = _trace_feature_vector(traces, pair['context_id'], pair['winner'])
        loser = _trace_feature_vector(traces, pair['context_id'], pair['loser'])
        # Missing measurements are unknown, not zero. Compare only shared measured dimensions.
        diff = {k:winner[k]-loser[k] for k in sorted(set(winner)&set(loser)) if abs(winner[k]-loser[k])>=.05}
        if not diff: continue
        ident = (pair['winner'], pair['loser'])
        grouped[pair['context_id']][ident] = (diff, min(1., .35+.22*pair['rating_margin']))
        for key in diff: feature_contexts[key].add(pair['context_id'])
    if not grouped: return [],0
    weights = {key:0. for key in sorted(feature_contexts)}
    # Batch mean over independent contexts: pair count cannot multiply either gradient or L2.
    for epoch in range(36):
        gradient = defaultdict(float)
        for context in sorted(grouped):
            examples=list(grouped[context].values());total=sum(w for _,w in examples)
            for diff, sample_weight in examples:
                z=max(-12,min(12,sum(weights[k]*v for k,v in diff.items())))
                error=1-1/(1+math.exp(-z))
                for key,value in diff.items():gradient[key]+=sample_weight/total*error*value/len(grouped)
        lr=.16/(1+epoch*.08)
        for key in weights:weights[key]+=lr*(gradient[key]-PAIRWISE_L2*weights[key])
    rows=[{'atom':key,'raw_weight':round(value,6),'weight':round(math.tanh(value),6),
           'evidence_contexts':len(feature_contexts[key]),'confidence':min(1,len(feature_contexts[key])/6),
           'evidence_pairs':sum(sum(key in diff for diff,_ in examples.values()) for examples in grouped.values())}
          for key,value in weights.items()]
    return rows,sum(len(x) for x in grouped.values())


def _prospective_rank_metrics(pairs: list[dict], traces: dict | None = None) -> dict:
    traces=traces if traces is not None else PreparedTraces(load(RANKING_TRACES, {'contexts':{}}))
    cohort_counts=defaultdict(int)
    contexts=defaultdict(list);by_revision=defaultdict(int);seen=set()
    for pair in pairs:
        trace=prospective_trace(traces,pair,active_cohort=False)
        ident=(pair['context_id'],pair['winner'],pair['loser'])
        if not trace or ident in seen:continue
        seen.add(ident)
        cohort=trace_cohort(trace);cohort_counts[cohort]+=1
        if cohort!=SCORING_COHORT_ID:continue
        winner=trace['candidates'][pair['winner']]['preference_learning']
        loser=trace['candidates'][pair['loser']]['preference_learning']
        values=[winner.get(k) for k in ('base_score','exploit_score')]+[loser.get(k) for k in ('base_score','exploit_score')]
        if any(not isinstance(v,(float,int)) or not math.isfinite(v) for v in values):continue
        def accuracy(key):return .5 if winner[key]==loser[key] else float(winner[key]>loser[key])
        contexts[pair['context_id']].append((accuracy('base_score'),accuracy('exploit_score')))
        by_revision[trace['model_revision']]+=1
    rows=[]
    for context in sorted(contexts,key=lambda k:(datetime.fromisoformat(traces['contexts'][k]['created_at']),k)):
        pairs_in_context=contexts[context]
        base=sum(x[0] for x in pairs_in_context)/len(pairs_in_context)
        rerank=sum(x[1] for x in pairs_in_context)/len(pairs_in_context)
        rows.append({'context_id':context,'created_at':traces['contexts'][context]['created_at'],'pairs':len(pairs_in_context),'base':base,'rerank':rerank,'delta':rerank-base})
    total=sum(row['pairs'] for row in rows);n=len(rows)
    return {'prospective_base_pair_count':total,'prospective_rerank_pair_count':total,
        'prospective_base_pair_accuracy':sum(x['base'] for x in rows)/n if n else None,
        'prospective_rerank_pair_accuracy':sum(x['rerank'] for x in rows)/n if n else None,
        'prospective_context_count':n,'prospective_contexts':rows,'model_revision_pair_counts':dict(by_revision),
        'evaluation_kind':'online_policy_frozen_predictions','tie_credit':.5,
        'scoring_cohort_id':SCORING_COHORT_ID,'cohort_pair_counts':dict(cohort_counts)}


def _quality_gate(metrics: dict) -> dict:
    rows=metrics.get('prospective_contexts') or []
    n=len(rows);pairs=sum(x['pairs'] for x in rows)
    delta=sum(x['delta'] for x in rows)/n if n else 0.
    gate={'status':'calibrating','multiplier':.5,'evidence_pairs':pairs,'independent_contexts':n,
          'accuracy_delta':delta,'reason':'insufficient_independent_contexts','lower_90':None}
    if n>=10 and delta<=-.05:
        gate.update(status='degraded' if delta<=-.1 else 'guarded',multiplier=.125 if delta<=-.1 else .25,
                    reason='prospective_context_degradation')
    elif n>=20 and pairs>=QUALITY_GATE_MIN_PAIRS:
        def lower(values):
            rng=random.Random(0)
            means=sorted(sum(rng.choices(values,k=len(values)))/len(values) for _ in range(500))
            return means[25]
        low=lower([x['delta'] for x in rows]);gate['lower_90']=low
        # Confirmation requires five further contexts after the first eligible promotion window.
        confirmed=n>=25 and sum(x['delta'] for x in rows[:-5])/len(rows[:-5])>=.05 and lower([x['delta'] for x in rows[:-5]])>0
        if delta>=.05 and low>0 and confirmed:
            gate.update(status='improving',multiplier=min(1.,.5+.05*(n-24)),reason='confirmed_context_improvement')
        else:gate.update(status='stable',reason='no_confirmed_improvement')
    return gate


def _decay(event: dict, as_of: str) -> float:
    try:
        days=max(0,(datetime.fromisoformat(as_of)-datetime.fromisoformat(event['timestamp'])).total_seconds()/86400)
        return 2**(-days/90)
    except (ValueError,KeyError,TypeError):return 1.


def _aggregate(events: list[dict], profile_ids: list[str], as_of: str, traces: dict | None = None) -> dict:
    traces=traces if traces is not None else PreparedTraces(load(RANKING_TRACES,{'contexts':{}}))
    models={}
    reviews=[x for x in events if x.get('event_type')!='action']
    for pid in ['__global__',*profile_ids]:
        scoped=[e for e in reviews if not e.get('profile_id') or e.get('profile_id')==pid] if pid!='__global__' else [e for e in reviews if not e.get('profile_id')]
        # One work is one direct evidence unit per model, regardless of rediscovery or UI.
        by_work={}
        for e in sorted(scoped,key=lambda x:x.get('sequence',0)):by_work[e['canonical_key']]=e
        independent=list(by_work.values());stats={};reason_stats=defaultdict(list)
        evidence_mass=0.;effective_contexts={};work_scores={};unresolved=[]
        for e in independent:
            analysis=analyze_note(e.get('note',''));atoms=analysis['atoms']
            unresolved.extend({'review_id':e['review_id'],**x} for x in analysis['unresolved'])
            decay=_decay(e,as_of)
            if atoms:
                evidence_mass+=decay
                context=e.get('context_id')
                if context:effective_contexts[context]=max(decay,effective_contexts.get(context,0))
            # Uniform allocation makes a long memo no stronger than one atom, including after shrinkage.
            for atom in atoms:
                key=atom['key'];support=decay/len(atoms)
                stat=stats.setdefault(key,{'atom':key,'label':atom['label'],'positive_support':0.,'negative_support':0.,
                    'positive_count':0,'negative_count':0,'works':set(),'contexts':set(),'evidence':[]})
                direction='positive' if atom['polarity']>0 else 'negative'
                stat[direction+'_support']+=support;stat[direction+'_count']+=1
                stat['works'].add(e['canonical_key'])
                if e.get('context_id'):stat['contexts'].add(e['context_id'])
                if atom['evidence'] not in stat['evidence']:stat['evidence'].append(atom['evidence'])
            explicit=[f'aspect:{x}' for x in e.get('reasons',[])]+[f'tag:{x}' for x in e.get('tags',[])]
            for reason in explicit:reason_stats[reason].append((e, float(e['score'])/max(1,len(explicit))*decay))
            work_scores[e['canonical_key']]=e['score']
        atoms=[];direct={}
        for key,st in sorted(stats.items()):
            positive,negative=st['positive_support'],st['negative_support'];support=positive+negative;signed=positive-negative
            consistency=abs(signed)/support if support else 0
            posterior=signed/(4+support)
            confidence=support/(4+support)*consistency
            count=len(st['works']);contexts=len(st['contexts'])
            stage='mixed' if positive and negative and consistency<.8 else 'stable' if count>=5 and contexts>=5 and support>=3 and consistency>=.8 else 'reinforced' if count>=2 and contexts>=2 else 'tentative'
            # A shared denominator bounds total influence independently of atom splitting.
            direct[key]=signed/(4+evidence_mass)
            atoms.append({k:v for k,v in st.items() if k not in {'works','contexts'}} | {
                'count':count,'evidence_contexts':contexts,'support':support,'score':signed,'consistency':consistency,
                'posterior_weight':posterior,'effective_weight':direct[key],'confidence':confidence,'stage':stage})
        pairs,rank_metrics=_pairwise(scoped)
        pair_weights,examples=_pairwise_atom_model(pairs,traces)
        prospective=_prospective_rank_metrics(pairs,traces);gate=_quality_gate(prospective)
        pair_mass=sum(abs(x['weight']*x['confidence']) for x in pair_weights)
        combined=dict(direct)
        for pair in pair_weights:
            combined[pair['atom']]=combined.get(pair['atom'],0)+.3*pair['weight']*pair['confidence']/max(1,pair_mass)
        mass=sum(abs(x) for x in combined.values())
        n=max(sum(effective_contexts.values()),float(prospective['prospective_context_count']))
        maturity=1-math.exp(-n/12)
        target={k:4*gate['multiplier']*maturity*v/max(1,mass) for k,v in combined.items()}
        ratings=[x['rating'] for x in scoped];signals=[];suggestions=[]
        for reason,values in sorted(reason_stats.items()):
            score=sum(v for _,v in values);contexts={e.get('context_id') for e,_ in values if e.get('context_id')}
            row={'reason':reason,'kind':reason.split(':')[0],'count':len(values),'score':score,'average':score/len(values),'confidence':min(1,len(contexts)/5)}
            signals.append(row)
            if pid!='__global__' and len(contexts)>=5 and abs(row['average'])>=1:
                direction='prefer' if score>0 else 'avoid'
                suggestions.append({'suggestion_id':f'{pid}:{reason}:{direction}','reason':reason,'direction':direction,
                    'evidence_count':len(values),'average_score':row['average'],'confidence':row['confidence'],'status':'proposed','target':'soft_preference'})
        metrics={'rating_count':len(ratings),'mean_rating':sum(ratings)/len(ratings) if ratings else None,
            'high_rating_rate':sum(x>=4 for x in ratings)/len(ratings) if ratings else None,
            'low_rating_rate':sum(x<=2 for x in ratings)/len(ratings) if ratings else None,
            'raw_model_maturity':maturity,'model_maturity':maturity*gate['multiplier'],
            'learned_preference_share':.28*maturity*gate['multiplier'],'effective_context_count':n,
            'pairwise_feature_examples':examples,'unresolved_clause_count':len(unresolved),
            **{stage+'_atom_count':sum(x['stage']==stage for x in atoms) for stage in ('tentative','reinforced','stable','mixed')},
            **rank_metrics,**prospective}
        models[pid]={'event_count':len(scoped),'verdict_counts':{v:sum(e['verdict']==v for e in scoped) for v in SCORES},
            'atom_signals':atoms,'signals':signals,'pairwise_preferences':pairs,'pairwise_atom_weights':pair_weights,
            'positive_examples':[k for k,v in work_scores.items() if v>0], 'negative_examples':[k for k,v in work_scores.items() if v<0],
            'suggestions':suggestions,'quality_gate':gate,'metrics':metrics,'target_score_weights':target,
            'preference_summary':{stage:[a['atom'] for a in atoms if (a['stage']==stage if stage in {'tentative','mixed'} else a['stage'] in {'reinforced','stable'} and (a['score']>0 if stage=='prefer' else a['score']<0))] for stage in ('prefer','avoid','tentative','mixed')},
            'unresolved_clauses':unresolved}
    return models


def _trace_dependencies(operations: list[dict], traces: dict) -> dict:
    contexts={e.get('context_id') for e in operations if e.get('context_id')}
    return {k:(traces.get('contexts',{}).get(k) or {}).get('trace_hash') for k in sorted(contexts)}


def _archive_recipe(model: dict, operations: list[dict], profiles: dict) -> None:
    """Content-address repeated inputs once; a trace references this compact scoring recipe."""
    base=MODEL.parent/'preference-revisions'
    def put(folder, value, key=None):
        ident=key or digest(value);path=base/folder/(ident+'.json')
        if not path.exists():save(path,value)
        return str(path.relative_to(base))
    code=model['code_revision']
    source_ref=put('code',{p.name:p.read_text() for p in sorted(Path(__file__).parent.glob('preference*.py'))},code)
    config_ref=put('config',profiles)
    operation_refs=[put('operations',e) for e in operations]
    archive=base/(model['revision_id']+'.json')
    if not archive.exists():
        scoring={pid:{k:row[k] for k in ('score_weights','quality_gate') if k in row} for pid,row in model['profiles'].items()}
        save(archive,{'schema_version':'2.1','revision_id':model['revision_id'],'scoring_cohort_id':SCORING_COHORT_ID,
            'code_revision':code,'source_ref':source_ref,'profiles_ref':config_ref,'operation_refs':operation_refs,
            'trace_hashes':model['rebuild_inputs']['trace_dependencies'],'scoring_profiles':scoring})


def rebuild() -> dict:
    with state_lock(FEEDBACK.parent):
        data=load(FEEDBACK,{'events':[]});operations=_journal(data)
        profiles=load(PROFILES,{'profiles':[]});profile_ids=sorted({p['profile_id'] for p in profiles.get('profiles',[]) if p.get('profile_id')})
        trace_data=load(RANKING_TRACES,{'contexts':{}})
        code=code_revision();config_hash=digest(profiles)
        inputs={'operation_count':len(operations),'operations_hash':digest(operations),
                'profiles_hash':config_hash,'trace_dependencies':_trace_dependencies(operations,trace_data)}
        revision=digest({'inputs':inputs,'code_revision':code,'scoring_cohort_id':SCORING_COHORT_ID})
        existing=load(MODEL,{})
        intact=existing.get('checkpoint_hash')==digest({k:v for k,v in existing.items() if k!='checkpoint_hash'})
        if intact and existing.get('revision_id')==revision:
            _write_projections(data,existing)
            return existing
        checkpoint=existing.get('rebuild_inputs') or {};start=checkpoint.get('operation_count',0)
        valid_prefix=(intact and existing.get('code_revision')==code and isinstance(start,int) and 0<=start<=len(operations)
            and checkpoint.get('operations_hash')==digest(operations[:start]) and checkpoint.get('profiles_hash')==config_hash
            and checkpoint.get('trace_dependencies')==_trace_dependencies(operations[:start],trace_data))
        models=existing['profiles'] if valid_prefix else {}
        applied={pid:dict(row.get('score_weights',{})) for pid,row in models.items()}
        if not valid_prefix:start=0
        traces=PreparedTraces(trace_data)  # disk load and immutable hash validation once per transaction
        for index in range(start,len(operations)):
            operation=operations[index]
            if operation.get('event_type') == 'action': continue
            events=_effective_events(operations[:index+1])
            models=_aggregate(events,profile_ids,operation.get('timestamp') or operation['created_at'],traces)
            for pid,model in models.items():
                old=applied.get(pid,{})
                target=model['target_score_weights'];keys=sorted(set(old)|set(target))
                distance=sum(abs(target.get(k,0)-old.get(k,0)) for k in keys)
                scale=min(1.,.5/distance) if distance else 1.
                applied[pid]={k:old.get(k,0)+scale*(target.get(k,0)-old.get(k,0)) for k in keys}
                model['score_weights']=applied[pid]
                model['metrics']['applied_score_budget']=sum(abs(v) for v in applied[pid].values())
        if not models:
            models=_aggregate([],profile_ids,'1970-01-01T00:00:00+00:00',traces)
            for model in models.values():model['score_weights']={}
        for config in profiles.get('profiles',[]):
            row=models.get(config.get('profile_id'))
            if row:
                approved=config.get('learned_preferences') or {}
                row['suggestions']=[x for x in row['suggestions'] if x['reason'] not in approved.get(x['direction'],[])]
        stamp=operations[-1]['timestamp'] if operations else '1970-01-01T00:00:00+00:00'
        model={'schema_version':'2.1','updated_at':stamp,'as_of':stamp,'revision_id':revision,'rebuild_inputs':inputs,
            'code_revision':code,'scoring_cohort_id':SCORING_COHORT_ID,'profiles':models,'policy':{'hard_filters_auto_mutate':False,
                'single_event_max_score_change':.5,'unvalidated_score_ceiling':2.,'validated_score_ceiling':4.,
                'support_half_life_days':90,'quality_gate_min_contexts':20,'quality_gate_min_pairs':60,
                'reward_source':'explicit_user_review_only','implicit_actions_in_rating_metrics':False}}
        model['checkpoint_hash']=digest(model)
        _archive_recipe(model,operations,profiles)
        save(MODEL,model)
        _write_projections(data,model)
        _record_learning_snapshot(data,model)
        return model


def _write_projections(data: dict, model: dict) -> None:
    events=_effective_events(data['operations'])
    for event in events:
        analysis=analyze_note(event.get('note',''))
        event.update(atoms=analysis['atoms'],unresolved_clauses=analysis['unresolved'],atomizer_version=ATOMIZER_VERSION)
    data.update(schema_version='2.0',events=events)
    save(FEEDBACK,data)
    rows=[dict(e,date=str(e.get('context_id') or '')[:10],entry_id=e.get('context_id'),updated_at=e.get('timestamp'))
          for e in events if e.get('event_type')!='action']
    save(DAILY_TASTE,{'schema_version':'2.0','responses':rows,'updated_at':model['updated_at']})


def _record_learning_snapshot(feedback: dict, model: dict) -> None:
    fingerprint = model['revision_id']
    history = load(LEARNING_HISTORY, {'schema_version':'1.0','snapshots':[]})
    if any(row.get('revision_id') == fingerprint for row in history.get('snapshots', [])):
        return
    profiles = {}
    for pid, row in (model.get('profiles') or {}).items():
        atoms = row.get('atom_signals') or []
        profiles[pid] = {
            'event_count': int(row.get('event_count') or 0),
            'metrics': row.get('metrics') or {},
            'quality_gate': row.get('quality_gate') or {},
            'atom_stage_counts': {
                stage: sum(1 for atom in atoms if atom.get('stage') == stage)
                for stage in ('tentative','reinforced','stable','mixed')
            },
            'max_effective_atom_weight': round(max([abs(float(atom.get('effective_weight') or 0)) for atom in atoms] or [0.0]), 4),
        }
    snapshots = history.setdefault('snapshots', [])
    snapshots.append({
        'revision_id': fingerprint,
        'created_at': now(),
        'feedback_updated_at': feedback.get('updated_at'),
        'profiles': profiles,
    })
    history['snapshots'] = snapshots[-200:]
    history['updated_at'] = now()
    save(LEARNING_HISTORY, history)


def apply_suggestion(profile_id: str, reason: str, direction: str) -> dict:
    with state_lock(FEEDBACK.parent):
        return _apply_suggestion(profile_id, reason, direction)


def _apply_suggestion(profile_id: str, reason: str, direction: str) -> dict:
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
    q=sp.add_parser('record'); q.add_argument('--key',required=True); q.add_argument('--verdict',required=True); q.add_argument('--reasons',default=''); q.add_argument('--tags'); q.add_argument('--note',default=''); q.add_argument('--profile'); q.add_argument('--source',default='manual'); q.add_argument('--external-id'); q.add_argument('--context'); q.add_argument('--recommended-rank'); q.add_argument('--read-chars',type=int)
    sp.add_parser('rebuild')
    q=sp.add_parser('apply'); q.add_argument('--profile',required=True); q.add_argument('--reason',required=True); q.add_argument('--direction',required=True)
    sp.add_parser('status')
    a=p.parse_args()
    if a.cmd=='record': result=record(canonical_key=a.key,verdict=a.verdict,reasons=[x.strip() for x in a.reasons.split(',') if x.strip()],tags=[x.strip() for x in a.tags.split(',') if x.strip()] if a.tags is not None else None,note=a.note,profile_id=a.profile,source=a.source,external_id=a.external_id,context_id=a.context,recommended_rank=a.recommended_rank,read_chars=a.read_chars)
    elif a.cmd=='rebuild': result=rebuild()
    elif a.cmd=='apply': result=apply_suggestion(a.profile,a.reason,a.direction)
    else: result={'feedback':load(FEEDBACK,{'events':[]}), 'model':load(MODEL,{'profiles':{}})}
    print(json.dumps(result,ensure_ascii=False,indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
