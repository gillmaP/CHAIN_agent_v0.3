"""Small persistent Summary HTTP runner for JLK integration; standard library only.

Domain entrypoint remains agent.invoke. No workflow transition or Safety Gate is
implemented here. Bind locally or place behind JLK's authenticated gateway.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs
import uuid

from .agent import invoke
from .mock_contract import FixtureDataAPI, requested_items, endpoint
from .history_s1_contract import canonical_questions
from .api_adapter import HTTPDataAPI, DataAPIError, mock_output

AGENT = 'clinical-summary-agent'
VERSION = '0.3.0-prototype'


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class ConflictError(ValueError):
    pass


class BusyError(RuntimeError):
    pass


def storage_root(value):
    root = Path(value).resolve()
    if not any(root.is_relative_to(Path(p)) for p in ('/data/data2', '/data/data3')):
        raise ValueError('Persistent output must be under /data/data2 or /data/data3')
    return root


class Store:
    def __init__(self, root):
        self.root = storage_root(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root/'summary.sqlite3', check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS executions (id TEXT PRIMARY KEY, input_hash TEXT NOT NULL, body TEXT NOT NULL)')
        # Interrupted runs cannot be silently re-labelled SUCCESS or automatically rerun.
        for eid, _, body in self.db.execute('SELECT * FROM executions').fetchall():
            data = json.loads(body)
            if data['status'] in ('QUEUED', 'RUNNING'):
                data.update(status='FAILED', completed=now(), error={'code': 'INTERRUPTED', 'message': 'Service restarted before completion'})
                self.db.execute('UPDATE executions SET body=? WHERE id=?', (encode(data), eid))
        self.db.commit()

    def get(self, eid):
        with self.lock:
            row = self.db.execute('SELECT body FROM executions WHERE id=?', (eid,)).fetchone()
            return json.loads(row[0]) if row else None

    def create(self, eid, request):
        digest = 'sha256:' + hashlib.sha256(encode(request).encode()).hexdigest()
        with self.lock:
            row = self.db.execute('SELECT input_hash,body FROM executions WHERE id=?', (eid,)).fetchone()
            if row:
                if row[0] != digest:
                    raise ConflictError('Execution ID already belongs to a different request')
                return json.loads(row[1]), False
            data = {'execution_id': eid, 'agent_id': AGENT, 'agent_version': VERSION,
                    'status': 'QUEUED', 'submitted': now(), 'input_hash': digest,
                    'request': request, 'output': None, 'typed_output': None, 'error': None}
            self.db.execute('INSERT INTO executions VALUES (?,?,?)', (eid, digest, encode(data)))
            self.db.commit()
            return data, True

    def update(self, eid, only_status=None, **fields):
        with self.lock:
            data = self.get(eid)
            if only_status is not None and data['status'] != only_status:
                return False
            data.update(fields)
            self.db.execute('UPDATE executions SET body=? WHERE id=?', (encode(data), eid))
            self.db.commit()
            return True


class Application:
    def __init__(self, root, reader_factory, extractor, timeout=120, demo_cases=None):
        self.store = Store(root)
        self.reader_factory, self.extractor, self.timeout = reader_factory, extractor, timeout
        self.demo_cases = demo_cases or []
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='summary')
        self.slots = threading.BoundedSemaphore(16)
        self.lock = threading.Lock()
        self.events = {}

    def submit(self, request, eid=None):
        requested_items(request)
        canonical_questions(request['questions'])
        for ref in request['input_references']:
            endpoint(ref, request)
        if not isinstance(request.get('trigger'), dict) or request['trigger'].get('state_enter') != 'S1':
            raise ValueError('HTTP S1 runner requires trigger.state_enter=S1')
        eid = eid or 'EXE-SUM-' + uuid.uuid4().hex
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', eid):
            raise ValueError('Invalid execution ID')
        with self.lock:
            prior = self.store.get(eid)
            if prior:
                data, _ = self.store.create(eid, request)
                return data
            if not self.slots.acquire(blocking=False):
                raise BusyError('Execution queue is full')
            try:
                data, created = self.store.create(eid, request)
                self.events[eid] = threading.Event()
                self.pool.submit(self._run, eid)
                return data
            except Exception:
                self.slots.release()
                raise

    def _run(self, eid):
        self.store.update(eid, status='RUNNING', started=now())
        timer = threading.Timer(self.timeout, self._expire, args=(eid,))
        timer.daemon = True
        timer.start()
        started = time.perf_counter()
        try:
            request = self.store.get(eid)['request']
            reader = self.reader_factory()
            result = invoke(request, None, SimpleNamespace(summary_data_api=reader, summary_extractor=self.extractor))
            completed = now()
            wire = mock_output(result, request, eid, completed, round((time.perf_counter()-started)*1000))
            digest = 'sha256:' + hashlib.sha256(encode(wire).encode()).hexdigest()
            self.store.update(eid, only_status='RUNNING', status='SUCCESS', completed=completed,
                              output=wire, typed_output=result, output_hash=digest,
                              generation=getattr(self.extractor, 'last_generation', None),
                              data_accessed=getattr(reader, 'accessed', []))
        except Exception as exc:
            code = 'DATA_API_FAILED' if isinstance(exc, DataAPIError) else 'EXTRACTION_FAILED'
            # Detailed patient-bearing raw output stays in the local result store.
            self.store.update(eid, only_status='RUNNING', status='FAILED', completed=now(),
                              error={'code': code, 'message': 'Summary could not produce a valid result'},
                              diagnostic={'type':type(exc).__name__, 'detail':str(exc)},
                              generation=getattr(self.extractor, 'last_generation', None))
        finally:
            timer.cancel()
            with self.lock:
                event = self.events.pop(eid, None)
            if event:
                event.set()
            self.slots.release()

    def _expire(self, eid):
        self.store.update(eid, only_status='RUNNING', status='FAILED', completed=now(),
                          error={'code':'TIMEOUT', 'message':'Execution exceeded configured time limit'})
        with self.lock:
            event = self.events.get(eid)
        if event:
            event.set()

    def wait(self, eid):
        with self.lock:
            event = self.events.get(eid)
        if event:
            event.wait(self.timeout + 1)
        return self.store.get(eid)

    def close(self):
        self.pool.shutdown(wait=True)
        self.store.db.close()


def execution_view(data):
    return {k:v for k,v in data.items() if k not in ('request','output','typed_output','generation','diagnostic')}


def _base_spec():
    request_schema = {'type':'object', 'required':['episode_id','encounter_id','patient_id','trigger','input_references','questions'],
        'properties': {**{k:{'type':'string'} for k in ('episode_id','encounter_id','patient_id')},
            'trigger':{'type':'object','required':['state_enter'],'properties':{'state_enter':{'type':'string','enum':['S1']},'cause_event_id':{'type':'string'}}},
            'input_references':{'type':'array','minItems':1,'uniqueItems':True,'items':{'type':'string'}},
            'questions':{'type':'array','minItems':1,'items':{'type':'string','enum':['anticoagulant_use','antiplatelet_use','recent_surgery_or_bleeding','recent_surgery','recent_bleeding','previous_stroke','lkw_records']}}}}
    return {'openapi':'3.0.3','info':{'title':'CHAIN Summary integration API','version':VERSION},
        'paths': {
            '/health':{'get':{'summary':'Readiness (model loaded before server starts)','responses':{'200':{'description':'Ready'}}}},
            '/agents/clinical-summary-agent/invoke':{'post':{'summary':'Run initial S1 summary',
                'parameters':[{'in':'header','name':'X-Execution-ID','schema':{'type':'string'},'description':'Idempotency key; same ID and same body reuses stored execution'},
                              {'in':'query','name':'async','schema':{'type':'boolean','default':False}},
                              {'in':'query','name':'format','schema':{'type':'string','enum':['mock','typed'],'default':'mock'}}],
                'requestBody':{'required':True,'content':{'application/json':{'schema':request_schema}}},
                'responses':{str(s):{'description':d} for s,d in [(200,'Completed output'),(202,'Queued/running; poll Location'),(400,'Invalid request'),(401,'Unauthorized'),(409,'ID conflict'),(413,'Body too large'),(422,'Extraction failed'),(429,'Queue full'),(504,'Execution timeout')]}}},
            '/agent-executions/{execution_id}':{'get':{'summary':'Poll persisted execution status','parameters':[{'in':'path','name':'execution_id','required':True,'schema':{'type':'string'}}],'responses':{'200':{'description':'Status, timestamps and error'},'404':{'description':'Unknown execution'}}}},
            '/agent-results/{execution_id}':{'get':{'summary':'Read persisted output; optional format=typed','parameters':[{'in':'path','name':'execution_id','required':True,'schema':{'type':'string'}},{'in':'query','name':'format','schema':{'type':'string','enum':['mock','typed']}}],'responses':{'200':{'description':'Result envelope with output'},'202':{'description':'Pending'},'404':{'description':'Unknown execution'},'422':{'description':'Failed execution'},'504':{'description':'Timeout'}}}},
        }}


def api_spec():
    spec = _base_spec()
    evidence = {'type':'object','required':['source_ref'],'properties':{
        'source_ref':{'type':'string'},'quote':{'type':'string'},'record':{'type':'object'}},
        'description':'Exactly source_ref+quote for narrative or source_ref+record for structured evidence.'}
    alternative = {'type':'object','required':['value','evidence'],'properties':{
        'value':{},'evidence':{'type':'array','items':{'$ref':'#/components/schemas/Evidence'}}}}
    typed_item = {'type':'object','additionalProperties':False,
        'required':['question','status','value','evidence','alternatives'],
        'properties':{'question':{'type':'string'},'status':{'type':'string','enum':['documented','not_stated','explicitly_unknown','conflicting','not_applicable']},
        'value':{'nullable':True,'description':'Boolean for use/history; time object for LKW; null for unknown/conflicting. See S1_TYPED_SUMMARY.md.'},
        'evidence':{'type':'array','items':{'$ref':'#/components/schemas/Evidence'}},
        'alternatives':{'type':'array','items':{'$ref':'#/components/schemas/Alternative'}}}}
    mock_item = {'type':'object','required':['status','value','confidence','sources','confirmation_status','alternatives'],
        'properties':{'status':{'type':'string','enum':['PRESENT','NO_EVIDENCE','NONE_DOCUMENTED','RECORDED','NOT_STATED','UNKNOWN','CONFLICTING','NOT_APPLICABLE']},
        'value':{'nullable':True},'confidence':{'type':'number','nullable':True,'description':'Always null; not calibrated.'},
        'sources':{'type':'array','items':{'$ref':'#/components/schemas/Evidence'}},
        'confirmation_status':{'type':'string','enum':['UNCONFIRMED']},
        'alternatives':{'type':'array','items':{'$ref':'#/components/schemas/Alternative'}}}}
    spec['components']={'securitySchemes':{'bearerAuth':{'type':'http','scheme':'bearer','description':'Deployment gateway token; NOT a WG4 execution JWT validator.'}},
        'schemas':{'Evidence':evidence,'Alternative':alternative,'TypedItem':typed_item,'MockItem':mock_item,
        'TypedOutput':{'type':'object','required':['schema_version','episode_id','encounter_id','items','missing_information','model_info','mock_only'],
            'properties':{'schema_version':{'type':'string'},'episode_id':{'type':'string'},'encounter_id':{'type':'string'},
                'items':{'type':'array','items':{'$ref':'#/components/schemas/TypedItem'}},'questions':{'type':'array','items':{'type':'string'}},
                'input_references':{'type':'array','items':{'type':'string'}},'missing_information':{'type':'array','items':{'type':'string'}},
                'model_info':{'type':'object'},'mock_only':{'type':'boolean'}}},
        'IntegrationOutput':{'type':'object','required':['schema_version','agent_id','agent_version','execution_id','items','typed_items','produced_time','processing_time_ms','mock_only'],
            'properties':{'schema_version':{'type':'string','enum':['clinical-summary-integration/v1']},
                **{k:{'type':'string'} for k in ('agent_id','agent_version','execution_id','episode_id','encounter_id','typed_schema_version')},
                'items':{'type':'object','additionalProperties':{'$ref':'#/components/schemas/MockItem'}},
                'typed_items':{'type':'array','items':{'$ref':'#/components/schemas/TypedItem'}},
                'produced_time':{'type':'string','format':'date-time'},'processing_time_ms':{'type':'integer'},
                'missing_information':{'type':'array','items':{'type':'string'}},'model_info':{'type':'object'},
                'mock_only':{'type':'boolean'},'compatibility_notes':{'type':'array','items':{'type':'string'}}}},
        'Execution':{'type':'object','required':['execution_id','status'],'properties':{
            'execution_id':{'type':'string'},'status':{'type':'string','enum':['QUEUED','RUNNING','SUCCESS','FAILED']},
            'submitted':{'type':'string','format':'date-time'},'started':{'type':'string','format':'date-time'},
            'completed':{'type':'string','format':'date-time'},'error':{'type':'object','nullable':True}}}}}
    post=spec['paths']['/agents/clinical-summary-agent/invoke']['post']
    post['responses']['200']['content']={'application/json':{'schema':{'oneOf':[{'$ref':'#/components/schemas/IntegrationOutput'},{'$ref':'#/components/schemas/TypedOutput'}]}}}
    for code in ('202','422','504'):
        post['responses'][code]['content']={'application/json':{'schema':{'$ref':'#/components/schemas/Execution'}}}
    spec['paths']['/agent-results/{execution_id}']['get']['responses']['200']['content']={'application/json':{'schema':{
        'type':'object','required':['execution_id','status','output','output_hash'],'properties':{
            'execution_id':{'type':'string'},'status':{'type':'string','enum':['SUCCESS']},'output_hash':{'type':'string'},
            'output':{'oneOf':[{'$ref':'#/components/schemas/IntegrationOutput'},{'$ref':'#/components/schemas/TypedOutput'}]}}}}}
    spec['security']=[{'bearerAuth':[]},{}]
    return spec


def make_server(app, host='127.0.0.1', port=8091, api_token=None, cors_origin=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not put request IDs or patient-bearing URLs into console logs.

        def send(self, status, obj, headers=None):
            raw = encode(obj).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            if cors_origin and self.headers.get('Origin') == cors_origin:
                self.send_header('Access-Control-Allow-Origin',cors_origin)
                self.send_header('Vary','Origin')
                self.send_header('Access-Control-Expose-Headers','Location,X-Execution-ID')
            for k,v in (headers or {}).items():
                self.send_header(k,v)
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError):
                pass

        def authorized(self):
            if api_token and not hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+api_token):
                self.send(401, {'error':{'code':'UNAUTHORIZED','message':'Bearer token required'}})
                return False
            return True

        def route(self):
            u=urlsplit(self.path)
            path=u.path
            if path.startswith('/chain/api/v0.1/'):
                path=path[len('/chain/api/v0.1'):]
            q=parse_qs(u.query)
            fmt=q.get('format',['mock'])[0]
            if fmt not in ('mock','typed'):
                raise ValueError('format must be mock or typed')
            return path,q,fmt

        def do_OPTIONS(self):
            self.send(200,{}, {'Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Headers':'Authorization,Content-Type,X-Execution-ID'})

        def result(self, data, fmt, invoke_response=False):
            eid=data['execution_id']
            headers={'X-Execution-ID':eid,'Location':'/agent-executions/'+eid}
            if data['status'] in ('QUEUED','RUNNING'):
                self.send(202,execution_view(data),headers)
            elif data['status']=='FAILED':
                self.send(504 if data['error']['code']=='TIMEOUT' else 422,execution_view(data),headers)
            else:
                out=data['typed_output'] if fmt=='typed' else data['output']
                if invoke_response:
                    self.send(200,out,headers)
                else:
                    digest='sha256:'+hashlib.sha256(encode(out).encode()).hexdigest()
                    self.send(200,{'execution_id':eid,'agent_id':AGENT,'agent_version':VERSION,'status':'SUCCESS',
                                   'output_format':fmt,'output_hash':digest,'output':out},headers)

        def do_GET(self):
            if not self.authorized(): return
            try:
                path,q,fmt=self.route()
                if path=='/health': return self.send(200,{'status':'ready','agent_id':AGENT,'version':VERSION,'demo':bool(app.demo_cases)})
                if path in ('/','/openapi.json'): return self.send(200,api_spec())
                if path=='/examples/s1' and app.demo_cases:
                    return self.send(200,{'request':app.demo_cases[0]['request'],'mock_only':True})
                for prefix in ('/agent-executions/','/agent-results/'):
                    if path.startswith(prefix):
                        data=app.store.get(path[len(prefix):])
                        if data is None: return self.send(404,{'error':{'code':'NOT_FOUND'}})
                        if prefix=='/agent-executions/': return self.send(200,execution_view(data))
                        return self.result(data,fmt)
                # Synthetic Site Data API examples, only when explicit --demo is selected.
                if app.demo_cases:
                    key='GET '+path+('?' + urlsplit(self.path).query if urlsplit(self.path).query else '')
                    for case in app.demo_cases:
                        if key in case['api_responses']:
                            return self.send(200,case['api_responses'][key],{'X-CHAIN-Mock':'true'})
                self.send(404,{'error':{'code':'NOT_FOUND'}})
            except ValueError as exc:
                self.send(400,{'error':{'code':'INVALID_REQUEST','message':str(exc)}})

        def do_POST(self):
            if not self.authorized(): return
            try:
                path,q,fmt=self.route()
                if path!='/agents/'+AGENT+'/invoke': return self.send(404,{'error':{'code':'NOT_FOUND'}})
                if self.headers.get('Transfer-Encoding'): raise ValueError('Chunked bodies are not supported')
                length=int(self.headers.get('Content-Length','0'))
                if length>1024*1024: return self.send(413,{'error':{'code':'BODY_TOO_LARGE'}})
                if length<=0: raise ValueError('JSON request body required')
                if q.get('async',['false'])[0] not in ('true','false'): raise ValueError('async must be true or false')
                request=json.loads(self.rfile.read(length), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))
                data=app.submit(request,self.headers.get('X-Execution-ID'))
                if q.get('async',['false'])[0]=='false': data=app.wait(data['execution_id'])
                self.result(data,fmt,invoke_response=True)
            except ConflictError as exc: self.send(409,{'error':{'code':'EXECUTION_ID_CONFLICT','message':str(exc)}})
            except BusyError as exc: self.send(429,{'error':{'code':'BUSY','message':str(exc)}})
            except (ValueError,TypeError) as exc: self.send(400,{'error':{'code':'INVALID_REQUEST','message':str(exc)}})
    return ThreadingHTTPServer((host,port),Handler)


class DemoExtractor:
    model_key='synthetic-demo-no-llm'
    method='demo'
    def __init__(self, cases):
        self.cases=cases
    def extract(self, docs, questions):
        from .history_s1_experiment import _sources,_oracle_payload
        for case in self.cases:
            _,_,expected=_sources(case)
            if docs==expected:
                if not set(questions).issubset(case['questions']): raise ValueError('Demo question mismatch')
                result=_oracle_payload(case,docs)
                result['facts']=[f for f in result['facts'] if f['question'] in questions]
                return result
        raise ValueError('Demo only accepts bundled synthetic documents; use a real model for other inputs')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8091)
    p.add_argument('--store-root',required=True);p.add_argument('--demo',action='store_true')
    p.add_argument('--data-api-url');p.add_argument('--fixture-data')
    p.add_argument('--synthetic-data',action='store_true',help='Mark HTTP Data API inputs as synthetic; always true for demo/fixture modes')
    p.add_argument('--model',choices=['qwen35_9b','gemma4_12b_it'],default='gemma4_12b_it')
    p.add_argument('--model-root',default='/data/data2/jhbak/CHAIN_agent_summary_prototype/models')
    p.add_argument('--gpu',choices=['2','3']);p.add_argument('--timeout',type=float,default=120)
    p.add_argument('--cors-origin')
    args=p.parse_args()
    if args.timeout<=0: p.error('timeout must be positive')
    if args.host not in ('127.0.0.1','localhost','::1') and not os.environ.get('SUMMARY_API_TOKEN'):
        p.error('Non-loopback binding requires SUMMARY_API_TOKEN; use an authenticated TLS gateway')
    demos=[]
    if args.demo:
        if args.data_api_url or args.fixture_data: p.error('--demo cannot combine with a data source')
        from .history_s1_cases import cases
        demos=cases(); responses={k:v for c in demos for k,v in c['api_responses'].items()}
        factory=lambda:FixtureDataAPI(responses)
        extractor=DemoExtractor(demos)
    else:
        if bool(args.data_api_url)==bool(args.fixture_data): p.error('Choose exactly one: --data-api-url or --fixture-data')
        if args.fixture_data:
            responses=json.loads(Path(args.fixture_data).read_text())
            factory=lambda:FixtureDataAPI(responses)
        else:
            factory=lambda:HTTPDataAPI(args.data_api_url,os.environ.get('SUMMARY_DATA_API_TOKEN'),mock_only=args.synthetic_data)
        from .experiment import MODELS
        from .history_s1_extractor import LocalS1Extractor
        base=Path('/data/data2/jhbak/CHAIN_agent_summary_prototype')
        os.environ.setdefault('HF_HOME',str(base/'hf_cache'))
        os.environ.setdefault('TMPDIR',str(base/'runtime/tmp'))
        extractor=LocalS1Extractor(args.model,Path(args.model_root)/MODELS[args.model]['directory'],gpu=args.gpu,method='direct',max_new_tokens=8192)
    app=Application(args.store_root,factory,extractor,args.timeout,demos)
    server=make_server(app,args.host,args.port,os.environ.get('SUMMARY_API_TOKEN'),args.cors_origin)
    print(encode({'status':'ready','host':args.host,'port':server.server_port,'demo':args.demo}),flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close();app.close()


if __name__=='__main__':
    main()
