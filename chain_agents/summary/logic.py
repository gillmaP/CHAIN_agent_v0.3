"""Build one complete, question-oriented Clinical Summary result."""


def run(request, snapshot, services):
    from .summary import run_summary
    return run_summary(request, services)
