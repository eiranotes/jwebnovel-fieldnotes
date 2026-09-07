import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from automation_store import AutomationError,digest
from project_backend import ProjectBackend,parse_envelope


class FakeBridge:
    """Transport fixture only: no claim that the provider created or answered a real chat."""
    def __init__(self):self.workers=[];self.calls=[];self.finish=True;self.lost_reply=False;self.fail_bootstrap_once=False;self.reject_spawn_before_worker_once=False;self.rate_limit_once=False;self.rate_limit_after_send_once=False;self.invalid_json_once=False
    def request(self,route,body=None,method='GET'):
        self.calls.append((route,copy.deepcopy(body)))
        project={'alias':'fieldnotes','name':'Fieldnotes','url':'https://chatgpt.com/g/g-p-test-fieldnotes/project'}
        if route.endswith('/registry'):return {'entries':{'fieldnotes':project}}
        if route.endswith('/status'):return {'workers':copy.deepcopy(self.workers)}
        if route.endswith('/spawn'):
            request=body['workers'][0];target=request['target'];prompt=json.loads(request['task'])
            if self.reject_spawn_before_worker_once:
                self.reject_spawn_before_worker_once=False
                raise AutomationError('spawn_failed')
            if self.fail_bootstrap_once:
                self.fail_bootstrap_once=False
                worker={'id':f'worker-{len(self.workers)+1}','createdAt':1000+len(self.workers),'state':'failed',
                        'revivable':False,'conversationId':None,'complete':False,'answer':None,
                        'projectTarget':{**project,'workId':target['workId'],'role':target['role']}}
                self.workers.append(worker)
                return {'workers':[copy.deepcopy(worker)]}
            if self.rate_limit_once:
                self.rate_limit_once=False
                worker={'id':f'worker-{len(self.workers)+1}','createdAt':1000+len(self.workers),'state':'failed',
                        'revivable':False,'conversationId':None,'complete':False,'answer':None,
                        'brokerResult':'the browser could not start the chat — CHATGPT_CONVERSATION_RATE_LIMITED: Too Many Requests',
                        'projectTarget':{**project,'workId':target['workId'],'role':target['role']}}
                self.workers.append(worker);return {'workers':[copy.deepcopy(worker)]}
            if self.rate_limit_after_send_once:
                self.rate_limit_after_send_once=False
                worker={'id':f'worker-{len(self.workers)+1}','createdAt':1000+len(self.workers),'state':'failed',
                        'revivable':False,'conversationId':None,'complete':False,'answer':None,
                        'brokerResult':'CHATGPT_CONVERSATION_RATE_LIMITED_AFTER_SEND: Too Many Requests',
                        'projectTarget':{**project,'workId':target['workId'],'role':target['role']}}
                self.workers.append(worker);return {'workers':[copy.deepcopy(worker)]}
            worker={'id':f'worker-{len(self.workers)+1}','createdAt':1000+len(self.workers),'state':'sleeping' if self.finish else 'active',
                    'revivable':True,'conversationId':'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee','complete':self.finish,
                    'projectTarget':{**project,'workId':target['workId'],'role':target['role']}}
            worker['last_prompt']=prompt
            worker['answer']=json.dumps({'operation_id':prompt['operation_id'],'work_id':prompt['work_id'],'payload':{'test_result':prompt['task']['number']}})
            if self.invalid_json_once:
                self.invalid_json_once=False
                worker['answer']=worker['answer'][:-1]
            self.workers.append(worker)
            if self.lost_reply:raise AutomationError('BRIDGE_TRANSPORT_UNCERTAIN')
            return {'workers':[copy.deepcopy(worker)]}
        if route.endswith('/message'):
            worker=next(w for w in self.workers if w['id']==body['to'])
            assert body['expectedCreatedAt']==worker['createdAt']
            prompt=json.loads(body['text'])
            if prompt.get('kind')=='fieldnotes_json_repair':
                original=worker['last_prompt']
                worker.update(state='sleeping',complete=True,answer=json.dumps({
                    'operation_id':original['operation_id'],'work_id':original['work_id'],
                    'payload':{'test_result':original['task']['number']},
                }))
                return {'ok':True}
            worker['last_prompt']=prompt
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
    def test_new_work_gets_its_own_project_chat(self):
        b=self.backend()
        self.assertEqual(b.execute('alpha','translator',{'number':1}),{'test_result':1})
        self.assertEqual(b.execute('beta','translator',{'number':2}),{'test_result':2})
        self.assertEqual(len(self.bridge.workers),2)
        self.assertEqual(len([r for r,_ in self.bridge.calls if r.endswith('/spawn')]),2)
        self.assertEqual([w['projectTarget']['workId'] for w in self.bridge.workers],['alpha','beta'])
        self.assertEqual(b.execute('beta','translator',{'number':3}),{'test_result':3})
        self.assertEqual(len(self.bridge.workers),2)
        self.assertEqual(len([r for r,_ in self.bridge.calls if r.endswith('/message')]),1)

    def test_missing_mapping_recovers_only_exact_work_chat(self):
        b=self.backend()
        self.assertEqual(b.execute('alpha','translator',{'number':1}),{'test_result':1})
        mapping=self.root/'workspace/automation-runs/backend/alpha/translator/worker.json'
        mapping.unlink()
        self.assertEqual(b.execute('alpha','translator',{'number':2}),{'test_result':2})
        self.assertEqual(len(self.bridge.workers),1)
        self.assertEqual(len([r for r,_ in self.bridge.calls if r.endswith('/spawn')]),1)
        self.assertEqual(len([r for r,_ in self.bridge.calls if r.endswith('/message')]),1)
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
    def test_identityless_uncertain_with_no_exact_broker_worker_is_safe_to_retry(self):
        self.bridge.reject_spawn_before_worker_once=True;b=self.backend()
        with self.assertRaisesRegex(AutomationError,'spawn_failed'):
            b.execute('example','translator',{'number':11})
        self.assertEqual(self.bridge.workers,[])
        self.assertEqual(b.execute('example','translator',{'number':11}),{'test_result':11})
        self.assertEqual(len(self.bridge.workers),1)
    def test_invalid_json_gets_one_same_worker_repair_turn(self):
        self.bridge.invalid_json_once=True;b=self.backend()
        self.assertEqual(b.execute('example','translator',{'number':12}),{'test_result':12})
        self.assertEqual(len(self.bridge.workers),1)
        messages=[body for route,body in self.bridge.calls if route.endswith('/message')]
        self.assertEqual(len(messages),1)
        repair=json.loads(messages[0]['text'])
        self.assertEqual(repair['kind'],'fieldnotes_json_repair')
        self.assertEqual(repair['work_id'],'example')
    def test_old_answer_rejected(self):
        with self.assertRaisesRegex(AutomationError,'RESULT_OPERATION_MISMATCH'):
            parse_envelope(json.dumps({'operation_id':'old','work_id':'example','payload':{}}),'new','example')
    def test_trailing_unmatched_closing_brace_is_repaired_but_prose_is_rejected(self):
        exact=json.dumps({'operation_id':'operation-123456','work_id':'example','payload':{'ok':True}})
        self.assertEqual(parse_envelope(exact+'}','operation-123456','example'),{'ok':True})
        with self.assertRaisesRegex(AutomationError,'INVALID_MODEL_JSON'):
            parse_envelope(exact+' trailing','operation-123456','example')
    def test_worker_busy_does_not_spawn_another(self):
        b=self.backend();b.execute('example','translator',{'number':1});self.bridge.workers[0]['state']='active'
        with self.assertRaisesRegex(AutomationError,'WORKER_BUSY'):b.execute('example','translator',{'number':2})
        self.assertEqual(len(self.bridge.workers),1)
    def test_unknown_project_never_submits_to_general_chat(self):
        with self.assertRaisesRegex(AutomationError,'PROJECT_TARGET_NOT_VERIFIED'):
            self.backend().execute('example','translator',{'number':1},alias='unknown')
        self.assertEqual(self.bridge.workers,[])
    def test_definitive_presend_worker_bootstrap_failure_can_retry_same_operation(self):
        self.bridge.fail_bootstrap_once=True;b=self.backend()
        with self.assertRaisesRegex(AutomationError,'PROJECT_WORKER_BOOTSTRAP_FAILED'):
            b.execute('example','translator',{'number':1})
        self.assertEqual(len(self.bridge.workers),1)
        self.assertIsNone(self.bridge.workers[0]['conversationId'])
        self.assertEqual(b.execute('example','translator',{'number':1}),{'test_result':1})
        self.assertEqual(len(self.bridge.workers),2)
    def test_presend_chatgpt_rate_limit_stops_now_but_is_retryable_after_cooldown(self):
        self.bridge.rate_limit_once=True;b=self.backend()
        with self.assertRaisesRegex(AutomationError,'CHATGPT_CONVERSATION_RATE_LIMITED'):
            b.execute('example','translator',{'number':8})
        self.assertEqual(b.execute('example','translator',{'number':8}),{'test_result':8})
        self.assertEqual(len(self.bridge.workers),2)

    def test_postsend_chatgpt_rate_limit_is_submission_uncertain(self):
        self.bridge.rate_limit_after_send_once=True;b=self.backend()
        with self.assertRaisesRegex(AutomationError,'CHATGPT_CONVERSATION_RATE_LIMITED'):
            b.execute('example','translator',{'number':9})
        with self.assertRaisesRegex(AutomationError,'OPERATION_SUBMISSION_UNCERTAIN'):
            b.execute('example','translator',{'number':9})
        self.assertEqual(len(self.bridge.workers),1)
    def test_legacy_generic_worker_failure_is_retryable_only_when_exact_worker_never_had_chat(self):
        self.bridge.fail_bootstrap_once=True;b=self.backend()
        with self.assertRaisesRegex(AutomationError,'PROJECT_WORKER_BOOTSTRAP_FAILED'):
            b.execute('example','translator',{'number':7})
        operation=digest({'work':'example','role':'translator','alias':'fieldnotes','payload':{'number':7}})
        state=self.root/'workspace/automation-runs/backend/example/translator'/f'{operation}.json'
        saved=json.loads(state.read_text());saved['error']='PROJECT_WORKER_FAILED';state.write_text(json.dumps(saved))
        self.assertEqual(b.execute('example','translator',{'number':7}),{'test_result':7})
    def test_reused_worker_ignores_previous_sleeping_answer_until_new_operation_finishes(self):
        b=self.backend()
        self.assertEqual(b.execute('example','translator',{'number':1}),{'test_result':1})
        worker=self.bridge.workers[0]
        old_answer=worker['answer']
        original=self.bridge.request
        status_calls=0
        def delayed(route,body=None,method='GET'):
            nonlocal status_calls
            if route.endswith('/message'):
                # Accept the wake, but deliberately leave the previous sleeping answer visible
                # for one status read before publishing the new result.
                prompt=json.loads(body['text'])
                worker['pending_prompt']=prompt
                return {'ok':True}
            if route.endswith('/status') and worker.get('pending_prompt'):
                status_calls+=1
                if status_calls == 1:
                    self.assertEqual(worker['answer'],old_answer)
                    return {'workers':copy.deepcopy(self.bridge.workers)}
                prompt=worker.pop('pending_prompt')
                worker.update(state='sleeping',complete=True,answer=json.dumps({'operation_id':prompt['operation_id'],'work_id':prompt['work_id'],'payload':{'test_result':prompt['task']['number']}}))
                return {'workers':copy.deepcopy(self.bridge.workers)}
            return original(route,body,method)
        self.bridge.request=delayed
        self.assertEqual(b.execute('example','translator',{'number':2}),{'test_result':2})
        self.assertGreaterEqual(status_calls,2)
    def test_translate_task_allows_only_exact_hash_validated_core_read(self):
        path=self.root/'workspace/books/example/translation/tasks/0001.json';path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'work_id':'example','chunk_id':'0001','local_source_probe':'0123456789abcdef0123456789abcdef','source_ja':'private fixture'})+'\n',encoding='utf-8')
        payload={'number':1,'kind':'translate_chunk','chunk_id':'0001','local_source_task':{'path':str(path.resolve()),'sha256':digest(path.read_bytes())}}
        self.assertEqual(self.backend().execute('example','translator',payload),{'test_result':1})
        spawn=next(body for route,body in self.bridge.calls if route.endswith('/spawn'))
        prompt=json.loads(spawn['workers'][0]['task'])
        self.assertIn('Chat On Steroids Core `read`',prompt['instructions'])
        self.assertIn('Do not read any other local path',prompt['instructions'])
        self.assertIn('exec, apply_patch, write_stdin, or agents',prompt['instructions'])
        self.assertEqual(prompt['task']['local_source_task']['path'],str(path.resolve()))
    def test_translate_task_rejects_outside_or_changed_local_reference_before_spawn(self):
        outside=self.root/'outside.json';outside.write_text('{}')
        with self.assertRaisesRegex(AutomationError,'LOCAL_SOURCE_REFERENCE_INVALID'):
            self.backend().execute('example','translator',{'kind':'translate_chunk','local_source_task':{'path':str(outside.resolve()),'sha256':digest(outside.read_bytes())}})
        path=self.root/'workspace/books/example/translation/tasks/0001.json';path.parent.mkdir(parents=True);path.write_text(json.dumps({'work_id':'example','chunk_id':'0001','local_source_probe':'0123456789abcdef0123456789abcdef'}))
        with self.assertRaisesRegex(AutomationError,'LOCAL_SOURCE_CHANGED'):
            self.backend().execute('example','translator',{'kind':'translate_chunk','chunk_id':'0001','local_source_task':{'path':str(path.resolve()),'sha256':'0'*64}})
        self.assertEqual(self.bridge.workers,[])
