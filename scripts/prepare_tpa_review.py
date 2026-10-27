"""Create a disposable, version-pinned reference Host with evidence-first HITL-2.

Never edits the upstream checkout. Requires its PyYAML dependency.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_SHA = 'fdb382a325d52f89a46b77d50a825a08fe3ff841'
VERSION = '0.2.0-prototype'
OPTIONAL_SCOPE = ['weight_method','weight_entered_by','summary_evidence','recent_surgery','recent_bleeding','previous_stroke',
                  'antiplatelet','aptt','glucose_poct','glucose_lab','a04_hemorrhage',
                  'physician_ncct_read','anticoagulant_details','intracranial_hemorrhage_history']

def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def replace(path, old, new):
    content = path.read_text(encoding='utf-8')
    if content.count(old) != 1:
        raise ValueError('Pinned patch anchor mismatch: ' + str(path))
    path.write_text(content.replace(old,new),encoding='utf-8',newline='\n')

def prepare(upstream, output, *, synthetic_demo=False):
    upstream, output = Path(upstream).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(upstream) or output.is_relative_to(ROOT):
        raise ValueError('Choose a new sibling output directory')
    sha = subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip()
    if sha != UPSTREAM_SHA:
        raise ValueError('Unsupported upstream revision; expected ' + UPSTREAM_SHA)
    if subprocess.run(['git','-C',str(upstream),'diff','--quiet','HEAD']).returncode:
        raise ValueError('Upstream tracked files differ from the pinned revision')
    shutil.copytree(upstream,output,ignore=shutil.ignore_patterns('.git','.venv','__pycache__','output','runtime'))
    agents = output/'chain_agents'
    agents.mkdir()
    for name in ('__init__.py','common.py'):
        shutil.copy2(ROOT/'chain_agents'/name, agents/name)
    shutil.copytree(ROOT/'chain_agents/tpa',agents/'tpa',ignore=shutil.ignore_patterns('__pycache__'))
    contracts = output/'chain_demo/contracts.py'
    replace(contracts,'"confirmations_on_decisions", "question"}, where="HITL Request")',
            '"confirmations_on_decisions", "question"}, {"evidence_mode"}, where="HITL Request")')
    replace(contracts,'for key in ("roles", "options", "result_ids"):\n        strings(request[key], key, nonempty=True)',
            'source_only = request.get("evidence_mode") == "SOURCE_SNAPSHOT"\n    if "evidence_mode" in request and not source_only:\n        raise ValueError("Unknown HITL evidence mode")\n    if source_only:\n        from chain_agents.tpa.orchestrator import validate_source_only\n        validate_source_only(request, snapshot, results)\n    for key in ("roles", "options", "result_ids"):\n        strings(request[key], key, nonempty=(key != "result_ids" or not source_only))')
    temporal = output/'chain_demo/temporal_workflow.py'
    local = output/'demo/local_runtime.py'
    for path, old in ((temporal,'from .engine import Engine'),(local,'from chain_demo.engine import Engine')):
        replace(path,old,'from chain_agents.tpa.orchestrator import EvidenceFirstEngine as Engine')
    replace(temporal,'source_documents_enabled=documents_enabled)',
            'source_documents_enabled=documents_enabled,\n                                 evidence_first_enabled=workflow.patched("chain-tpa-evidence-first-v1"))')
    replace(temporal,'    @workflow.signal\n    def request_context(',
            '    @workflow.signal\n    def request_tpa_review_refresh(self, request: dict):\n        self.inbox.append({"kind":"review_refresh", "request":request})\n\n    @workflow.signal\n    def request_context(')
    replace(temporal,'                elif kind == "context":',
            '                elif kind == "review_refresh":\n                    commands = self.engine.refresh_tpa_review(message["request"], self._now())\n                elif kind == "context":')
    replace(local,'    async def request_context(self,request):',
            '    async def request_tpa_review_refresh(self,request):return await self._submit("review_refresh",request)\n    async def request_context(self,request):')
    replace(local,'                    elif kind=="context":',
            '                    elif kind=="review_refresh":commands=self.engine.refresh_tpa_review(value,self.clock.now())\n                    elif kind=="context":')
    # Portability fix in this disposable reference copy; no clinical rule changes.
    replace(output/'chain_demo/agents/fixture_backend.py','str(resolved.relative_to(self.root))','resolved.relative_to(self.root).as_posix()')
    config = output/'config'
    read = lambda name: yaml.safe_load((config/name).read_text(encoding='utf-8'))
    catalog, registry, policy, workflow = [read(n) for n in ('agents_v03.yaml','plugins.yaml','policy_v03.yaml','workflow_v03.yaml')]
    for installed in registry['implementations'].values():
        installed['files'] = {name:'sha256:' + hashlib.sha256((output/name).read_bytes()).hexdigest()
                              for name in installed['files']}
        installed['manifest_hash'] = digest({k:v for k,v in installed.items() if k != 'manifest_hash'})
    spec = catalog['agents']['tpa_decision_support']
    spec.update(version=VERSION,implementation='tpa-review-v2',backend={'kind':'structured'})
    policy['runtime']['approved_agents'][spec['agent_id']]['versions'] = [VERSION]
    scope = workflow['agents']['tpa_decision_support']['scopes']
    for mode in ('interim','final'):
        scope[mode] = list(dict.fromkeys(scope[mode] + OPTIONAL_SCOPE))
    paths = [agents/'__init__.py',agents/'common.py'] + sorted(p for p in (agents/'tpa').iterdir() if p.suffix in {'.py','.html'})
    manifest = {'version':'tpa-review-2','entrypoint':'chain_agents.tpa.agent:invoke',
        'contract':'chain-agent/v0.3','installed':True,'status':'APPROVED' if synthetic_demo else 'PENDING',
        'agent_id':spec['agent_id'],'agent_version':VERSION,'data_scopes':spec['data_scopes'],'actions':spec['actions'],
        'files':{p.relative_to(output).as_posix():'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    manifest['manifest_hash'] = digest(manifest)
    registry['implementations']['tpa-review-v2'] = manifest
    catalog['version'] += '-tpa-review2'
    policy['policy_version'] += '-tpa-review2'
    workflow['version'] += '-tpa-review2'
    for name, value in zip(('agents_v03.yaml','plugins.yaml','policy_v03.yaml','workflow_v03.yaml'),(catalog,registry,policy,workflow)):
        (config/name).write_text(yaml.safe_dump(value,allow_unicode=True,sort_keys=False),encoding='utf-8')
    (output/'TPA_REVIEW_INTEGRATION.json').write_text(json.dumps({'upstream_commit':sha,
        'synthetic_demo_only':synthetic_demo,'production_approved':False,
        'changes':['source-only HITL contract','evidence-first Engine','explicit refresh Signal','tPA plugin/scopes']},indent=2),encoding='utf-8')
    return output

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--synthetic-demo',action='store_true')
    args = parser.parse_args()
    print(prepare(args.upstream,args.output,synthetic_demo=args.synthetic_demo))
