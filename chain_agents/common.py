"""Small shared helpers. Upstream Runtime owns wire-contract validation."""
import copy
import hashlib
import json

MISSING_STATUSES = frozenset({'UNKNOWN', 'PENDING', 'CONFLICT', 'UNAVAILABLE', 'ERROR', 'RETRACTED', 'INVALIDATED'})

def canonical_hash(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return 'sha256:' + hashlib.sha256(raw).hexdigest()

def inputs(request, snapshot, modes):
    """Check plugin boundary and return isolated facts; no mutation of inputs."""
    if request.get('mode') not in modes:
        raise ValueError('Unsupported Agent mode')
    if request.get('input_snapshot_id') != snapshot.get('snapshot_id'):
        raise ValueError('Snapshot binding mismatch')
    if set(snapshot['facts']) != set(request['scope']):
        raise ValueError('Expected scoped snapshot')
    if not request.get('evaluated_at'):
        raise ValueError('Explicit evaluated_at required')
    return copy.deepcopy(snapshot['facts'])

def missing_fields(facts):
    return sorted(name for name, fact in facts.items()
                  if fact['value'] is None or fact['status'] in MISSING_STATUSES)
