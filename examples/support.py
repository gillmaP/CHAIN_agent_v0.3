"""Local stand-ins for the two injected services; no Temporal required."""
import copy
from threading import RLock
from chain_agents.services import AgentServices
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

def services(backend=None, *, data_api=None, extractor=None, input_observer=None):
    return AgentServices(cache=MemoryCache(), backend=backend, data_api=data_api, extractor=extractor, input_observer=input_observer)

def sample(mode='screening'):
    timestamp = '2026-10-06T09:00:00+09:00'
    ref = {'system': 'SYNTHETIC', 'record_id': 'TEST-001', 'version': 1, 'field': 'age'}
    facts = {'age': {'value': 68, 'status': 'AVAILABLE', 'source_ref': ref,
                     'source_time': timestamp, 'known_at': timestamp}}
    snapshot = {'known_at': timestamp, 'facts': facts}
    snapshot['snapshot_id'] = canonical_hash(snapshot)
    request = {'request_id': 'LOCAL-TEST-'+mode,
               'input_snapshot_id': snapshot['snapshot_id'], 'scope': ['age'],
               'dependencies': [copy.deepcopy(ref)], 'evaluated_at': timestamp}
    if mode in {'interim', 'final'}:
        request['mode'] = mode
    return request, snapshot
