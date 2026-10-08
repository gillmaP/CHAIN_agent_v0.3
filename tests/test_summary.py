import json
import unittest
from pathlib import Path
from chain_agents.summary.agent import invoke
from chain_agents.summary.data_contract import FixtureDataAPI
from chain_agents.services import AgentServices
from examples.summary import FixtureExtractor

class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((Path(__file__).resolve().parents[1] / 'examples/summary_fixture.json').read_text(encoding='utf-8'))
        self.services = AgentServices(data_api=FixtureDataAPI(self.fixture['api_responses']),
                                      extractor=FixtureExtractor(self.fixture['synthetic_extraction']))

    def test_one_call_builds_question_items(self):
        result = invoke(self.fixture['request'], None, self.services)
        self.assertEqual(result['schema_version'], 'summary-items/v1')
        self.assertEqual(len(result['items']), 6)
        self.assertNotIn('agent', result)
        self.assertNotIn('action', result)

    def test_agent_route_does_not_require_agent_or_action_fields(self):
        request = self.fixture['request']
        self.assertNotIn('agent', request)
        self.assertNotIn('action', request)
        self.assertEqual(len(invoke(request, None, self.services)['items']), 6)

    def test_non_summary_mode_is_rejected(self):
        request = dict(self.fixture['request'], mode='unsupported')
        with self.assertRaises(ValueError):
            invoke(request, None, self.services)
