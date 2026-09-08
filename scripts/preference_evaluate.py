#!/usr/bin/env python3
"""Report frozen prediction coverage and optional user-labeled discovery recall. Read-only."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from preference_state import load
from preference_contract import trace_valid

ROOT=Path(__file__).resolve().parent.parent


def evaluate(root: Path, benchmark: dict | None = None) -> dict:
    traces=load(root/'workspace/preference-ranking-traces.json',{}).get('contexts',{})
    reviews=load(root/'workspace/preference-feedback.json',{}).get('events',[])
    contexts=[]
    for key,trace in traces.items():
        if not trace_valid(trace):continue
        rows=trace.get('candidates',{});selected=[(k,x) for k,x in rows.items() if x.get('selected')]
        reviewed={e['canonical_key'] for e in reviews if e.get('context_id')==key and e.get('profile_id')==trace.get('profile_id') and e.get('event_type')!='action'}
        contexts.append({'context_id':key,'qualified_pool':len(rows),'rejected_pool':len(trace.get('rejected',[])),
            'selected':len(selected),'reviewed':len(reviewed),'explore_selected':sum(x.get('selection_mode')=='explore' for _,x in selected),
            'explore_reviewed':sum(x.get('selection_mode')=='explore' and k in reviewed for k,x in selected),
            'zero_propensity_candidates':sum(not x.get('inclusion_probability') for x in rows.values()),
            'model_revision':trace['model_revision']})
    result={'contexts':contexts,'observed_only_warning':'Ratings exclude unexposed/unread works; these are not unbiased population rewards.',
            'benchmark':{'status':'not_available','reason':'requires independent user relevance labels'}}
    if benchmark is not None:
        if benchmark.get('label_source')!='user':raise ValueError('benchmark requires independent user labels')
        labels=benchmark.get('labels') or []
        if not labels:raise ValueError('empty benchmark')
        if any(type(x.get('relevant')) is not bool or not x.get('intent_id') or not x.get('canonical_key') for x in labels):
            raise ValueError('each label requires intent_id, canonical_key and boolean relevant')
        intents=[]
        for intent in sorted({x['intent_id'] for x in labels}):
            relevant={x['canonical_key'] for x in labels if x['intent_id']==intent and x['relevant']}
            retrieved=(benchmark.get('retrieved') or {}).get(intent,[])[:20]
            if len(retrieved)!=len(set(retrieved)):raise ValueError('duplicate retrieved key')
            intents.append({'intent_id':intent,'relevant_count':len(relevant),'recall_at_20':len(relevant.intersection(retrieved))/len(relevant) if relevant else None,
                            'retrieved_count':len(retrieved)})
        result['benchmark']={'status':'measured_user_labeled_set','intents':intents}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--benchmark')
    args=parser.parse_args();print(json.dumps(evaluate(ROOT,load(Path(args.benchmark),{}) if args.benchmark else None),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
