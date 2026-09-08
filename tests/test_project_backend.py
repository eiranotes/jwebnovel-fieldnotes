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
    def __init__(self):self.workers=[];self.calls=[];self.finish=True;self.lost_reply=False;self.fail_bootstrap_once=False;self.reject_spawn_before_worker_once=False;self.rate_limit_once=False;self.rate_limit_after_send_once=False;self.uncertain_after_send_once=False;self.invalid_json_once=False
    def publish(self,worker,prompt):
        task=prompt['task']
        worker['answer']=json.dumps({'operation_id':prompt['operation_id'],'work_id':prompt['work_id'],'payload':{'test_result':task['number']}})
    def request(self,route,body=None,method='GET'):
        self.calls.append((route,copy.deepcopy(body)))
        project={'alias':'fieldnotes','name':'Fieldnotes','url':'https://chatgpt.com/g/g-p-test-fieldnotes/project'}
        if route.endswith('/registry'):return {'entries':{'fieldnotes':project}}
        if route.endswith('/status'):return {'workers':copy.deepcopy(self.workers)}
        if route.endswith('/control'):
            assert body['action']=='interrupt'
            worker=next(w for w in self.workers if w['id']==body['workerId'])
            assert body['expectedCreatedAt']==worker['createdAt']
            worker.update(state='sleeping',revivable=True,complete=True)
            return {'ok':True,'action':'interrupt','workerId':worker['id'],'conversationId':worker.get('conversationId'),'remoteStopped':True}
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
            if self.uncertain_after_send_once:
                self.uncertain_after_send_once=False
                worker={'id':f'worker-{len(self.workers)+1}','createdAt':1000+len(self.workers),'state':'failed',
                        'revivable':False,'conversationId':None,'complete':False,'answer':None,
                        'brokerResult':'CHATGPT_BOOTSTRAP_SUBMISSION_UNCERTAIN_AFTER_SEND: send clicked; no provider evidence yet',
                        'projectTarget':{**project,'workId':target['workId'],'role':target['role']}}
                self.workers.append(worker);return {'workers':[copy.deepcopy(worker)]}
            worker={'id':f'worker-{len(self.workers)+1}','createdAt':1000+len(self.workers),'state':'sleeping' if self.finish else 'active',
                    'revivable':True,'conversationId':'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee','complete':self.finish,
                    'projectTarget':{**project,'workId':target['workId'],'role':target['role']}}
            worker['last_prompt']=prompt
            self.publish(worker,prompt)
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
            worker.update(state='sleeping',complete=True)
            self.publish(worker,prompt)
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

    def test_long_conversation_title_is_shortened_only_for_broker_label(self):
        b=self.backend()
        title='260908-' + ('長い作品タイトル' * 12)
        self.assertEqual(b.execute('example','translator',{'number':1,'conversation_title':title}),{'test_result':1})
        spawn=next(body for route,body in self.bridge.calls if route.endswith('/spawn'))
        label=spawn['workers'][0]['label']
        prompt=json.loads(spawn['workers'][0]['task'])
        self.assertLessEqual(len(label),60)
        self.assertTrue(label.endswith('…'))
        self.assertEqual(prompt['task']['conversation_title'],title)

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
    def test_timeout_can_retry_same_chat_only_after_confirmed_remote_interrupt(self):
        self.bridge.finish=False;b=self.backend(timeout=0.003);payload={'number':13}
        operation=digest({'work':'example','role':'translator','alias':'fieldnotes','payload':payload})
        with self.assertRaisesRegex(AutomationError,'WORKER_RESULT_TIMEOUT'):
            b.execute('example','translator',payload)
        self.bridge.workers[0]['answer']=None
        interrupted=b.mark_remote_interrupted('example','translator',operation,'interrupt-example-0001')
        self.assertEqual(interrupted['state'],'interrupted')
        self.assertEqual(interrupted['last_error'],'REMOTE_INTERRUPT_CONFIRMED')
        self.assertEqual(self.backend().execute('example','translator',payload),{'test_result':13})
        self.assertEqual(len(self.bridge.workers),1)
        self.assertEqual(len([1 for route,_ in self.bridge.calls if route.endswith('/message')]),1)
        final=json.loads((self.root/'workspace/automation-runs/backend/example/translator'/f'{operation}.json').read_text())
        self.assertEqual(final['state'],'complete')
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
    def test_fresh_bootstrap_click_without_provider_evidence_is_never_resubmitted(self):
        self.bridge.uncertain_after_send_once=True;b=self.backend()
        with self.assertRaisesRegex(AutomationError,'OPERATION_SUBMISSION_UNCERTAIN'):
            b.execute('example','translator',{'number':10})
        with self.assertRaisesRegex(AutomationError,'OPERATION_SUBMISSION_UNCERTAIN'):
            b.execute('example','translator',{'number':10})
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
        self.assertIn('do not use any local write capability',prompt['instructions'])
        self.assertIn('trusted local driver will create a new operation-specific result file',prompt['instructions'])
        self.assertIn('create_file, apply_patch, exec_command, write_stdin, or agents',prompt['instructions'])
        self.assertEqual(prompt['task']['local_source_task']['path'],str(path.resolve()))
        self.assertNotIn('local_result',prompt['task'])
        self.assertIn('payload',prompt['response_contract'])
        self.assertEqual(json.loads(self.bridge.workers[0]['answer'])['operation_id'],prompt['operation_id'])
        operation=prompt['operation_id']
        state=json.loads((self.root/'workspace/automation-runs/backend/example/translator'/f'{operation}.json').read_text())
        self.assertEqual(state['result_source'],'driver_capture')
        captured=self.root/'workspace/automation-runs/backend/example/translator'/state['result_receipt_file']
        self.assertTrue(captured.exists())
        envelope=json.loads(captured.read_text())
        self.assertEqual(envelope['operation_id'],operation)
        self.assertEqual(envelope['payload'],{'test_result':1})

    def test_complete_answer_can_be_recovered_before_worker_parks(self):
        b=self.backend()
        self.bridge.finish=False
        # Spawn returns active, then emulate recorder proving a final assistant answer while
        # the broker has not yet swept the worker into sleeping state.
        original=self.bridge.request
        calls={'status':0}
        def request(route,body=None,method='GET'):
            if route.endswith('/status'):
                calls['status']+=1
                if self.bridge.workers:
                    w=self.bridge.workers[0]
                    w['complete']=True
                    w['answer']=json.dumps({'operation_id':'fixed-operation-1234','work_id':'example','payload':{'test_result':8}})
                return {'workers':self.bridge.workers}
            return original(route,body,method)
        self.bridge.request=request
        out=b.execute('example','translator',{'number':8},operation_id='fixed-operation-1234')
        self.assertEqual(out,{'test_result':8})
        self.assertEqual(self.bridge.workers[0]['state'],'active')

    def test_existing_result_receipt_is_authoritative_recovery_input(self):
        path=self.root/'workspace/books/example/translation/tasks/0001.json';path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'work_id':'example','chunk_id':'0001','local_source_probe':'0123456789abcdef0123456789abcdef','source_ja':'private fixture'})+'\n',encoding='utf-8')
        payload={'number':4,'kind':'translate_chunk','chunk_id':'0001','local_source_task':{'path':str(path.resolve()),'sha256':digest(path.read_bytes())}}
        operation=digest({'work':'example','role':'translator','alias':'fieldnotes','payload':payload})
        direct=self.root/'workspace/automation-runs/backend/example/translator'/f'{operation}.worker-result.json'
        direct.parent.mkdir(parents=True,exist_ok=True)
        direct.write_text(json.dumps({'operation_id':operation,'work_id':'example','payload':{'test_result':4}})+'\n',encoding='utf-8')
        result=self.backend().execute('example','translator',payload)
        self.assertEqual(result,{'test_result':4})
        state=json.loads((self.root/'workspace/automation-runs/backend/example/translator'/f'{operation}.json').read_text())
        self.assertEqual(state['result_source'],'result_receipt_recovery')
        self.assertTrue((self.root/'workspace/automation-runs/backend/example/translator'/state['result_receipt_file']).exists())

    def test_driver_capture_is_create_only_and_refuses_conflicting_existing_result(self):
        path=self.root/'workspace/books/example/translation/tasks/0001.json';path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'work_id':'example','chunk_id':'0001','local_source_probe':'0123456789abcdef0123456789abcdef','source_ja':'private fixture'})+'\n',encoding='utf-8')
        payload={'number':5,'kind':'translate_chunk','chunk_id':'0001','local_source_task':{'path':str(path.resolve()),'sha256':digest(path.read_bytes())}}
        operation=digest({'work':'example','role':'translator','alias':'fieldnotes','payload':payload})
        direct=self.root/'workspace/automation-runs/backend/example/translator'/f'{operation}.worker-result.json'
        direct.parent.mkdir(parents=True,exist_ok=True)
        direct.write_text(json.dumps({'operation_id':operation,'work_id':'example','payload':{'test_result':999}})+'\n',encoding='utf-8')
        # An existing valid envelope is authoritative recovery input. It is never overwritten
        # by a later model response for the same operation.
        self.assertEqual(self.backend().execute('example','translator',payload),{'test_result':999})
        self.assertEqual(json.loads(direct.read_text())['payload'],{'test_result':999})

    def test_reused_translation_ignores_previous_chat_answer_before_result_receipt_check(self):
        task_path=self.root/'workspace/books/example/translation/tasks/0001.json';task_path.parent.mkdir(parents=True)
        task_path.write_text(json.dumps({'work_id':'example','chunk_id':'0001','local_source_probe':'0123456789abcdef0123456789abcdef','source_ja':'private fixture'})+'\n',encoding='utf-8')
        first={'number':1,'kind':'translate_chunk','chunk_id':'0001','local_source_task':{'path':str(task_path.resolve()),'sha256':digest(task_path.read_bytes())}}
        self.backend().execute('example','translator',first)
        # Remove the direct result so the second operation cannot accidentally succeed from it.
        op1=digest({'work':'example','role':'translator','alias':'fieldnotes','payload':first})
        (self.root/'workspace/automation-runs/backend/example/translator'/f'{op1}.worker-result.json').unlink()
        task_path2=self.root/'workspace/books/example/translation/tasks/0002.json'
        task_path2.write_text(json.dumps({'work_id':'example','chunk_id':'0002','local_source_probe':'0123456789abcdef0123456789abcdef','source_ja':'private fixture 2'})+'\n',encoding='utf-8')
        second={'number':2,'kind':'translate_chunk','chunk_id':'0002','local_source_task':{'path':str(task_path2.resolve()),'sha256':digest(task_path2.read_bytes())}}
        out=self.backend().execute('example','translator',second)
        self.assertEqual(out,{'test_result':2})
    def test_translate_task_rejects_outside_or_changed_local_reference_before_spawn(self):
        outside=self.root/'outside.json';outside.write_text('{}')
        with self.assertRaisesRegex(AutomationError,'LOCAL_SOURCE_REFERENCE_INVALID'):
            self.backend().execute('example','translator',{'kind':'translate_chunk','local_source_task':{'path':str(outside.resolve()),'sha256':digest(outside.read_bytes())}})
        path=self.root/'workspace/books/example/translation/tasks/0001.json';path.parent.mkdir(parents=True);path.write_text(json.dumps({'work_id':'example','chunk_id':'0001','local_source_probe':'0123456789abcdef0123456789abcdef'}))
        with self.assertRaisesRegex(AutomationError,'LOCAL_SOURCE_CHANGED'):
            self.backend().execute('example','translator',{'kind':'translate_chunk','chunk_id':'0001','local_source_task':{'path':str(path.resolve()),'sha256':'0'*64}})
        self.assertEqual(self.bridge.workers,[])
