"""python -m examples.run [screening|summary|tpa|all]"""
import argparse
import json
from chain_agents.screening.agent import invoke as screening
from chain_agents.summary.agent import invoke as summary
from chain_agents.tpa.agent import invoke as tpa
from .support import sample, services, SyntheticBackend

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('agent', nargs='?', default='all', choices=['all','screening','summary','tpa'])
    args=parser.parse_args()
    calls=[('screening','screening',screening),('summary','context',summary),('tpa','interim',tpa),('tpa','final',tpa)]
    for team,mode,fn in calls:
        if args.agent not in ('all',team): continue
        request,snapshot=sample(mode)
        backend = SyntheticBackend(request,snapshot,{'screening_result':'POSITIVE','mock_only':True,
                                   'basis':['EXPLICIT_SYNTHETIC_TEST_NOT_A_CLASSIFICATION']}) if team=='screening' else None
        print(json.dumps({'agent':team,'mode':mode,'result':fn(request,snapshot,services(backend))},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
