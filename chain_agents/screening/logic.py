"""Baseline: explicit synthetic fixture ONLY. Replace run() with team logic.

No keyword classifier, hard-coded positive fallback, LLM or clinical rule here.
Keep the domain output contract or coordinate its change with orchestration.
"""
import copy
from .prototype import ScreeningLLMBackend


def run(request, snapshot, services):
    backend = getattr(services, 'backend', None)
    if backend is None:
        raise ValueError('Screening backend missing: configure an explicit fixture or ScreeningLLMBackend')
    result = copy.deepcopy(backend.select(request, snapshot))
    if not isinstance(result, dict) or set(result) != {'screening_result', 'mock_only', 'basis'}:
        raise ValueError('Unexpected screening output keys')
    basis = result['basis']
    is_real = isinstance(backend, ScreeningLLMBackend)
    if (result['screening_result'] not in {'POSITIVE', 'NEGATIVE'}
            or type(result['mock_only']) is not bool
            or result['mock_only'] is is_real
            or not isinstance(basis, list) or not basis
            or not all(isinstance(s, str) and s.strip() for s in basis)
            or len(set(basis)) != len(basis)):
        raise ValueError('Invalid screening result or untrusted backend mode')
    return result
