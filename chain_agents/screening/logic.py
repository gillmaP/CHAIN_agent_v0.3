"""Baseline: explicit synthetic fixture ONLY. Replace run() with team logic.

No keyword classifier, hard-coded positive fallback, LLM or clinical rule here.
Keep the domain output contract or coordinate its change with orchestration.
"""
import copy


def run(request, snapshot, services):
    backend = getattr(services, 'backend', None)
    if backend is None:
        raise ValueError('Screening not implemented: configure a synthetic fixture backend')
    result = copy.deepcopy(backend.select(request, snapshot))
    if set(result) != {'screening_result', 'mock_only', 'basis'}:
        raise ValueError('Unexpected screening output keys')
    basis = result['basis']
    if (result['screening_result'] not in {'POSITIVE', 'NEGATIVE'}
            or result['mock_only'] is not True
            or not isinstance(basis, list) or not basis
            or not all(isinstance(s, str) and s.strip() for s in basis)
            or len(set(basis)) != len(basis)):
        raise ValueError('Invalid synthetic screening result')
    return result
