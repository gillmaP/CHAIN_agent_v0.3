"""Build a NEW, disposable orchestrator checkout with these plugins.
Never overwrite the upstream checkout or claim production approval.
Requires PyYAML (already an upstream dependency).
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.1.0-starter'
TEAMS = {'stroke_screening':'screening','clinical_summary':'summary','tpa_decision_support':'tpa'}

def hash_object(obj):
    return 'sha256:'+hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def prepare(upstream, output, demo=False):
    upstream, output = Path(upstream).resolve(), Path(output).resolve()
    if output.exists(): raise ValueError('Output already exists; choose a new directory')
    if output.is_relative_to(upstream) or output.is_relative_to(ROOT):
        raise ValueError('Use a separate sibling directory for integration output')
    if not (upstream/'config/plugins.yaml').is_file(): raise ValueError('Not a CHAIN v0.3 checkout')
    shutil.copytree(upstream,output,ignore=shutil.ignore_patterns('.git','.venv','__pycache__','output','runtime'))
    shutil.copytree(ROOT/'chain_agents',output/'chain_agents',ignore=shutil.ignore_patterns('__pycache__'))
    config=output/'config'
    read=lambda name:yaml.safe_load((config/name).read_text(encoding='utf-8'))
    catalog=read('agents_v03.yaml');registry=read('plugins.yaml');policy=read('policy_v03.yaml')
    # Copy, never edit original fixture manifests: their installation hashes stay intact.
    fixture_relative='starter_fixtures'
    shutil.copytree(output/'episodes/stroke_reference_001_v03/fixtures/cli',output/fixture_relative)
    fixture_path=output/fixture_relative/'manifest.json'
    fixtures=json.loads(fixture_path.read_text(encoding='utf-8'))
    for entry in fixtures['entries']: entry['agent_version']=VERSION
    fixture_path.write_text(json.dumps(fixtures,ensure_ascii=False,indent=2),encoding='utf-8')
    for alias,team in TEAMS.items():
        spec=catalog['agents'][alias]
        plugin_id='starter-'+team
        spec.update(version=VERSION,implementation=plugin_id)
        spec['backend']={'kind':'fixture','manifest':fixture_relative+'/manifest.json'} if team=='screening' else {'kind':'structured'}
        policy['runtime']['approved_agents'][spec['agent_id']]['versions']=[VERSION]
        paths=[output/'chain_agents/__init__.py',output/'chain_agents/common.py',output/'chain_agents/services.py']
        paths+=sorted((output/'chain_agents'/team).rglob('*.py'))
        if team=='screening':paths+=sorted((output/fixture_relative).rglob('*.json'))
        files={p.relative_to(output).as_posix():'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        manifest={'version':'starter-1','entrypoint':f'chain_agents.{team}.agent:invoke',
                  'contract':'chain-agent/v0.3','installed':True,'status':'APPROVED' if demo else 'PENDING',
                  'agent_id':spec['agent_id'],'agent_version':VERSION,
                  'data_scopes':spec['data_scopes'],'actions':spec['actions'],'files':files}
        manifest['manifest_hash']=hash_object(manifest)
        registry['implementations'][plugin_id]=manifest
    catalog['version']='0.3-starter-demo' if demo else '0.3-starter-draft'
    policy['policy_version']=str(policy['policy_version'])+'-starter'
    for name,obj in [('agents_v03.yaml',catalog),('plugins.yaml',registry),('policy_v03.yaml',policy)]:
        (config/name).write_text(yaml.safe_dump(obj,allow_unicode=True,sort_keys=False),encoding='utf-8')
    try:commit=subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip()
    except (subprocess.CalledProcessError,FileNotFoundError):commit='unknown'
    (output/'STARTER_INTEGRATION.json').write_text(json.dumps({'synthetic_demo_only':demo,'production_approved':False,'upstream_commit':commit,'starter_version':VERSION},indent=2))
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--upstream',required=True);p.add_argument('--output',required=True)
    p.add_argument('--synthetic-demo',action='store_true',help='Enable plugins only in a disposable synthetic demo copy; not clinical approval')
    a=p.parse_args();print(prepare(a.upstream,a.output,a.synthetic_demo))
