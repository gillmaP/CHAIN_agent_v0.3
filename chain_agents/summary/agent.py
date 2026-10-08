"""Team 2 entrypoint. Keep this signature stable."""
from ..common import inputs
from .logic import run


def invoke(request, snapshot, services):
    if 'input_references' not in request:
        inputs(request, snapshot, {'context'})
    return run(request, snapshot, services)


def invoke_s1(request, *, data_api, extractor=None, input_observer=None):
    """Explicit S1 entrypoint; caller owns execution IDs, storage and workflow state.

    Returns summary-s1-fields/v1, not the v0.3 structured_context result.
    """
    from types import SimpleNamespace
    from .summary import run_history
    if (not isinstance(request, dict) or not isinstance(request.get('trigger'), dict)
            or request['trigger'].get('state_enter') != 'S1'):
        raise ValueError('invoke_s1 requires trigger.state_enter=S1')
    return run_history(request, None, SimpleNamespace(
        summary_data_api=data_api, summary_extractor=extractor,
        summary_input_observer=input_observer))
