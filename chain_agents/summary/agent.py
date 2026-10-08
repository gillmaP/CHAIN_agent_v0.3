"""Team 2 entrypoint. Keep this signature stable."""
from ..common import inputs
from .logic import run


def invoke(request, snapshot, services):
    if 'input_references' not in request:
        inputs(request, snapshot, {'context'})
    return run(request, snapshot, services)
