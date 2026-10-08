"""Team 3 entrypoint. Keep this signature stable."""
from .logic import run


def invoke(request, snapshot, services):
    return run(request, snapshot, services)
