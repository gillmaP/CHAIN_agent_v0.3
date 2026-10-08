"""Clinical Summary entrypoint for v0.3 context and explicit S1 extraction."""
from ..common import inputs
from .logic import run


def invoke(request, snapshot, services):
    if not isinstance(request, dict):
        raise ValueError('Summary request must be an object')
    if request.get('mode') == 's1':
        from .summary import run_history
        if snapshot is not None:
            raise ValueError('S1 reference-based request expects snapshot=None')
        if not isinstance(request.get('trigger'), dict) or request['trigger'].get('state_enter') != 'S1':
            raise ValueError('S1 request must identify state_enter=S1')
        return run_history(request, None, services)
    if 'input_references' in request:
        raise ValueError('Use mode=s1 for reference-based Summary')
    inputs(request, snapshot, {'context'})
    return run(request, snapshot, services)


def invoke_s1(request, *, data_api, extractor=None, input_observer=None):
    """Convenience wrapper around the same invoke(request, snapshot, services) entrypoint."""
    from ..services import AgentServices
    payload = dict(request, mode='s1')
    return invoke(payload, None, AgentServices(data_api=data_api, extractor=extractor, input_observer=input_observer))
