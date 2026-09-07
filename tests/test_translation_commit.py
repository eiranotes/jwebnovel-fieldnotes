import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import source_pipeline as pipeline
from automation_store import AutomationError, atomic_json, read_json


class CommitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.work=Path(self.tmp.name)/'example';self.work.mkdir()
        atomic_json(self.work/'metadata.json',{'work_id':'example'})
        atomic_json(self.work/'glossary.json',{'people':{'A':'에이'},'decisions':[]})
        atomic_json(self.work/'state.json',{'status':'translation_pending'})
        self.ja='「こんにちは。」\n風が吹く。\n';self.segments=pipeline.sentence_segments(self.ja)
        self.result={'work_id':'example','chunk_id':'0001','segment_translations':[{'id':s['id'],'ko':f'번역 {i}'} for i,s in enumerate(self.segments)],'glossary_update':{'decisions':[{'type':'fixture'}]}}
        cdir=self.work/'translation/chunks/0001';cdir.mkdir(parents=True);(cdir/'ja.txt').write_text(self.ja)
        meta={'chunk_id':'0001','status':'pending','order':1}
        atomic_json(cdir/'meta.json',meta);atomic_json(self.work/'translation/manifest.json',{'chunk_count':1,'chunks':[meta]})
    def tearDown(self):self.tmp.cleanup()
    def test_duplicate_reordered_empty_and_extra_segments_rejected(self):
        a=self.result['segment_translations'];bad=[a+a[:1],list(reversed(a)),[a[0],a[0]],[{**a[0],'ko':''},a[1]],None]
        for rows in bad:
            with self.subTest(rows=rows),self.assertRaises(AutomationError):pipeline.validate_segment_translations(self.segments,rows)
    def test_repeat_completion_has_no_duplicate_glossary_decisions(self):
        first=pipeline.complete_chunk(self.work,'0001',self.result)
        second=pipeline.complete_chunk(self.work,'0001',self.result)
        self.assertEqual(first['done'],1);self.assertTrue(second['repeated'])
        self.assertEqual(len(read_json(self.work/'glossary.json')['decisions']),1)
    def test_conflicting_glossary_does_not_write_translation(self):
        self.result['glossary_update']['people']={'A':'다른표기'}
        with self.assertRaisesRegex(AutomationError,'GLOSSARY_CONFLICT'):pipeline.complete_chunk(self.work,'0001',self.result)
        self.assertFalse((self.work/'translation/chunks/0001/ko.txt').exists())
    def test_interrupted_commit_replays_prepared_artifacts(self):
        real=pipeline.atomic_json;failed=False
        def fail_once(path,value,*args,**kwargs):
            nonlocal failed
            real(path,value,*args,**kwargs)
            if path.name=='glossary.json' and not failed:
                failed=True;raise OSError('simulated process loss after glossary replace')
        with patch.object(pipeline,'atomic_json',side_effect=fail_once),self.assertRaises(OSError):pipeline.complete_chunk(self.work,'0001',self.result)
        self.assertEqual(read_json(self.work/'translation/commits/0001.json')['state'],'prepared')
        self.assertEqual(pipeline.complete_chunk(self.work,'0001',self.result)['done'],1)
        self.assertEqual(len(read_json(self.work/'glossary.json')['decisions']),1)
    def test_changed_result_cannot_overwrite_completed_chunk(self):
        pipeline.complete_chunk(self.work,'0001',self.result)
        changed=copy.deepcopy(self.result);changed['segment_translations'][0]['ko']='changed'
        with self.assertRaises(AutomationError):pipeline.complete_chunk(self.work,'0001',changed)
