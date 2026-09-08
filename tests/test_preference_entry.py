import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import preference_rank as r
from preference_contract import finalize_entry, validate_entry
from preference_state import load, save
import test_preference_harness as harness


class EntryIntegrationTests(unittest.TestCase):
    def test_frozen_slate_finalizes_safely_and_cannot_be_reordered(self):
        helper=harness.HarnessTests();helper.setUp()
        try:
            root=helper.root;request=helper.request()
            save(root/'data/entries/e.json',{'entry_id':'e','profile_id':'p','status':'draft','ranking_request':request,'request_frozen_at':'2026-09-01T00:00:00+00:00','preference_policy':{'required_trace':True}})
            with patch.object(r,'TRACE',root/'workspace/preference-ranking-traces.json'):
                result=r.rank_candidates([helper.candidate('A',82),helper.candidate('B',80)],{},count=2,seed='s',request=request,root=root)
                r.persist_trace('e','p',result,model={'revision_id':'before','profiles':{}},root=root)
                entry=finalize_entry(root,'e');trace=load(r.TRACE,{})
                validate_entry(entry,trace)
                self.assertEqual(entry['profile_id'],'p')
                self.assertFalse(any('preference_features' in x or 'samples' in x for x in entry['results']['shortlist']))
                entry['hard_filters']={'must_not':['changed after ranking']}
                with self.assertRaises(ValueError):validate_entry(entry,trace)
                entry['hard_filters']=request['hard_filters']
                entry['results']['shortlist'].reverse()
                with self.assertRaises(ValueError):validate_entry(entry,trace)
        finally:helper.doCleanups()
