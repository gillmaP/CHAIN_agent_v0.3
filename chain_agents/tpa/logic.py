"""Baseline: package received Facts. No eligibility or dose calculations."""
import copy
from ..common import missing_fields


def run(request, snapshot, services):
    facts = copy.deepcopy(snapshot['facts'])
    return {'mode': request['mode'], 'evidence_package': facts,
            'assessment': 'PENDING_MOCK' if missing_fields(facts) else 'STRUCTURED_MOCK_ONLY',
            'mock_only': True}
