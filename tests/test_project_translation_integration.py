"""Local integration fixture. Model/Project retrieval is simulated, never a live E2E claim."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import source_pipeline as source
import project_context as context
import translate_project as driver
from automation_store import atomic_json,read_json


class FixtureModel:
    def __init__(self,root,sequence=None,probe_unavailable=0):self.root=root;self.calls=[];self.sequence=sequence;self.probe_unavailable=probe_unavailable;self.translation_payloads=[]
    def execute(self,work_id,role,payload,**kwargs):
        self.calls.append(payload['kind'])
        if self.sequence is not None:self.sequence.append(payload['kind'])
        if payload['kind']=='project_source_probe':
            if self.probe_unavailable:
                self.probe_unavailable-=1
                return {'status':'source_unavailable','work_id':work_id,'sources':[]}
            packs=[]
            for descriptor in payload['sources']:
                manifest=read_json(self.root/'workspace/project-context'/descriptor['source_name']/'current.json')
                packs.append({'filename':manifest['filename'],'source_probe':manifest['source_probe']})
            return {'status':'ready','work_id':work_id,'sources':packs}
        self.translation_payloads.append(payload)
        assert 'source_ja' not in payload
        assert 'source_segments' not in payload
        local_task=read_json(Path(payload['local_source_task']['path']))
        proof={'status':'ready','work_id':work_id,'sources':[]}
        for descriptor in payload['project_sources']:
            manifest=read_json(self.root/'workspace/project-context'/descriptor['source_name']/'current.json')
            proof['sources'].append({'filename':manifest['filename'],'source_probe':manifest['source_probe']})
        return {'project_source_proof':proof,'local_source_proof':local_task['local_source_probe'],'segment_translations':[{'id':s['id'],'ko':{'風が吹く。':'바람이 분다.','雨が降る。':'비가 내린다.'}[s['ja']]} for s in local_task['source_segments'] if s['kind']=='sentence'],'glossary_update':{}}


class ProjectTranslationIntegration(unittest.TestCase):
    def test_two_chunks_commit_parallel_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();work=root/'workspace/2026-09-07/test/example';work.mkdir(parents=True)
            actual=Path(__file__).resolve().parents[1]
            for name in ('PROJECT_INSTRUCTIONS.md','GLOBAL_CONTEXT.md'):
                destination=root/'templates/project-context'/name;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_text((actual/'templates/project-context'/name).read_text())
            atomic_json(root/'config/project-translation.json',read_json(actual/'config/project-translation.json'))
            atomic_json(work/'metadata.json',{'work_id':'example','entry_id':'test','title':'Fixture'})
            atomic_json(work/'glossary.json',{'people':{},'decisions':[]})
            atomic_json(work/'state.json',{'status':'translation_pending'})
            chunks=[]
            for index,ja in enumerate(('風が吹く。\n','雨が降る。\n'),1):
                cid=f'{index:04d}';d=work/'translation/chunks'/cid;d.mkdir(parents=True);(d/'ja.txt').write_text(ja)
                meta={'chunk_id':cid,'order':index,'status':'pending'};atomic_json(d/'meta.json',meta);chunks.append(meta)
            atomic_json(work/'translation/manifest.json',{'chunk_count':2,'chunks':chunks})
            def complete(script,args):
                self.assertEqual(script,'translation_queue.py')
                cid=args[args.index('--chunk')+1];result=read_json(Path(args[args.index('--result')+1]))
                outcome=source.complete_chunk(work,cid,result)
                ns=SimpleNamespace(work_dir=str(work),entry='test',work='example')
                with contextlib.redirect_stdout(io.StringIO()):
                    source.build_parallel(ns)
                    if outcome['done']==outcome['total']:source.build_output(ns)
                return outcome
            sequence=[]
            backend=FixtureModel(root,sequence)
            def sync(packs,**kwargs):
                sequence.append('source_sync')
                self.assertEqual([p['source_name'] for p in packs],['GLOBAL_CONTEXT','WORK_example'])
                self.assertEqual(kwargs['root'],root)
                self.assertEqual(kwargs['alias'],'fieldnotes')
                self.assertIs(kwargs['instructions'],True)
                return {'state':'complete'}
            with patch.object(driver,'ROOT',root),patch.object(source,'ROOT',root),patch.object(driver,'build_common',side_effect=lambda:context.build_common(root)),patch.object(driver,'build_work',side_effect=lambda w:context.build_work(w,root)),patch.object(driver,'script_json',side_effect=complete):
                for _ in range(2):
                    capture=io.StringIO()
                    with contextlib.redirect_stdout(capture):
                        source.next_task(SimpleNamespace(work_dir=str(work),entry='test',work='example',context_tail=700,context_head=500))
                    task=read_json(Path(capture.getvalue().strip()))
                    outcome=driver.process_task(task,backend=backend,source_sync=sync)
                    self.assertEqual(outcome['backend'],'webgpt_project')
            self.assertEqual(backend.calls,['project_source_probe','translate_chunk','project_source_probe','translate_chunk'])
            self.assertEqual(sequence,['source_sync','project_source_probe','translate_chunk','source_sync','project_source_probe','translate_chunk'])
            self.assertEqual(len(backend.translation_payloads),2)
            for payload in backend.translation_payloads:
                self.assertTrue(Path(payload['local_source_task']['path']).is_absolute())
                serialized=json.dumps(payload,ensure_ascii=False)
                self.assertNotIn('風が吹く。',serialized)
                self.assertNotIn('雨が降る。',serialized)
                self.assertNotIn('source_segments',payload)
            self.assertEqual(read_json(work/'state.json')['chunks_done'],2)
            self.assertTrue((work/'translation/parallel/index.html').exists())
            self.assertTrue((work/'translation/output/example-translation.zip').exists())
            text=(work/'translation/output/ja-ko-alternating.txt').read_text()
            self.assertIn('원문: 風が吹く。\n번역: 바람이 분다.',text)
            self.assertIn('원문: 雨が降る。\n번역: 비가 내린다.',text)

    def test_guide_revision_changes_when_glossary_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();work=root/'workspace/books/example';work.mkdir(parents=True)
            templates=root/'templates/project-context';templates.mkdir(parents=True)
            for name in ('PROJECT_INSTRUCTIONS.md','GLOBAL_CONTEXT.md'):
                (templates/name).write_text(name)
            atomic_json(work/'metadata.json',{'work_id':'example','title':'Fixture'})
            atomic_json(work/'glossary.json',{'people':{}})
            with patch.object(driver,'ROOT',root):
                before=driver.guide_revision(work)
                atomic_json(work/'glossary.json',{'people':{'紅':'쿠레나이'}})
                after=driver.guide_revision(work)
            self.assertNotEqual(before,after)

    def test_source_probe_retries_only_explicit_unavailable_with_new_attempt_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();work=root/'workspace/books/example';work.mkdir(parents=True)
            actual=Path(__file__).resolve().parents[1]
            for name in ('PROJECT_INSTRUCTIONS.md','GLOBAL_CONTEXT.md'):
                destination=root/'templates/project-context'/name;destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_text((actual/'templates/project-context'/name).read_text())
            atomic_json(work/'metadata.json',{'work_id':'example','title':'Fixture'})
            atomic_json(work/'glossary.json',{'people':{}})
            common=context.build_common(root);pack=context.build_work(work,root)
            backend=FixtureModel(root,probe_unavailable=2)
            ids=[]
            original=backend.execute
            def execute(*args,**kwargs):
                ids.append(kwargs.get('operation_id'))
                return original(*args,**kwargs)
            backend.execute=execute
            with patch.object(driver.time,'sleep') as sleep:
                proof=driver.prove_project_sources(backend,'example','0001',common,pack,alias='fieldnotes',max_attempts=3,retry_seconds=7)
            self.assertEqual(proof['work_id'],'example')
            self.assertEqual(len(set(ids)),3)
            self.assertEqual(sleep.call_count,2)
            sleep.assert_called_with(7)
