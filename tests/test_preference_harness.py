"""Independent-audit regressions. Synthetic evidence never becomes runtime user data."""
import copy
import json
import sys
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import preference_feedback as f
import preference_rank as r
from preference_atoms import analyze_note, extract_note_atoms
from preference_state import digest
from preference_contract import request_hash, validate_entry


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for key in ['FEEDBACK','MODEL','PROFILES','DAILY_TASTE','WORK_INDEX','RANKING_TRACES','LEARNING_HISTORY']:
            self.stack.enter_context(patch.object(f, key, self.root/(key+'.json')))
        self.stack.enter_context(patch.object(r, 'TRACE', f.RANKING_TRACES))
        f.save(f.PROFILES, {'profiles':[{'profile_id':'p'}]})
        f.save(f.DAILY_TASTE, {'responses':[]}); f.save(f.WORK_INDEX, {'works':[]})
        f.save(self.root/'data/work-index.json',{'works':[]})

    def request(self, **overrides):
        return dict(context_id='e',profile_id='p',hard_filters={},explicit_dimensions=[],
                    analysis_confirmed=True,review_budget=5,**overrides)

    def candidate(self, title='A', base=80, value=1, request=None):
        request=request or self.request()
        path=self.root/'workspace'/'sample.txt';path.parent.mkdir(exist_ok=True)
        path.write_text('日本語の本文。',encoding='utf-8')
        import hashlib
        row={'title':title,'url':'https://example.test/'+title,'base_score':base,'eligible':True,'length_chars':300000,
             'samples':[{'sample_id':'s','path':'workspace/sample.txt','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_url':'https://example.test/episode'}],
             'preference_features':[{'atom':'pacing:fast','value':value,'confidence':1,'sample_id':'s','start':0,'end':8,'evidence':'日本語の本文。'}]}
        row['preference_features'][0]['end']=len('日本語の本文。')
        row['eligibility_receipt']={'request_hash':request_hash(request),'candidate_key':r.canonical(row),'checks':{'min_chars':{'status':'pass','evidence':'300000 chars','source_url':row['url']}}}
        return row

    def frozen_trace(self, context='e', good=True, works=5):
        rows={}
        for i in range(works):
            rating=i%5+1
            rows[f'w{i}']={'selected':True,'preference_features':[{'atom':'pacing:fast','value':(rating-3)/2,'confidence':1}],
                           'preference_learning':{'base_score':50+(rating-3)*(-.1 if good else .1),'exploit_score':50+(rating-3)*(.1 if good else -.1)}}
        trace={'schema_version':'2.0','scoring_cohort_id':f.SCORING_COHORT_ID,'profile_id':None,'model_revision':'frozen-before-review','request_hash':'frozen-request',
               'created_at':'2026-09-01T00:00:00+00:00','candidates':rows,'model_snapshot':{'code_revision':f.code_revision()}}
        trace['trace_hash']=digest(trace)
        return trace

    def batch(self, n, negative_after=None, same_work=False, same_context=False):
        events=[]
        for i in range(n):
            negative=negative_after is not None and i>=negative_after
            events.append({'canonical_key':'same' if same_work else f'w{i}', 'context_id':'same' if same_context else f'e{i}',
                'timestamp':f'2026-09-08T00:{i//60:02}:{i%60:02}+00:00',
                'verdict':'exclude' if negative else 'love','rating':1 if negative else 5,'score':-3 if negative else 3,
                'note':'전개가 빠른 건 싫다' if negative else '전개가 빠른 게 좋다','reasons':[],'tags':[]})
        f.save(f.FEEDBACK,{'events':events});return f.rebuild()['profiles']['__global__']

    def record(self, key='a', verdict='love', context='e', note='전개가 빠른 게 좋다', **kw):
        return f.record(canonical_key=key, verdict=verdict, context_id=context, note=note,
                        reasons=[], **kw)

    def test_negative_scope_and_mixed_clauses(self):
        cases = {
            '전개가 빠른 건 싫다': {('pacing:fast',-1)},
            '전개가 너무 빠름': {('pacing:fast',-1)},
            '전개가 느리지만 좋다': {('pacing:slow',1)},
            '느린 전개가 좋다': {('pacing:slow',1)},
            '문체는 좋지 않다': {('prose:rough',-1)},
            '경어 문체는 별로': {('prose:formal_honorific',-1)},
            '캐릭터는 매력 없고 문체는 좋다': {('characters:flat',-1),('prose:polished',1)},
            '문체는 좋고 전개는 별로': {('prose:polished',1),('pacing:quality_deficit',-1)},
            '겉만 그럴듯하게 묘사함': {('prose:surface_only',-1)},
        }
        for note, expected in cases.items():
            with self.subTest(note=note):
                self.assertEqual({(x['key'],x['polarity']) for x in extract_note_atoms(note)}, expected)
        for note in ['주인공 설득력이 떨어지는 건 아니다','시간 순서를 뒤집어 회수하는 구성이 좋다']:
            self.assertEqual(extract_note_atoms(note), [])
            self.assertTrue(analyze_note(note)['unresolved'])

    def test_quality_deficit_cannot_penalize_positive_trait(self):
        self.record(note='주인공 설득력이 떨어짐. 세계관이 허술하다', verdict='exclude')
        model=f.load(f.MODEL,{})['profiles']['__global__']
        weights=model['score_weights']
        self.assertNotIn('protagonist:plausibility',weights)
        self.assertNotIn('worldbuilding:coherence',weights)
        self.assertLess(weights['protagonist:implausible'],0)
        self.assertLess(weights['worldbuilding:incoherent'],0)

    def test_cross_ui_correction_and_retry_are_one_review(self):
        self.record(source='daily_taste',external_id='daily_taste:d:a',tags=['keep'])
        self.record(verdict='exclude',note='전개가 빠른 건 싫다',source='private_console',external_id='private_console:global:a')
        data=f.load(f.FEEDBACK,{})
        self.assertEqual(len(data['events']),1);self.assertEqual(len(data['operations']),2)
        self.assertEqual(data['events'][0]['rating'],1)
        self.assertEqual(data['events'][0]['tags'],['keep'])
        before=f.load(f.MODEL,{})
        self.record(verdict='exclude',note='전개가 빠른 건 싫다',source='private_console',external_id='new-retry-id')
        self.assertEqual(len(f.load(f.FEEDBACK,{})['operations']),2)
        self.assertEqual(f.load(f.DAILY_TASTE,{})['responses'][0]['verdict'],'exclude')
        self.assertEqual(before['profiles'],f.load(f.MODEL,{})['profiles'])

    def test_different_context_review_not_overwritten(self):
        self.record(context='one');self.record(context='two',verdict='exclude')
        self.assertEqual(len(f.load(f.FEEDBACK,{})['events']),2)

    def test_concurrent_records_are_not_lost(self):
        failures=[]
        def write(i):
            try:self.record(key=f'w{i}',context=f'e{i}')
            except Exception as exc:failures.append(str(exc))
        threads=[threading.Thread(target=write,args=(i,)) for i in range(20)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(failures,[])
        self.assertEqual(len(f.load(f.FEEDBACK,{})['events']),20)

    def test_continuous_learning_conflict_and_independent_stage(self):
        one=self.batch(1);twenty=self.batch(20)
        self.assertLessEqual(abs(one['score_weights']['pacing:fast']),.1)
        self.assertGreater(twenty['score_weights']['pacing:fast'],one['score_weights']['pacing:fast']*10)
        conflict=self.batch(20,negative_after=10)
        signal=conflict['atom_signals'][0]
        self.assertLess(abs(signal['effective_weight']),.05)
        self.assertEqual(signal['stage'],'mixed')
        repeated=self.batch(5,same_work=True,same_context=True)
        self.assertEqual(repeated['atom_signals'][0]['stage'],'tentative')
        self.assertEqual(repeated['atom_signals'][0]['count'],1)

    def test_request_violation_and_override(self):
        request=self.request(intent='느린 정치극을 찾아줘')
        profile={'score_weights':{'pacing:fast':2}}
        slow=self.candidate('slow',80,-1,request);fast=self.candidate('fast',78,1,request)
        result=r.rank_candidates([slow,fast],profile,count=2,seed='s',request=request,root=self.root)
        self.assertEqual(result['selected'][0]['title'],'slow')
        self.assertEqual(result['selected'][0]['preference_learning']['rerank_shift'],0)
        fast['must_not_violations']=['commercial']
        result=r.rank_candidates([fast],profile,count=1,seed='s',request=request,root=self.root)
        self.assertEqual(result['selected'],[])
        del slow['eligible']
        self.assertEqual(r.rank_candidates([slow],profile,count=1,seed='s',request=request,root=self.root)['selected'],[])

    def test_duplicate_features_and_fabricated_evidence_rejected(self):
        c=self.candidate();c['preference_features']*=8
        with self.assertRaises(ValueError):r.rank_candidates([c],{},count=1,seed='s',request=self.request(),root=self.root)
        c=self.candidate();c['preference_features'][0]['evidence']='not in the sample'
        with self.assertRaises(ValueError):r.rank_candidates([c],{},count=1,seed='s',request=self.request(),root=self.root)

    def test_trace_immutable_idempotent_and_pre_feedback(self):
        result=r.rank_candidates([self.candidate()],{},count=1,seed='s',request=self.request(),root=self.root)
        model={'revision_id':'before','profiles':{}}
        f.save(self.root/'data/entries/e.json',{'status':'draft','entry_id':'e','profile_id':'p','ranking_request':self.request(),'request_frozen_at':'2026-09-01T00:00:00+00:00'})
        h=r.persist_trace('e','p',result,model=model,root=self.root)
        self.assertEqual(h,r.persist_trace('e','p',result,model=model,root=self.root))
        result['all_scored'][0]['preference_learning']['exploit_score']=99
        with self.assertRaises(ValueError):r.persist_trace('e','p',result,model=model,root=self.root)
        f.RANKING_TRACES.unlink()
        # persist_trace uses the canonical workspace filename, independently of feedback test alias.
        f.save(f.RANKING_TRACES.parent/'preference-feedback.json',{'events':[{'context_id':'e'}]})
        with self.assertRaises(ValueError):r.persist_trace('e','p',result,model=model,root=self.root)

    def test_explore_reaches_review_budget_and_abstains_from_garbage(self):
        rows=[self.candidate(f'w{i}',90-i) for i in range(20)]
        result=r.rank_candidates(rows,{},count=10,seed='repeatable',request=self.request(),root=self.root)
        explore=[x for x in result['selected'] if x['selection_mode']=='explore']
        self.assertTrue(explore);self.assertTrue(all(x['sample_priority'] for x in explore))
        self.assertEqual(result,r.rank_candidates(rows,{},count=10,seed='repeatable',request=self.request(),root=self.root))
        rows=[self.candidate(f'g{i}',90-i) for i in range(4)]+[self.candidate('bad',2)]
        result=r.rank_candidates(rows,{},count=5,seed='s',request=self.request(),root=self.root)
        self.assertFalse(any(x['selection_mode']=='explore' and x['base_score']<60 for x in result['selected']))

    def test_rebuild_without_model_replays_bounded_updates(self):
        p=self.batch(20);previous=dict(p['score_weights'])
        self.record(key='w0',context='e0',verdict='exclude',note='전개가 빠른 건 싫다')
        expected=f.load(f.MODEL,{})
        current=expected['profiles']['__global__']['score_weights']
        self.assertLessEqual(sum(abs(current.get(k,0)-previous.get(k,0)) for k in set(current)|set(previous)),.500001)
        f.MODEL.unlink();actual=f.rebuild()
        self.assertEqual(actual,expected)

    def test_gate_requires_independent_confirmed_contexts(self):
        for n in (1,6,19,24):
            rows=[{'context_id':str(i),'pairs':40,'delta':1.} for i in range(n)]
            self.assertLessEqual(f._quality_gate({'prospective_contexts':rows})['multiplier'],.5)
        rows=[{'context_id':str(i),'pairs':3,'delta':1.} for i in range(25)]
        self.assertAlmostEqual(f._quality_gate({'prospective_contexts':rows})['multiplier'],.55)
        bad=[dict(x,delta=-1.) for x in rows]
        self.assertEqual(f._quality_gate({'prospective_contexts':bad})['status'],'degraded')

    def test_prospective_pair_learning_uses_valid_frozen_shared_features(self):
        trace=self.frozen_trace(works=10)
        f.save(f.RANKING_TRACES,{'contexts':{'e':trace}})
        events=[{'canonical_key':f'w{i}','context_id':'e','profile_id':None,'created_at':'2026-09-08T00:00:00+00:00',
                 'timestamp':'2026-09-08T00:00:00+00:00','rating':i%5+1} for i in range(10)]
        pairs,_=f._pairwise(events)
        self.assertEqual(len(pairs),40)
        weights,n=f._pairwise_atom_model(pairs)
        self.assertEqual(n,40);self.assertEqual(weights[0]['evidence_contexts'],1)
        self.assertLessEqual(weights[0]['confidence'],1/6)
        self.assertEqual(weights,f._pairwise_atom_model(pairs*10)[0])
        metrics=f._prospective_rank_metrics(pairs)
        self.assertEqual(metrics['prospective_context_count'],1)
        self.assertEqual(f._quality_gate(metrics)['status'],'calibrating')
        trace['candidates']['w0']['preference_features']=[]  # mutable/tampered trace rejected entirely
        f.save(f.RANKING_TRACES,{'contexts':{'e':trace}})
        self.assertEqual(f._pairwise_atom_model(pairs),([],0))

    def test_same_tied_pair_population_is_scored(self):
        trace=self.frozen_trace(works=2)
        trace['candidates']['w0']['preference_learning']['base_score']=50
        trace['candidates']['w1']['preference_learning']['base_score']=50
        trace['trace_hash']=digest({k:v for k,v in trace.items() if k!='trace_hash'})
        f.save(f.RANKING_TRACES,{'contexts':{'e':trace}})
        pair={'context_id':'e','profile_id':None,'winner':'w1','loser':'w0','rating_margin':1,
              'winner_created_at':'2026-09-08T00:00:00+00:00','loser_created_at':'2026-09-08T00:00:00+00:00'}
        metrics=f._prospective_rank_metrics([pair])
        self.assertEqual(metrics['prospective_base_pair_count'],metrics['prospective_rerank_pair_count'])
        self.assertEqual(metrics['prospective_base_pair_accuracy'],.5)
        pair['loser_created_at']='2026-08-01T00:00:00+00:00'
        self.assertEqual(f._prospective_rank_metrics([pair])['prospective_context_count'],0)

    def test_good_and_bad_frozen_contexts_drive_real_aggregate_gate(self):
        events=[]
        for context in range(34):
            for work,rating in enumerate((1,3,5)):
                events.append(dict(canonical_key=f'w{work}',context_id=f'e{context:02}',profile_id=None,
                    created_at='2026-09-08T00:00:00+00:00',timestamp='2026-09-08T00:00:00+00:00',
                    review_id=f'{context}:{work}',rating=rating,score=rating-3,verdict={1:'exclude',3:'neutral',5:'love'}[rating],
                    note='',reasons=[],tags=[]))
        for good,expected in [(True,1.),(False,.125)]:
            traces={f'e{i:02}':self.frozen_trace(f'e{i:02}',good=good,works=3) for i in range(34)}
            f.save(f.RANKING_TRACES,{'contexts':traces})
            result=f._aggregate(events,[],'2026-09-08T00:00:00+00:00')['__global__']
            self.assertEqual(result['metrics']['prospective_context_count'],34)
            self.assertEqual(result['metrics']['prospective_rerank_pair_count'],102)
            self.assertEqual(result['quality_gate']['multiplier'],expected)
            self.assertLessEqual(sum(abs(v) for v in result['target_score_weights'].values()),4*expected)
        with patch.object(f,'SCORING_COHORT_ID','incompatible-new-policy'):
            self.assertEqual(f._prospective_rank_metrics(f._pairwise(events)[0])['prospective_context_count'],0)

    def test_explicit_genre_and_full_translation_action(self):
        request=self.request();request['hard_filters']={'genres':['romance']}
        row=self.candidate(request=request);row['genres']=['romance']
        row['eligibility_receipt']['checks'].update({'genres:0':{'status':'pass','evidence':'genre metadata','source_url':row['url']}})
        row['preference_features'][0]['atom']='romance:quality'
        result=r.rank_candidates([row],{'score_weights':{'romance:quality':-4}},count=1,seed='s',request=request,root=self.root)
        self.assertEqual(len(result['selected']),1)
        self.assertEqual(result['selected'][0]['preference_learning']['rerank_shift'],0)
        self.record();before=f.load(f.MODEL,{})['profiles']['__global__']
        self.record(key='action',context='action',source='full_translation')
        after=f.load(f.MODEL,{})['profiles']['__global__']
        self.assertEqual(before,after)

    def test_long_memo_shared_denominator_preserves_learning_budget(self):
        # The extractor's semantic fixtures are separate. This attacks atom-count arithmetic directly.
        values=[]
        for n in (1,2,5,10,20):
            atoms=[{'key':f'feature:{i}','label':str(i),'polarity':1,'evidence':'test'} for i in range(n)]
            event={'canonical_key':'one','review_id':'one','context_id':'one','note':'fixture','timestamp':'2026-09-08T00:00:00+00:00',
                   'score':3,'rating':5,'verdict':'love','reasons':[],'tags':[]}
            with patch.object(f,'analyze_note',return_value={'atoms':atoms,'unresolved':[]}):
                profile=f._aggregate([event],[],event['timestamp'])['__global__']
            self.assertAlmostEqual(sum(x['support'] for x in profile['atom_signals']),1)
            values.append(sum(profile['target_score_weights'].values()))
        self.assertLess(max(values)-min(values),1e-10)

if __name__=='__main__':unittest.main()
