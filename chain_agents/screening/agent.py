"""Team 1 entrypoint. Keep this signature stable."""
from ..common import inputs
from .logic import run


def invoke(request, snapshot, services):
    inputs(request, snapshot)
    return run(request, snapshot, services)
