"""python -m chain_agents.tpa.demo [interim|final|high-bp|low-platelets]."""
import argparse
import copy
import json
from types import SimpleNamespace

from ..common import canonical_hash
from .agent import invoke


def sample(mode='final', scenario='normal'):
    """Explicit synthetic inputs; never source real patient data."""
    now = '2026-10-06T15:36:00+09:00'
    values = {'lkw': '2026-10-06T13:35:00+09:00', 'ncct_completed': mode == 'final',
              'ncct_order_id': 'SYNTHETIC-CT-001', 'ct_order_id': 'SYNTHETIC-CT-001',
              'platelet_count': 214000, 'inr': 1.04, 'anticoagulant': 'NO_EVIDENCE',
              'weight_kg': 67, 'nihss': 12, 'sbp': 172, 'dbp': 94, 'glucose': 158, 'age': 68}
    units = {'platelet_count': '/uL', 'weight_kg': 'kg', 'sbp': 'mmHg', 'dbp': 'mmHg', 'glucose': 'mg/dL'}
    facts = {}
    for name, value in values.items():
        missing = mode == 'interim' and name in {'platelet_count', 'inr', 'nihss'}
        facts[name] = {'value': None if missing else value, 'status': 'PENDING' if missing else 'AVAILABLE',
                       'source_ref': {'system': 'SYNTHETIC', 'record_id': 'TPA-DEMO-001',
                                      'version': 1, 'field': name}, 'source_time': now, 'known_at': now}
        if name in units:
            facts[name]['unit'] = units[name]
    if scenario == 'high-bp':
        facts['sbp']['value'] = 190
    elif scenario == 'low-platelets':
        facts['platelet_count'].update(value=90000, status='AVAILABLE')
    elif scenario != 'normal':
        raise ValueError('Unknown synthetic scenario')
    snapshot = {'known_at': now, 'facts': facts}
    snapshot['snapshot_id'] = canonical_hash(snapshot)
    request = {'request_id': 'SYNTHETIC-TPA-' + mode, 'mode': mode,
               'input_snapshot_id': snapshot['snapshot_id'], 'scope': list(facts),
               'dependencies': [copy.deepcopy(fact['source_ref']) for fact in facts.values()], 'evaluated_at': now}
    return request, snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', nargs='?', default='final',
                        choices=['interim', 'final', 'high-bp', 'low-platelets'])
    scenario = parser.parse_args().scenario
    request, snapshot = sample('interim' if scenario == 'interim' else 'final',
                               scenario if scenario in {'high-bp', 'low-platelets'} else 'normal')
    print(json.dumps(invoke(request, snapshot, SimpleNamespace()), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
