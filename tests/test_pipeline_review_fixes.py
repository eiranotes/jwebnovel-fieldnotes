"""Executable counterexamples to the second review; all user-like data is synthetic/private."""
import copy
import io
from contextlib import redirect_stdout
import json
import random
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_preference_harness as harness
import preference_feedback as f
import preference_rank as r
import private_console as console
import select_search_profiles as selector
from preference_atoms import analyze_note, extract_note_atoms
from preference_contract import eligibility, request_hash, finalize_entry, validate_entry, selected_candidates
from preference_state import digest, load, save
from test_runtime_sync import load_module


class ReviewFixTests(unittest.TestCase):
    def setUp(self):
        self.h=harness.HarnessTests();self.h.setUp();self.addCleanup(self.h.doCleanups)
        self.root=self.h.root

    def test_default_floor_and_honest_exception(self):
        req=self.h.request();row=self.h.candidate(request=req);row['length_chars']=12000
        self.assertEqual(eligibility(row,req),(False,'length'))
        req.update(length_exception={'enabled':True,'explicit_minimum':False})
        row['length_exception']=True;checks=row['eligibility_receipt']['checks']
        checks['min_chars']['status']='fail';checks['min_chars']['evidence']='12000 chars'
        checks['length_exception_fit']={'status':'pass','evidence':'strong fingerprint fit','source_url':row['url']}
        row['eligibility_receipt']['request_hash']=request_hash(req)
        self.assertEqual(eligibility(row,req),(True,'pass'))
        checks['min_chars']['status']='pass'
        self.assertFalse(eligibility(row,req)[0]) # no fabricated passing minimum
        checks['min_chars']['status']='fail';req['hard_filters']['min_chars']=500000
        row['eligibility_receipt']['request_hash']=request_hash(req)
        self.assertFalse(eligibility(row,req)[0]) # never waive an explicit higher minimum
        for invalid in [0,-1,float('nan'),False]:
            req['hard_filters']['min_chars']=invalid
            with self.assertRaises(ValueError):request_hash(req)

    def test_korean_inflections_keep_specific_dimensions(self):
        for text,key in [('전개가 빨라서 좋았다','pacing:fast'),('전개가 빨랐다','pacing:fast'),('문장이 잘 읽힌다','prose:polished')]:
            self.assertEqual({a['key'] for a in extract_note_atoms(text)},{key})
        unresolved=analyze_note('전개가 쏜살같아서 좋았다')
        self.assertEqual(unresolved['atoms'],[]);self.assertTrue(unresolved['unresolved'])

    def test_incremental_checkpoint_matches_full_replay_after_correction(self):
        self.h.batch(50)
        with patch.object(f,'_aggregate',wraps=f._aggregate) as aggregate:
            self.h.record(key='w0',context='e0',verdict='exclude',note='전개가 빠른 건 싫다')
            self.assertEqual(aggregate.call_count,1)
        expected=f.load(f.MODEL,{})
        f.MODEL.unlink();self.assertEqual(f.rebuild(),expected)
        corrupted=copy.deepcopy(expected);corrupted['profiles']['__global__']['score_weights']={'fake':4}
        save(f.MODEL,corrupted)
        self.assertEqual(f.rebuild(),expected) # integrity-invalid checkpoints cannot affect scores
        before_sources=list((f.MODEL.parent/'preference-revisions/code').glob('*.json'))
        self.h.record(key='new',context='new')
        self.assertEqual(before_sources,list((f.MODEL.parent/'preference-revisions/code').glob('*.json')))

    def test_cohort_survives_provenance_change_but_separates_incompatible_policy(self):
        trace=self.h.frozen_trace(works=2);trace['model_snapshot']['code_revision']='some earlier comment-only revision'
        trace['trace_hash']=digest({k:v for k,v in trace.items() if k!='trace_hash'})
        save(f.RANKING_TRACES,{'contexts':{'e':trace}})
        pair=dict(context_id='e',profile_id=None,winner='w1',loser='w0',rating_margin=1,
                  winner_created_at='2026-09-08T00:00:00+00:00',loser_created_at='2026-09-08T00:00:00+00:00')
        self.assertEqual(f._prospective_rank_metrics([pair])['prospective_context_count'],1)
        with patch.object(f,'SCORING_COHORT_ID','new-incompatible-policy'):
            result=f._prospective_rank_metrics([pair])
            self.assertEqual(result['prospective_context_count'],0)
            self.assertEqual(result['cohort_pair_counts'],{trace['scoring_cohort_id']:1})

    def test_confirmation_context_order_uses_time_not_identifier(self):
        traces={};pairs=[]
        for ident,day in [('z-older',1),('a-newer',2)]:
            trace=self.h.frozen_trace(works=2);trace['created_at']=f'2026-09-0{day}T00:00:00+00:00'
            trace['trace_hash']=digest({k:v for k,v in trace.items() if k!='trace_hash'});traces[ident]=trace
            pairs.append(dict(context_id=ident,profile_id=None,winner='w1',loser='w0',rating_margin=1,
                  winner_created_at='2026-09-08T00:00:00+00:00',loser_created_at='2026-09-08T00:00:00+00:00'))
        save(f.RANKING_TRACES,{'contexts':traces})
        self.assertEqual([x['context_id'] for x in f._prospective_rank_metrics(pairs)['prospective_contexts']],['z-older','a-newer'])

    def test_quota_two_cardinality_with_nonzero_learned_scores(self):
        rng=random.Random(19);req=self.h.request();req['review_budget']=10
        for iteration in range(100):
            rows=[self.h.candidate(f'w{i}',rng.uniform(60,100),rng.uniform(-1,1),req) for i in range(20)]
            result=r.rank_candidates(rows,{'score_weights':{'pacing:fast':4}},count=10,seed=str(iteration),request=req,root=self.root)
            self.assertEqual(len(result['selected']),10)
            self.assertEqual(len({x['canonical_key'] for x in result['selected']}),10)
            self.assertEqual(sum(x['selection_mode']=='explore' for x in result['selected']),2)

    def test_seen_index_enforced_before_sample_read_and_cooldown(self):
        req=self.h.request();row=self.h.candidate(request=req)
        save(self.root/'data/work-index.json',{'works':[dict(canonical_key=r.canonical(row),url=row['url'],last_seen_entry='2026-08-01-01')]})
        row['samples'][0]['path']='missing'
        self.assertEqual(r.rank_candidates([row],{},count=1,seed='s',request=req,root=self.root)['selected'],[])
        req['context_id']='2026-09-08-01';row=self.h.candidate(request=req)
        save(self.root/'config/automation.json',{'dedupe':{'default_mode':'cooldown','repeat_candidate_cooldown_days':30}})
        self.assertEqual(len(r.rank_candidates([row],{},count=1,seed='s',request=req,root=self.root)['selected']),1)

    def test_profile_compare_and_swap_and_selection_consumption(self):
        config={'profiles':[{'profile_id':'p','name':'P','enabled':True}], 'selection':{'selected_profile_ids':['p'],'explicit_selection_mode':'once'}}
        path=self.root/'config/search-profiles.json';save(path,config)
        with patch.object(console,'ROOT',self.root),patch.object(console,'PROFILES',path),patch.object(selector,'ROOT',self.root),patch.object(selector,'CONFIG',path):
            stale=console.profile_document()
            selector.consume_explicit_selection(config,'explicit_selected')
            with self.assertRaises(ValueError):console.save_profiles(stale)
            fresh=console.profile_document()
            selected=console.update_selection({'selected_profile_ids':['p'],'profile_revision':fresh['_revision']})
            self.assertEqual(selected['selected_profile_ids'],['p'])
            with self.assertRaises(ValueError):selector.consume_explicit_selection(fresh,'explicit_selected')
            self.assertEqual(load(path,{})['selection']['selected_profile_ids'],['p'])

    def test_request_only_selection_never_rebuilds_preference_state(self):
        path=self.root/'config/search-profiles.json'
        save(path,{'profiles':[{'profile_id':'p','enabled':True,'learned_preferences':{'prefer':['x']}}]})
        with patch.object(selector,'ROOT',self.root),patch.object(selector,'CONFIG',path),patch.object(selector,'STATE',self.root/'rotation.json'),patch.object(selector,'rebuild_preferences') as rebuild,patch.object(selector,'seed_known'),patch.object(selector,'active_context',return_value={}),patch.object(sys,'argv',['select_search_profiles.py']):
            output=io.StringIO()
            with redirect_stdout(output):selector.main()
            rebuild.assert_not_called()
            self.assertNotIn('learned_preferences',json.loads(output.getvalue())['profiles'][0])

    def test_immutable_union_and_explicit_cas_conflict_resolution(self):
        mod=load_module();mod.ROOT=self.root/'repo';mod.RUNTIME=self.root/'runtime'
        for root in [mod.ROOT,mod.RUNTIME]:root.mkdir()
        rel='workspace/preference-revisions'
        save(mod.ROOT/rel/'left.json',{'left':1});save(mod.RUNTIME/rel/'right.json',{'right':1})
        result=mod.push();self.assertEqual(result['status'],'pushed')
        self.assertTrue((mod.ROOT/rel/'right.json').exists());self.assertTrue((mod.RUNTIME/rel/'left.json').exists())
        path='config/search-profiles.json';save(mod.ROOT/path,{'value':0});mod.push()
        save(mod.ROOT/path,{'value':1});save(mod.RUNTIME/path,{'value':2})
        self.assertEqual(mod.push()['status'],'conflict')
        left,right=mod.entry_hash(mod.ROOT/path),mod.entry_hash(mod.RUNTIME/path)
        with self.assertRaises(ValueError):mod.resolve(path,'runtime','stale-hash',right)
        result=mod.resolve(path,'runtime',left,right)
        self.assertEqual(load(mod.ROOT/path,{})['value'],2)
        backup=Path(result['backup'])
        self.assertEqual(load(backup/'canonical'/path,{})['value'],1)
        self.assertEqual(load(backup/'runtime'/path,{})['value'],2)
        self.assertEqual(mod.push()['status'],'pushed')

    def test_schema2_cli_freeze_rank_finalize_register_review(self):
        canonical=Path(__file__).resolve().parents[1]
        shutil.copytree(canonical/'scripts',self.root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
        for name in ['index.html','console.html']:shutil.copy2(canonical/name,self.root/name)
        save(self.root/'data/research-index.json',[])
        save(self.root/'config/search-profiles.json',{'profiles':[{'profile_id':'p','name':'P','enabled':True}]})
        def run(script,*args,ok=True):
            result=subprocess.run([sys.executable,str(self.root/'scripts'/script),*args],cwd=self.root,text=True,capture_output=True)
            if ok:self.assertEqual(result.returncode,0,result.stderr)
            else:self.assertNotEqual(result.returncode,0)
            return result
        result=run('new_entry.py','--date','2026-09-08','--profile','p','--title','Synthetic contract test')
        eid=result.stdout.splitlines()[0];request=self.h.request();request['context_id']=eid
        request['length_exception']={'enabled':True,'explicit_minimum':False};save(self.root/'request.json',request)
        wrong=copy.deepcopy(request);wrong['profile_id']='other';save(self.root/'wrong.json',wrong)
        run('new_entry.py','--freeze-request',eid,'--request','wrong.json',ok=False)
        run('new_entry.py','--freeze-request',eid,'--request','request.json')
        candidates=[self.h.candidate(f'work{i}',90-i,request=request) for i in range(6)]
        short=candidates[0];short['length_chars']=120000;short['length_exception']=True
        checks=short['eligibility_receipt']['checks'];checks['min_chars'].update(status='fail',evidence='120000 chars')
        checks['length_exception_fit']={'status':'pass','evidence':'fixture fit','source_url':short['url']}
        save(self.root/'candidates.json',candidates)
        run('preference_rank.py','--context',eid,'--profile','p','--request','request.json','--input','candidates.json','--count','5','--seed','fixture')
        traces=load(self.root/'workspace/preference-ranking-traces.json',{});trace=traces['contexts'][eid]
        self.assertNotIn('model_snapshot',trace)
        self.assertTrue((self.root/'workspace'/trace['model_ref']).is_file())
        run('new_entry.py','--finalize',eid)
        entry=load(self.root/'data/entries'/f'{eid}.json',{});validate_entry(entry,traces)
        self.assertEqual(len(entry['results']['length_exceptions']),1)
        self.assertEqual([r.canonical(x) for x in selected_candidates(entry)],trace['selected_order'])
        run('register_targets.py','--entry',eid,'--top-n','5')
        self.assertEqual(len(load(self.root/'data/work-registry.json',{})['works']),5)
        for key,verdict in zip(trace['selected_order'][:2],['love','exclude']):
            run('preference_feedback.py','record','--key',key,'--context',eid,'--profile','p','--verdict',verdict)
        model=load(self.root/'workspace/preference-model.json',{})
        self.assertEqual(model['profiles']['p']['metrics']['prospective_rerank_pair_count'],1)
        run('validate_repo.py')


if __name__=='__main__':unittest.main()
