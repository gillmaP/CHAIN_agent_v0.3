"""Clinical Summary Agent entrypoint."""
from .logic import run


def invoke(request, snapshot, services):
    if not isinstance(request, dict):
        raise ValueError('Summary request must be an object')
    mode = request.get('mode')
    if mode not in (None, 'summary'):
        raise ValueError('Summary supports one operation: summary')
    if snapshot is not None:
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get('snapshot_id'), str):
            raise ValueError('snapshot must contain snapshot_id when supplied')
        requested_snapshot = request.get('input_snapshot_id')
        if requested_snapshot is not None and requested_snapshot != snapshot['snapshot_id']:
            raise ValueError('Snapshot binding mismatch')
    return run(request, snapshot, services)
