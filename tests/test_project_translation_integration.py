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
    def __init__(self,root):self.root=root;self.calls=[]
    def execute(self,work_id,role,payload,**kwargs):
        self.calls.append(payload['kind'])
        if payload['kind']=='project_source_probe':
            packs=[]
            for descriptor in payload['sources']:
                manifest=read_json(self.root/'workspace/project-context'/descriptor['source_name']/'current.json')
                packs.append({'filename':manifest['filename'],'source_probe':manifest['source_probe']})
            return {'status':'ready','work_id':work_id,'sources':packs}
        proof={'status':'ready','work_id':work_id,'sources':[]}
        for descriptor in payload['project_sources']:
            manifest=read_json(self.root/'workspace/project-context'/descriptor['source_name']/'current.json')
            proof['sources'].append({'filename':manifest['filename'],'source_probe':manifest['source_probe']})
        return {'project_source_proof':proof,'segment_translations':[{'id':s['id'],'ko':{'風が吹く。':'바람이 분다.','雨が降る。':'비가 내린다.'}[s['ja']]} for s in payload['source_segments'] if s['kind']=='sentence'],'glossary_update':{}}


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
            backend=FixtureModel(root)
            with patch.object(driver,'ROOT',root),patch.object(source,'ROOT',root),patch.object(driver,'build_common',side_effect=lambda:context.build_common(root)),patch.object(driver,'build_work',side_effect=lambda w:context.build_work(w,root)),patch.object(driver,'script_json',side_effect=complete):
                for _ in range(2):
                    capture=io.StringIO()
                    with contextlib.redirect_stdout(capture):
                        source.next_task(SimpleNamespace(work_dir=str(work),entry='test',work='example',context_tail=700,context_head=500))
                    task=read_json(Path(capture.getvalue().strip()))
                    outcome=driver.process_task(task,backend=backend)
                    self.assertEqual(outcome['backend'],'webgpt_project')
            self.assertEqual(backend.calls,['project_source_probe','translate_chunk','project_source_probe','translate_chunk'])
            self.assertEqual(read_json(work/'state.json')['chunks_done'],2)
            self.assertTrue((work/'translation/parallel/index.html').exists())
            self.assertTrue((work/'translation/output/example-translation.zip').exists())
            text=(work/'translation/output/ja-ko-alternating.txt').read_text()
            self.assertIn('원문: 風が吹く。\n번역: 바람이 분다.',text)
            self.assertIn('원문: 雨が降る。\n번역: 비가 내린다.',text)
