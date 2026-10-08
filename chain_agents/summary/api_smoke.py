"""Real-model end-to-end HTTP smoke run against synthetic Site Data API examples.

Usage: python -m chain_agents.summary.api_smoke --root /data/data2/.../new --model gemma4_12b_it
Never uses a model-output fixture for inference. Starts loopback HTTP servers and stops them on exit.
"""
import argparse
import json
from pathlib import Path
import threading
from urllib.request import Request,urlopen
from urllib.error import HTTPError

from .api_service import Application,DemoExtractor,make_server
from .api_adapter import HTTPDataAPI
from .mock_contract import FixtureDataAPI
from .history_s1_cases import cases
from .history_s1_extractor import LocalS1Extractor
from .history_s1_report import _semantic_match
from .experiment import MODELS


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True)
    p.add_argument('--model',required=True,choices=['qwen35_9b','gemma4_12b_it'])
    args=p.parse_args()
    root=Path(args.root).resolve()
    if not any(root.is_relative_to(Path(x)) for x in ('/data/data2','/data/data3')):raise ValueError('root must be data2/data3')
    root.mkdir(parents=True,exist_ok=False)
    base=Path('/data/data2/jhbak/CHAIN_agent_summary_prototype')
    files=base/'datasets/mock_v012'
    mock_request=next(x['input'] for x in json.loads((files/'05_agent_executions.json').read_text()) if x['key']=='summary')
    mock_responses=json.loads((files/'15_data_api_simple.json').read_text())
    case=cases()[0]
    responses={**mock_responses,**case['api_responses']}
    data_app=Application(root/'tool',lambda:FixtureDataAPI(responses),DemoExtractor([case]),demo_cases=[{'request':mock_request,'api_responses':mock_responses},case])
    tool=make_server(data_app,port=0,api_token='synthetic-test-token')
    t=threading.Thread(target=tool.serve_forever,daemon=True);t.start()
    api=None;app=None
    results=[]
    try:
        gpu={'qwen35_9b':'2','gemma4_12b_it':'3'}[args.model]
        print('LOADING',args.model,'GPU',gpu,flush=True)
        extractor=LocalS1Extractor(args.model,base/'models'/MODELS[args.model]['directory'],gpu=gpu,method='direct',max_new_tokens=8192)
        endpoint='http://127.0.0.1:'+str(tool.server_port)+'/chain/api/v0.1'
        app=Application(root/'agent',lambda:HTTPDataAPI(endpoint,'synthetic-test-token',mock_only=True),extractor,timeout=120)
        api=make_server(app,port=0)
        u=threading.Thread(target=api.serve_forever,daemon=True);u.start()
        url='http://127.0.0.1:'+str(api.server_port)
        for name,request in [('mock_v012',mock_request),('positive_use',case['request'])]:
            eid='EXE-smoke-'+name
            call=Request(url+'/agents/clinical-summary-agent/invoke?async=true',data=json.dumps(request).encode(),headers={'Content-Type':'application/json','X-Execution-ID':eid})
            with urlopen(call,timeout=10) as response: submitted=json.load(response)
            app.wait(eid)
            try:response=urlopen(url+'/agent-results/'+eid+'?format=typed',timeout=10)
            except HTTPError as exc:response=exc
            with response:status=response.status;body=json.load(response)
            stored=app.store.get(eid)
            record={'case':name,'http_status':status,'execution_status':stored['status'],
                    'result':body,'data_accessed':stored.get('data_accessed',[]),
                    'generation_calls':extractor.generation_calls,'error':stored.get('error')}
            if status==200:
                assert stored['output']['mock_only'] is True
                assert stored['output']['items']['anticoagulant_use']['confidence'] is None
                assert len(stored['data_accessed'])==len(request['input_references'])
                assert extractor.generation_calls==1
                if name=='positive_use':
                    actual={x['question']:x for x in body['output']['items']}
                    record['correct_fields']=sum(_semantic_match(x['question'],actual.get(x['question']),x) for x in case['gold_items'])
                else:
                    actual={x['question']:x for x in body['output']['items']}
                    record['explicit_medication_checks']={'anticoagulant_false':actual['anticoagulant_use']['value'] is False,'antiplatelet_true':actual['antiplatelet_use']['value'] is True}
            results.append(record)
            (root/'results.json').write_text(json.dumps({'model':args.model,'gpu':gpu,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
            print(name,status,record.get('correct_fields'),record.get('error'),flush=True)
        if any(x['http_status']!=200 for x in results):raise RuntimeError('Live smoke includes failed extraction; inspect raw generation in SQLite')
        print('PASS',args.model,flush=True)
    finally:
        if api:api.shutdown();api.server_close();u.join()
        if app:app.close()
        tool.shutdown();tool.server_close();t.join();data_app.close()


if __name__=='__main__':main()
