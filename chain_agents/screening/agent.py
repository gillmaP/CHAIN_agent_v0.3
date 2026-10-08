"""Team 1 entrypoint. Keep this signature stable."""
from ..common import inputs
from .logic import run


def invoke(request, snapshot, services):
    inputs(request, snapshot, {'screening'})
    return run(request, snapshot, services)


# Mock v0.12 reference-only JLK Runner contract. Returns a Python dict.
from .v012_contract import invoke_v012  # noqa: E402,F401
