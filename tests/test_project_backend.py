import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from automation_store import AutomationError
from project_backend import ProjectBackend,parse_envelope


class FakeBridge:
    """Transport fixture only: no claim that the provider created or answered a real chat."""
    def __init__(self):self.workers=[];self.calls=[];self.finish=True;self.lost_reply=False
    def request(self,route,body=None,method='GET'):
        self.calls.append((route,copy.deepcopy(body)))
        project={'alias':'fieldnotes','name':'Fieldnotes','url':'https://chatgpt.com/g/g-p-test-fieldnotes/project'}
        if route.endswith('/registry'):return {'entries':{'fieldnotes':project}}
        if route.endswith('/status'):return {'workers':copy.deepcopy(self.workers)}
        if route.endswith('/spawn'):
            request=body['workers'][0];target=request['target'];prompt=json.loads(request['task'])
            worker={'id':f'worker-{len(self.workers)+1}','createdAt':1000+len(self.workers),'state':'sleeping' if self.finish else 'active',
                    'revivable':True,'conversationId':'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee','complete':self.finish,
                    'projectTarget':{**project,'workId':target['workId'],'role':target['role']}}
            worker['answer']=json.dumps({'operation_id':prompt['operation_id'],'work_id':prompt['work_id'],'payload':{'test_result':prompt['task']['number']}})
            self.workers.append(worker)
            if self.lost_reply:raise AutomationError('BRIDGE_TRANSPORT_UNCERTAIN')
            return {'workers':[copy.deepcopy(worker)]}
        if route.endswith('/message'):
            worker=next(w for w in self.workers if w['id']==body['to'])
            assert body['expectedCreatedAt']==worker['createdAt']
            prompt=json.loads(body['text'])
            worker.update(state='sleeping',complete=True,answer=json.dumps({'operation_id':prompt['operation_id'],'work_id':prompt['work_id'],'payload':{'test_result':prompt['task']['number']}}))
            return {'ok':True}
        raise AssertionError(route)


class BackendTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.bridge=FakeBridge()
    def tearDown(self):self.tmp.cleanup()
    def backend(self,**kwargs):return ProjectBackend(self.root,bridge=self.bridge,poll_interval=0.001,**kwargs)
    def test_two_operations_reuse_exact_project_worker(self):
        b=self.backend()
        self.assertEqual(b.execute('example','translator',{'number':1}),{'test_result':1})
        self.assertEqual(b.execute('example','translator',{'number':2}),{'test_result':2})
        self.assertEqual(len(self.bridge.workers),1)
        self.assertEqual(len([r for r,b in self.bridge.calls if r.endswith('/message')]),1)
        self.assertEqual(b.execute('example','translator',{'number':2}),{'test_result':2})
        self.assertEqual(len([r for r,b in self.bridge.calls if r.endswith('/message')]),1)
    def test_timeout_resumes_result_wait_without_repeating_submit(self):
        self.bridge.finish=False;b=self.backend(timeout=0.003)
        with self.assertRaisesRegex(AutomationError,'WORKER_RESULT_TIMEOUT'):b.execute('example','translator',{'number':1})
        self.bridge.workers[0].update(state='sleeping',complete=True)
        self.assertEqual(self.backend().execute('example','translator',{'number':1}),{'test_result':1})
        self.assertEqual(len(self.bridge.workers),1)
    def test_lost_spawn_response_never_auto_retries(self):
        self.bridge.lost_reply=True;b=self.backend()
        with self.assertRaises(AutomationError):b.execute('example','translator',{'number':1})
        with self.assertRaisesRegex(AutomationError,'OPERATION_SUBMISSION_UNCERTAIN'):b.execute('example','translator',{'number':1})
        self.assertEqual(len(self.bridge.workers),1)
    def test_old_answer_rejected(self):
        with self.assertRaisesRegex(AutomationError,'RESULT_OPERATION_MISMATCH'):
            parse_envelope(json.dumps({'operation_id':'old','work_id':'example','payload':{}}),'new','example')
    def test_worker_busy_does_not_spawn_another(self):
        b=self.backend();b.execute('example','translator',{'number':1});self.bridge.workers[0]['state']='active'
        with self.assertRaisesRegex(AutomationError,'WORKER_BUSY'):b.execute('example','translator',{'number':2})
        self.assertEqual(len(self.bridge.workers),1)
    def test_unknown_project_never_submits_to_general_chat(self):
        with self.assertRaisesRegex(AutomationError,'PROJECT_TARGET_NOT_VERIFIED'):
            self.backend().execute('example','translator',{'number':1},alias='unknown')
        self.assertEqual(self.bridge.workers,[])
