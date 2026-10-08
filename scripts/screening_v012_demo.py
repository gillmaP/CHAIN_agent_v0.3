#!/usr/bin/env python3
"""Offline, synthetic v0.12 handoff demo: one direct Python call, no HTTP server.

  python scripts/screening_v012_demo.py --mode smoke
  python scripts/screening_v012_demo.py --mode gpu --model qwen35_9b --gpu 0 \
     --model-root /absolute/model/root

Returns JSON to stdout as a *demonstration*. JLK Runtime instead receives the
same Python dict directly. Smoke is not model inference.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from chain_agents.screening.agent import invoke_v012
from chain_agents.screening.site_data_api import SyntheticFixtureDataAPI
from chain_agents.screening.prototype import MODELS


class _SmokeLLM:
    model_key='synthetic-mock-NOT-LLM'
    model_revision='none'
    def generate(self, messages):
        # Verbatim evidence from the provided mock's synthetic patient case.
        obj=json.loads(messages[1]['content'])
        texts={d['source_ref']:d['text'] for d in obj['documents']}
        a='document:DOC-2610060412@1'
        b='document:DOC-2610060403@2'
        rows=[
            ('acute_onset',a,'13:35경 딸과 전화통화 시까지 특이증상 없었다고 함'),
            ('focal_weakness',a,'Motor: Rt. U/E G2, Rt. L/E G3, Lt. side G5'),
            ('language_or_speech_deficit',a,'Global aphasia (comprehension 일부 보존), dysarthria'),
            ('fast_positive',b,'FAST: Face(+) Arm(+) Speech(+)'),
            ('lkw',a,'13:35경 딸과 전화통화 시까지 특이증상 없었다고 함'),
        ]
        findings=[{'code':code,'status':'present','source_ref':ref,'quote':quote}
                  for code,ref,quote in rows if quote in texts[ref]]
        if len(findings) != len(rows):
            raise ValueError('Smoke fixture no longer matches v0.12 source documents')
        return json.dumps({'findings':findings},ensure_ascii=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['smoke','gpu'],default='smoke')
    parser.add_argument('--model',choices=sorted(MODELS),default='qwen35_9b')
    parser.add_argument('--model-root',type=Path)
    parser.add_argument('--gpu',default='0')
    parser.add_argument('--max-new-tokens',type=int,default=1800)
    args=parser.parse_args()
    if args.mode=='gpu':
        if args.model_root:
            os.environ['CHAIN_SCREENING_MODEL_ROOT']=str(args.model_root.resolve())
        from chain_agents.screening.local_model import LocalScreeningModel
        model=LocalScreeningModel(args.model, gpu=args.gpu,max_new_tokens=args.max_new_tokens)
    else:
        model=_SmokeLLM()
    req=json.loads((ROOT/'examples/v012_screening_request.json').read_text(encoding='utf-8'))
    fixtures=json.loads((ROOT/'examples/v012_screening_site_data_fixture.json').read_text(encoding='utf-8'))
    result=invoke_v012(req,execution_id='EXE-HYG-261006-0141',
                       data_api=SyntheticFixtureDataAPI(fixtures),model=model)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
