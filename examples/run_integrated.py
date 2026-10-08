"""Invoke all three Agent modules with synthetic inputs and shared services."""
import json
from pathlib import Path
from chain_agents.screening.agent import invoke as screening
from chain_agents.summary.agent import invoke as summary
from chain_agents.tpa.agent import invoke as tpa
from chain_agents.summary.data_contract import FixtureDataAPI
from chain_agents.services import AgentServices
from .summary_s1 import FixtureExtractor
from .support import sample, services, SyntheticBackend


def main():
    outputs = []
    request, snapshot = sample('screening')
    screening_out = {'screening_result': 'POSITIVE', 'mock_only': True,
                     'basis': ['SYNTHETIC_FIXTURE_ONLY_NOT_A_CLASSIFICATION']}
    outputs.append({'agent': 'screening', 'mode': 'screening',
        'result': screening(request, snapshot, services(SyntheticBackend(request, snapshot, screening_out)))})

    fixture_path = Path(__file__).with_name('summary_s1_fixture.json')
    fixture = json.loads(fixture_path.read_text(encoding='utf-8'))
    summary_request = dict(fixture['request'], mode='s1')
    summary_services = AgentServices(
        data_api=FixtureDataAPI(fixture['api_responses']),
        extractor=FixtureExtractor(fixture['synthetic_extraction']))
    outputs.append({'agent': 'summary', 'mode': 's1',
        'result': summary(summary_request, None, summary_services)})

    for mode in ('interim', 'final'):
        request, snapshot = sample(mode)
        outputs.append({'agent': 'tpa', 'mode': mode,
            'result': tpa(request, snapshot, services())})

    print(json.dumps({'synthetic_only': True, 'pipeline_mapping': False,
                      'agent_results': outputs}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
