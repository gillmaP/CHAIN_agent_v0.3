"""Local stand-ins for the two injected services; no Temporal required."""
import copy
from threading import RLock
from types import SimpleNamespace
from chain_agents.common import canonical_hash

class MemoryCache:
    def __init__(self):
        self.values = {}; self.lock = RLock()
    def get_or_create(self, key, factory):
        with self.lock:
            hit = key in self.values
            if not hit: self.values[key] = copy.deepcopy(factory())
            return copy.deepcopy(self.values[key]), hit

class SyntheticBackend:
    def __init__(self, request, snapshot, output):
        self.commitment = canonical_hash([request, snapshot])
        self.output = copy.deepcopy(output)
    def select(self, request, snapshot):
        if canonical_hash([request, snapshot]) != self.commitment:
            raise ValueError('Synthetic fixture input mismatch')
        return copy.deepcopy(self.output)

def services(backend=None):
    return SimpleNamespace(cache=MemoryCache(), backend=backend)

def sample(mode='context'):
    timestamp = '2026-10-06T09:00:00+09:00'
    ref = {'system': 'SYNTHETIC', 'record_id': 'TEST-001', 'version': 1, 'field': 'age'}
    facts = {'age': {'value': 68, 'status': 'AVAILABLE', 'source_ref': ref,
                     'source_time': timestamp, 'known_at': timestamp}}
    snapshot = {'contract_schema': 'chain-context/v0.3', 'known_at': timestamp, 'facts': facts}
    snapshot['snapshot_id'] = canonical_hash(snapshot)
    aid = {'context': 'clinical-summary-agent', 'screening': 'stroke-screening-agent',
           'interim': 'tpa-decision-support-agent', 'final': 'tpa-decision-support-agent'}[mode]
    request = {'contract_schema': 'chain-agent-request/v0.3', 'request_id': 'LOCAL-TEST-'+mode,
               'agent_id': aid, 'agent_version': '0.1.0-starter', 'manifest_hash': 'sha256:'+'0'*64,
               'mode': mode, 'input_snapshot_id': snapshot['snapshot_id'], 'scope': ['age'],
               'dependencies': [copy.deepcopy(ref)], 'evaluated_at': timestamp}
    return request, snapshot
