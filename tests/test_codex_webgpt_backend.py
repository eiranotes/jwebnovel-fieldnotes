import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from automation_store import AutomationError,digest,read_json
from codex_webgpt_backend import CodexWebGptBackend


class FakeRunner:
    def __init__(self, *, fail_oracle=False):
        self.calls=[];self.fail_oracle=fail_oracle
    def __call__(self,args,**kwargs):
        self.calls.append(list(args))
        if Path(args[0]).name == 'codex':
            out=Path(args[args.index('-o')+1]);out.parent.mkdir(parents=True,exist_ok=True)
            out.write_text('Preserve every sentence id and return JSON only.',encoding='utf-8')
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        out=Path(args[args.index('--write-output')+1])
        if self.fail_oracle:return SimpleNamespace(returncode=1,stdout='',stderr='browser failed after launch')
        prompt=args[args.index('-p')+1]
        operation=prompt.split('"operation_id":"',1)[1].split('"',1)[0]
        work=prompt.split('"work_id":"',1)[1].split('"',1)[0]
        task=read_json(Path(args[args.index('--file')+1]))
        result={'operation_id':operation,'work_id':work,'payload':{
            'local_source_proof':task['local_source_probe'],
            'segment_translations':[{'id':'s000001','ko':'바람이 분다.'}],
            'glossary_update':{}}}
        out.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        return SimpleNamespace(returncode=0,stdout='',stderr='')


class CodexWebGptBackendTests(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory();root=Path(temp.name).resolve()
        path=root/'workspace/books/example/translation/tasks/0001.json';path.parent.mkdir(parents=True)
        task={'work_id':'example','chunk_id':'0001','local_source_probe':'0123456789abcdef0123456789abcdef',
              'source_segments':[{'id':'s000001','kind':'sentence','ja':'風が吹く。'}]}
        path.write_text(json.dumps(task,ensure_ascii=False),encoding='utf-8')
        payload={'kind':'translate_chunk','work_id':'example','chunk_id':'0001',
                 'local_source_task':{'path':str(path),'sha256':digest(path.read_bytes())}}
        return temp,root,payload

    def test_codex_plans_and_oracle_webgpt_returns_contract(self):
        temp,root,payload=self.fixture();runner=FakeRunner()
        try:
            backend=CodexWebGptBackend(root,runner=runner,codex_command='/usr/bin/codex',oracle_command='/usr/bin/oracle',chrome_profile_root=root)
            result=backend.execute('example',payload,operation_id='fallback-operation-0001')
            self.assertEqual(result['local_source_proof'],'0123456789abcdef0123456789abcdef')
            self.assertEqual(result['segment_translations'][0]['ko'],'바람이 분다.')
            self.assertEqual([Path(call[0]).name for call in runner.calls],['codex','oracle'])
            self.assertIn('--sandbox',runner.calls[0]);self.assertIn('read-only',runner.calls[0])
            self.assertIn('--engine',runner.calls[1]);self.assertIn('browser',runner.calls[1])
            self.assertIn('--copy-profile',runner.calls[1])
            self.assertEqual(runner.calls[1][runner.calls[1].index('--chatgpt-url')+1],'https://chatgpt.com/')
            self.assertIn('--file',runner.calls[1])
        finally:temp.cleanup()

    def test_oracle_failure_is_uncertain_and_never_auto_resubmitted(self):
        temp,root,payload=self.fixture();runner=FakeRunner(fail_oracle=True)
        try:
            backend=CodexWebGptBackend(root,runner=runner,codex_command='/usr/bin/codex',oracle_command='/usr/bin/oracle',chrome_profile_root=root)
            with self.assertRaisesRegex(AutomationError,'FALLBACK_SUBMISSION_UNCERTAIN'):
                backend.execute('example',payload,operation_id='fallback-operation-0002')
            before=len(runner.calls)
            with self.assertRaisesRegex(AutomationError,'FALLBACK_SUBMISSION_UNCERTAIN'):
                backend.execute('example',payload,operation_id='fallback-operation-0002')
            self.assertEqual(len(runner.calls),before)
        finally:temp.cleanup()
