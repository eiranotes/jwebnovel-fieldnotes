#!/usr/bin/env python3
"""Bounded secondary ranking after a verified current-request and body-sample contract."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from preference_state import digest, load, save, state_lock, SCORING_COHORT_ID
from preference_contract import (CONTRACT_VERSION, request_hash, protected_dimensions, features,
    finite_number, eligibility, verify_samples, trace_valid)
from rebuild_work_index import canonical

ROOT=Path(__file__).resolve().parent.parent
MODEL=ROOT/'workspace/preference-model.json'
TRACE=ROOT/'workspace/preference-ranking-traces.json'
MAX_PREFERENCE_RERANK_SHIFT=4.0


def _base_score(candidate: dict) -> float:
    return finite_number(candidate.get('base_score'),0,100,'base_score (0–100, explicit)')


def score_candidate(candidate: dict, profile: dict, *, request: dict) -> dict:
    request_hash(request)
    fs=features(candidate);protected=protected_dimensions(request)
    weights={k:finite_number(v,-4,4,'model score weight') for k,v in (profile.get('score_weights') or {}).items()}
    # Weights are already projected, in score units, during deterministic learning replay.
    if sum(abs(float(x)) for x in weights.values()) > MAX_PREFERENCE_RERANK_SHIFT + 1e-6:
        raise ValueError('model exceeds the verified score-weight budget; rebuild it')
    signals={x['atom']:x for x in profile.get('atom_signals',[])}
    contribution=[];shift=0.;uncertainty=[];novelty=[]
    for feature in fs:
        key=feature['atom'];blocked=key in protected or key.split(':')[0] in protected
        weight=0. if blocked else float(weights.get(key,0))
        amount=weight*feature['value']*feature['confidence'];shift+=amount
        learned_conf=float((signals.get(key) or {}).get('confidence') or 0)
        uncertainty.append(1-feature['confidence']*learned_conf)
        novelty.append(0. if key in signals else abs(feature['value'])*feature['confidence'])
        contribution.append(dict(atom=key,contribution=amount,learned_weight=weight,blocked_by_request=blocked))
    base=_base_score(candidate)
    learning={'base_score':base,'rerank_shift':round(shift,6),'exploit_score':round(max(0,min(100,base+shift)),6),
        'uncertainty':sum(uncertainty)/len(uncertainty) if uncertainty else 1.,
        'novelty':sum(novelty)/len(novelty) if novelty else 0.,
        'model_maturity':(profile.get('metrics') or {}).get('model_maturity',0),
        'quality_gate_multiplier':(profile.get('quality_gate') or {}).get('multiplier',.5),
        'matched_atoms':contribution,'score_budget':sum(abs(float(v)) for v in weights.values())}
    return {**candidate,'canonical_key':canonical(candidate),'preference_learning':learning}


def dedupe_context(root: Path, request: dict) -> tuple[dict,dict]:
    policy=(load(root/'config/automation.json',{}).get('dedupe') or {})
    mode=policy.get('default_mode','strict_seen_index')
    if mode not in {'strict_seen_index','cooldown'}:raise ValueError('unknown dedupe mode')
    index=load(root/'data/work-index.json',None)
    if index is None:raise ValueError('rebuild the work index before ranking')
    seen={}
    for row in index.get('works',[]):
        seen[row.get('canonical_key')]=row
        for url in [row.get('url'),*[x.get('url') for x in row.get('platform_instances',[])]]:
            if url:seen[url]=row
    return seen,{'mode':mode,'cooldown_days':int(policy.get('repeat_candidate_cooldown_days',30)),
                 'index_hash':digest(index)}


def repeat_allowed(candidate: dict, seen: dict, policy: dict, request: dict) -> bool:
    prior=seen.get(canonical(candidate)) or seen.get(candidate.get('url'))
    if not prior:return True
    revisit=request.get('revisit') or {};check=(candidate.get('eligibility_receipt') or {}).get('checks',{}).get('revisit',{})
    if revisit.get('enabled') is True and revisit.get('reason') and check.get('status')=='pass' and check.get('evidence') and check.get('source_url'):return True
    if policy['mode']=='strict_seen_index':return False
    try:
        then=datetime.fromisoformat(str(prior['last_seen_entry'])[:10])
        date=datetime.fromisoformat(str(request['context_id'])[:10])
    except (KeyError,ValueError):return False
    return (date-then).days>=policy['cooldown_days']


def rank_candidates(candidates: list[dict], profile: dict, *, count: int, seed: str,
                    request: dict, root: Path | None = None) -> dict:
    root=root or ROOT;rh=request_hash(request)
    if count < 0:raise ValueError('count must be nonnegative')
    prior,dedupe=dedupe_context(root,request)
    eligible=[];rejected=[];seen=set()
    for candidate in candidates:
        key=canonical(candidate)
        if key in seen:raise ValueError('duplicate canonical candidate in pool')
        seen.add(key)
        if not repeat_allowed(candidate,prior,dedupe,request):
            rejected.append({**candidate,'canonical_key':key,'rejection_reason':'seen_work'});continue
        passed,reason=eligibility(candidate,request)
        if not passed:
            rejected.append({**candidate,'canonical_key':key,'rejection_reason':reason});continue
        if _base_score(candidate)<float(request.get('minimum_base_score',60)):
            rejected.append({**candidate,'canonical_key':key,'rejection_reason':'below_quality_floor'});continue
        verify_samples(candidate,root)
        eligible.append(score_candidate(candidate,profile,request=request))
    ordered=sorted(eligible,key=lambda x:(-x['preference_learning']['exploit_score'],x['canonical_key']))
    count=min(count,len(ordered))
    review_budget=min(count,max(0,int(request.get('review_budget',5))))
    quota=min(max(1,round(count*.2)),review_budget//5) if count>=5 else 0
    exploit=ordered[:count-quota]
    pool=ordered[count-quota:]
    cutoff=sorted((_base_score(x) for x in ordered),reverse=True)[count-1] if count else 100
    # Absolute quality floor + relative frontier; abstain rather than fill with garbage.
    floor=max(float(request.get('minimum_base_score',60)),cutoff-5)
    frontier=[x for x in pool if _base_score(x)>=floor]
    quota=min(quota,len(frontier))
    if not quota:
        exploit=ordered[:count]
    rng=random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8],'big'))
    frontier.sort(key=lambda x:x['canonical_key'])
    explore=rng.sample(frontier,quota)
    explore_keys={x['canonical_key'] for x in explore}
    exploit=[x for x in ordered if x['canonical_key'] not in explore_keys][:count-len(explore)]
    probabilities={x['canonical_key']:quota/len(frontier) for x in frontier} if frontier else {}
    for row in exploit:
        row.update(selection_mode='exploit',selection_probability=1.)
    for row in explore:
        row.update(selection_mode='explore',selection_probability=probabilities[row['canonical_key']])
    # Reserve exploration inside acquisition/review capacity, even if display slate is longer.
    split=max(0,review_budget-len(explore))
    selected=exploit[:split]+explore+exploit[split:]
    for i,row in enumerate(selected,1):row.update(preference_rank=i,sample_priority=i<=review_budget)
    selected_keys={x['canonical_key'] for x in selected}
    for row in eligible:
        row['inclusion_probability']=1. if row in exploit else probabilities.get(row['canonical_key'],0.)
        row['selected']=row['canonical_key'] in selected_keys
    return {'schema_version':CONTRACT_VERSION,'request':request,'request_hash':rh,
        'profile_event_count':profile.get('event_count',0),'policy':{'seed':seed,'explore_ratio_target':.2,
            'dedupe':dedupe,'explore_slots':len(explore),'review_budget':review_budget,'frontier_floor':floor,
            'max_preference_rerank_shift':4,'exploration':'uniform_without_replacement_qualified_frontier'},
        'selected':selected,'all_scored':eligible,'rejected':rejected}


def persist_trace(context_id: str, profile_id: str, result: dict, *, model: dict, root: Path | None = None) -> str:
    root=root or ROOT
    request=result['request']
    if context_id!=request['context_id'] or profile_id!=request['profile_id']:raise ValueError('trace context/profile mismatch')
    if not model.get('revision_id'):raise ValueError('model revision must be fixed before recommendation')
    rows={canonical(row):row for row in result['all_scored']}
    entry=load(root/'data/entries'/f'{context_id}.json',{})
    if entry.get('profile_id')!=profile_id:raise ValueError('draft profile differs from ranking model scope')
    if model.get('profiles') and profile_id not in model['profiles']:raise ValueError('unknown model profile')
    if digest(entry.get('ranking_request'))!=request_hash(request) or not entry.get('request_frozen_at'):
        raise ValueError('freeze the entry request before discovery and ranking')
    content={'schema_version':CONTRACT_VERSION,'context_id':context_id,'profile_id':profile_id,
        'request':request,'request_hash':request_hash(request),'model_revision':model['revision_id'],
        'model_ref':f"preference-revisions/{model['revision_id']}.json",
        'scoring_cohort_id':model.get('scoring_cohort_id',SCORING_COHORT_ID),'code_revision':model.get('code_revision'),'policy':result['policy'],'candidates':rows,
        'rejected':result.get('rejected',[]),'selected_order':[canonical(x) for x in result['selected']]}
    with state_lock(TRACE.parent):
        data=load(TRACE,{'schema_version':CONTRACT_VERSION,'contexts':{}})
        existing=data['contexts'].get(context_id)
        if existing:
            existing_content={k:v for k,v in existing.items() if k not in {'created_at','trace_hash'}}
            if trace_valid(existing) and digest(existing_content)==digest(content):return existing['trace_hash']
            raise ValueError('ranking trace is immutable; use a new research entry')
        feedback=load(TRACE.parent/'preference-feedback.json',{})
        if any(e.get('context_id')==context_id for e in feedback.get('operations',feedback.get('events',[]))):
            raise ValueError('cannot create a prospective trace after context feedback')
        # Retain exact sampled bytes by content address, independently of mutable acquisition files.
        for row in rows.values():
            for sample in verify_samples(row,root):
                raw=(root/sample['path']).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=sample['sha256']:raise ValueError('sample changed during trace commit')
                dest=root/'workspace/preference-evidence'/f"{sample['sha256']}.txt"
                dest.parent.mkdir(parents=True,exist_ok=True)
                if dest.exists():
                    if dest.read_bytes()!=raw:raise ValueError('immutable sample cache conflict')
                else:
                    with dest.open('xb') as stream:stream.write(raw)
        stamp=datetime.now(timezone.utc).isoformat()
        trace={**content,'created_at':stamp};trace['trace_hash']=digest(trace)
        data['contexts'][context_id]=trace;data['updated_at']=stamp
        save(TRACE,data)
        return trace['trace_hash']


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',required=True);parser.add_argument('--context',required=True)
    parser.add_argument('--request',required=True,help='Frozen request JSON, prepared before discovery')
    parser.add_argument('--input',required=True);parser.add_argument('--count',type=int,default=5)
    parser.add_argument('--seed',required=True)
    args=parser.parse_args()
    from preference_feedback import rebuild
    model=rebuild();profile=model['profiles'].get(args.profile,model['profiles']['__global__'])
    data=load(Path(args.input),{});candidates=data if isinstance(data,list) else data['candidates']
    result=rank_candidates(candidates,profile,count=args.count,seed=args.seed,request=load(Path(args.request),{}))
    result['trace_hash']=persist_trace(args.context,args.profile,result,model=model)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
