"""Baseline: scoped Fact passthrough with cache. No clinical NLP.

v0.3 Engine requires structured_context == snapshot.facts.
Do not insert inferred fields here without agreeing a new output contract.
"""
import copy
from ..common import canonical_hash, missing_fields


def run(request, snapshot, services):
    if 'input_references' in request:
        from .history_s1_summary import run_history
        return run_history(request, snapshot, services)
    key = canonical_hash({'snapshot': snapshot['snapshot_id'], 'scope': sorted(request['scope']),
                          'agent_id': request['agent_id'], 'version': request['agent_version'],
                          'manifest': request['manifest_hash'], 'mode': request['mode']})
    def build():
        facts = copy.deepcopy(snapshot['facts'])
        return {'structured_context': facts, 'missing_information': missing_fields(facts),
                'computed_at': request['evaluated_at']}
    payload, hit = services.cache.get_or_create(key, build)
    payload = copy.deepcopy(payload)
    computed = payload.pop('computed_at')
    payload['cache'] = {'key': key, 'hit': hit, 'computed_at': computed}
    return payload
