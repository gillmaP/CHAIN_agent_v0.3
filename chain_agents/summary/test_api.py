"""Synthetic HTTP integration tests; no LLM download or GPU required."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

from .api_service import Application,DemoExtractor,make_server,Store,encode,storage_root
from .api_adapter import HTTPDataAPI,DataAPIError
from .history_s1_cases import cases
from .mock_contract import FixtureDataAPI,endpoint
from .input_audit import digest


class APITests(unittest.TestCase):
    def setUp(self):
        parent=Path('/data/data2/jhbak/CHAIN_agent_summary_prototype/outputs/api_tests')
        # Server artifacts stay on data2; CI/developer machines need no privileged /data mount.
        self.tmp=tempfile.TemporaryDirectory(dir=parent if parent.exists() else None)
        self.root_patch=patch('chain_agents.summary.api_service.storage_root',lambda p:Path(p).resolve())
        self.root_patch.start()
        self.cases=cases()
        self.request=copy.deepcopy(self.cases[0]['request'])
        self.request['trigger']={'state_enter':'S1'}
        self.responses={k:v for c in self.cases for k,v in c['api_responses'].items()}
        self.app=Application(self.tmp.name,lambda:FixtureDataAPI(self.responses),DemoExtractor(self.cases),timeout=2,demo_cases=self.cases)
        self.server=make_server(self.app,port=0,api_token='test-token',cors_origin='http://localhost:3000')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.app.close();self.tmp.cleanup();self.root_patch.stop()

    def call(self,path,body=None,headers=None,method=None):
        h={'Authorization':'Bearer test-token','Content-Type':'application/json'}
        h.update(headers or {})
        req=Request(self.base+path,data=None if body is None else json.dumps(body).encode(),headers=h,method=method)
        try: r=urlopen(req,timeout=5)
        except HTTPError as e:r=e
        with r:return r.status,json.loads(r.read()),dict(r.headers)

    def test_sync_and_persisted_mock_and_typed(self):
        status,out,h=self.call('/agents/clinical-summary-agent/invoke',self.request,{'X-Execution-ID':'EXE-test'})
        self.assertEqual(status,200,out)
        self.assertTrue(out['mock_only']);self.assertIsNone(out['items']['anticoagulant_use']['confidence'])
        self.assertEqual(out['items']['previous_stroke']['confirmation_status'],'UNCONFIRMED')
        self.assertIn('recent_surgery_or_bleeding',out['items']);self.assertEqual(len(out['typed_items']),6)
        code,data,_=self.call('/chain/api/v0.1/agent-results/EXE-test')
        self.assertEqual(code,200);self.assertEqual(data['output'],out)
        self.assertEqual(data['output_hash'],'sha256:'+hashlib.sha256(encode(out).encode()).hexdigest())
        code,typed,_=self.call('/agent-results/EXE-test?format=typed')
        self.assertEqual(code,200);self.assertIsInstance(typed['output']['items'],list)
        self.assertEqual(typed['output']['items'],out['typed_items'])
        self.assertTrue((Path(self.tmp.name)/'summary.sqlite3').is_file())

    def test_async_poll_idempotency_and_conflict(self):
        code,data,h=self.call('/agents/clinical-summary-agent/invoke?async=true',self.request,{'X-Execution-ID':'EXE-async'})
        self.assertIn(code,(200,202))
        self.app.wait('EXE-async')
        _,status,_=self.call('/agent-executions/EXE-async');self.assertEqual(status['status'],'SUCCESS')
        before=self.app.store.get('EXE-async')['completed']
        self.call('/agents/clinical-summary-agent/invoke',self.request,{'X-Execution-ID':'EXE-async'})
        self.assertEqual(before,self.app.store.get('EXE-async')['completed'])
        modified=copy.deepcopy(self.request);modified['episode_id']='changed'
        code,_,_=self.call('/agents/clinical-summary-agent/invoke',modified,{'X-Execution-ID':'EXE-async'})
        self.assertEqual(code,409)

    def test_http_data_api_all_four_resources_and_tokens(self):
        reader=HTTPDataAPI(self.base+'/chain/api/v0.1',token='test-token',mock_only=True)
        for ref in self.request['input_references']:
            path=endpoint(ref,self.request)
            self.assertEqual(reader.get(path),self.responses['GET '+path])
        self.app.reader_factory=lambda:HTTPDataAPI(self.base+'/chain/api/v0.1',token='test-token',mock_only=True)
        code,_,_=self.call('/agents/clinical-summary-agent/invoke',self.request)
        self.assertEqual(code,200)
        auto=HTTPDataAPI(self.base+'/chain/api/v0.1',token='test-token')
        auto.get(endpoint(self.request['input_references'][0],self.request))
        self.assertTrue(auto.mock_only)
        with self.assertRaises(DataAPIError):HTTPDataAPI(self.base,token='wrong').get('/health')
        with self.assertRaises(ValueError):reader.get('https://elsewhere.invalid/documents/x')

    def test_rejects_bad_requests_without_creating_runs(self):
        for body in [None,[],{},dict(self.request,trigger={'state_enter':'S2'}),dict(self.request,input_references=['document:../bad@1'])]:
            code,_,_=self.call('/agents/clinical-summary-agent/invoke',body,method='POST')
            self.assertEqual(code,400)
        code,_,_=self.call('/agents/clinical-summary-agent/invoke?async=maybe',self.request,{'X-Execution-ID':'invalid-query'})
        self.assertEqual(code,400);self.assertIsNone(self.app.store.get('invalid-query'))
        code,_,_=self.call('/health',headers={'Authorization':'Bearer wrong'});self.assertEqual(code,401)
        code,_,_=self.call('/agent-results/unknown');self.assertEqual(code,404)

    def test_split_question_ids_and_source_failure(self):
        self.request['questions']=['recent_surgery','recent_bleeding']
        code,out,_=self.call('/agents/clinical-summary-agent/invoke?format=typed',self.request)
        self.assertEqual(code,200,out);self.assertEqual(len(out['items']),2)
        self.app.reader_factory=lambda:FixtureDataAPI({})
        code,data,_=self.call('/agents/clinical-summary-agent/invoke',self.request)
        self.assertEqual(code,422);self.assertEqual(data['status'],'FAILED');self.assertNotIn('output',data)

    def test_timeout_never_becomes_success_later(self):
        original=self.app.extractor
        class Slow:
            def extract(self,docs,questions):
                time.sleep(.15)
                return original.extract(docs,questions)
        self.app.extractor=Slow();self.app.timeout=.03
        code,data,_=self.call('/agents/clinical-summary-agent/invoke',self.request,{'X-Execution-ID':'timeout'})
        self.assertEqual(code,504);self.assertEqual(data['error']['code'],'TIMEOUT')
        time.sleep(.2)
        self.assertEqual(self.app.store.get('timeout')['status'],'FAILED')
        self.assertIsNone(self.app.store.get('timeout')['output'])

    def test_openapi_cors_and_demo_examples(self):
        code,spec,_=self.call('/openapi.json');self.assertEqual(code,200)
        self.assertIn('/agents/clinical-summary-agent/invoke',spec['paths'])
        code,_,h=self.call('/health',headers={'Origin':'http://localhost:3000'})
        self.assertEqual(h['Access-Control-Allow-Origin'],'http://localhost:3000')
        code,d,_=self.call('/examples/s1');self.assertEqual(code,200);self.assertTrue(d['mock_only'])

    def test_store_reopens_results_and_marks_interrupted(self):
        root=Path(self.tmp.name)/'restart'
        one=Store(root);one.create('pending',self.request);one.db.close()
        two=Store(root)
        self.assertEqual(two.get('pending')['error']['code'],'INTERRUPTED')
        two.db.close()

    def test_production_storage_guard_rejects_root(self):
        with self.assertRaises(ValueError):storage_root('/tmp/summary-outside-approved-data')

    def latest_url(self, **overrides):
        params={k:self.request[k] for k in ('patient_id','encounter_id','episode_id')}
        params.update(overrides)
        return '/summary-results/latest?'+urlencode(params)

    def test_input_is_persisted_before_inference_and_not_exposed(self):
        original=self.app.extractor
        def extract(docs, questions):
            saved=self.app.store.get('audit')
            self.assertEqual(saved['input_audit']['coverage'],'complete')
            self.assertEqual(len(saved['input_snapshot']),len(self.request['input_references']))
            result=original.extract(docs,questions)
            next(iter(docs.values()))['text']='mutated extractor copy'
            return result
        with patch.object(original,'extract',side_effect=None) as call:
            # Use a separate instance to avoid recursive mocked extract calls.
            original=DemoExtractor(self.cases)
            call.side_effect=extract
            code,_,_=self.call('/agents/clinical-summary-agent/invoke',self.request,{'X-Execution-ID':'audit'})
        self.assertEqual(code,200)
        data=self.app.store.get('audit');audit=data['input_audit']
        expected=digest({'patient_id':self.request['patient_id'],'encounter_id':self.request['encounter_id'],
            'episode_id':self.request['episode_id'],'questions':audit['question_plan']['resolved'],
            'resources':data['input_snapshot']})
        self.assertEqual(audit['input_snapshot_hash'],expected)
        self.assertIn('history_s1_extractor.py',audit['implementation']['files'])
        for source in audit['sources']:
            self.assertEqual(source['content_hash'],digest(data['input_snapshot'][source['source_ref']]))
        _,view,_=self.call('/agent-executions/audit')
        self.assertNotIn('input_snapshot',view)
        self.assertEqual(view['input_audit'],audit)

    def test_question_plan_and_invalid_question_types(self):
        self.request['questions']=[q for q in self.request['questions'] if q!='antiplatelet_use']
        code,_,_=self.call('/agents/clinical-summary-agent/invoke',self.request,{'X-Execution-ID':'plan'})
        self.assertEqual(code,200)
        plan=self.app.store.get('plan')['question_plan']
        self.assertEqual(plan['resolved'],self.app.store.get('plan')['typed_output']['questions'])
        self.assertIn('recent_surgery_or_bleeding',plan['aliases'])
        self.assertEqual(plan['automatically_included'],['antiplatelet_use'])
        for question in ('unsupported',{},[],None,17):
            code,_,_=self.call('/agents/clinical-summary-agent/invoke',dict(self.request,questions=[question]))
            self.assertEqual(code,400)

    def test_missing_resource_fails_without_model_and_keeps_partial_input(self):
        responses=copy.deepcopy(self.responses)
        ref=self.request['input_references'][-1]
        del responses['GET '+endpoint(ref,self.request)]
        self.app.reader_factory=lambda:FixtureDataAPI(responses)
        with patch.object(self.app.extractor,'extract') as extract:
            code,out,_=self.call('/agents/clinical-summary-agent/invoke',self.request,{'X-Execution-ID':'missing'})
            extract.assert_not_called()
        self.assertEqual(code,422);self.assertEqual(out['error']['code'],'INPUT_RESOLUTION_FAILED')
        saved=self.app.store.get('missing')
        self.assertIsNone(saved['typed_output']);self.assertIsNone(saved['generation'])
        self.assertEqual(saved['input_audit']['coverage'],'incomplete')
        self.assertEqual(saved['input_audit']['sources'][-1]['stage'],'retrieve')
        self.assertEqual(len(saved['input_snapshot']),len(self.request['input_references'])-1)

    def test_bad_patient_version_and_structured_shape_never_call_model(self):
        self.request['input_references'].append('medication:active')
        self.responses['GET '+endpoint('medication:active',self.request)]={
            'patient_id':self.request['patient_id'],'medications':[]}
        document=next(r for r in self.request['input_references'] if r.startswith('document:'))
        for ref,key,value in ((document,'patient_id','wrong'),(document,'version',999),
                              ('medication:active','medications',None)):
            responses=copy.deepcopy(self.responses)
            responses['GET '+endpoint(ref,self.request)][key]=value
            self.app.reader_factory=lambda:FixtureDataAPI(responses)
            with patch.object(self.app.extractor,'extract') as extract:
                code,out,_=self.call('/agents/clinical-summary-agent/invoke',self.request)
                extract.assert_not_called()
            self.assertEqual(code,422);self.assertEqual(out['error']['code'],'INPUT_RESOLUTION_FAILED')

    def test_extraction_failure_keeps_complete_input_and_restart_history(self):
        with patch.object(self.app.extractor,'extract',side_effect=ValueError('invalid model JSON')):
            code,out,_=self.call('/agents/clinical-summary-agent/invoke',self.request,{'X-Execution-ID':'badmodel'})
        self.assertEqual(code,422);self.assertEqual(out['error']['code'],'EXTRACTION_FAILED')
        before=self.app.store.get('badmodel')
        self.assertEqual(before['input_audit']['coverage'],'complete')
        reopened=Store(self.tmp.name)
        try:self.assertEqual(reopened.get('badmodel')['input_snapshot'],before['input_snapshot'])
        finally:reopened.db.close()

    def test_latest_success_survives_newer_failed_attempt_and_filters_ids(self):
        self.call('/agents/clinical-summary-agent/invoke',self.request,{'X-Execution-ID':'good'})
        self.app.reader_factory=lambda:FixtureDataAPI({})
        self.call('/agents/clinical-summary-agent/invoke',self.request,{'X-Execution-ID':'failed'})
        code,view,_=self.call(self.latest_url(format='typed'))
        self.assertEqual(code,200);self.assertTrue(view['has_newer_attempt'])
        self.assertEqual(view['latest_execution']['execution_id'],'failed')
        self.assertEqual(view['latest_success']['execution_id'],'good')
        self.assertIsInstance(view['latest_success']['output']['items'],list)
        self.assertNotIn('input_snapshot',view['latest_execution'])
        for key in ('patient_id','encounter_id','episode_id'):
            self.assertEqual(self.call(self.latest_url(**{key:'unrelated'}))[0],404)
        self.assertEqual(self.call('/summary-results/latest')[0],400)

    def test_latest_without_success_is_explicit(self):
        self.app.reader_factory=lambda:FixtureDataAPI({})
        self.call('/agents/clinical-summary-agent/invoke',self.request)
        code,view,_=self.call(self.latest_url())
        self.assertEqual(code,200);self.assertIsNone(view['latest_success'])
        self.assertFalse(view['has_newer_attempt'])

    def test_same_id_reuses_input_and_new_id_captures_changed_resource(self):
        self.request['input_references'].append('medication:active')
        self.responses['GET '+endpoint('medication:active',self.request)]={
            'patient_id':self.request['patient_id'],'medications':[]}
        self.call('/agents/clinical-summary-agent/invoke',self.request,{'X-Execution-ID':'first'})
        first=self.app.store.get('first')['input_audit']['input_snapshot_hash']
        responses=copy.deepcopy(self.responses)
        responses['GET '+endpoint('medication:active',self.request)]['as_of']='2026-10-08'
        self.app.reader_factory=lambda:FixtureDataAPI(responses)
        self.call('/agents/clinical-summary-agent/invoke',self.request,{'X-Execution-ID':'first'})
        self.assertEqual(first,self.app.store.get('first')['input_audit']['input_snapshot_hash'])
        self.call('/agents/clinical-summary-agent/invoke',self.request,{'X-Execution-ID':'second'})
        self.assertNotEqual(first,self.app.store.get('second')['input_audit']['input_snapshot_hash'])


if __name__=='__main__':unittest.main()
