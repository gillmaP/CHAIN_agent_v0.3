"""Summary Agent input and service boundary tests."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from chain_agents.summary.agent import invoke
from chain_agents.summary.extractor import LocalSummaryExtractor
from chain_agents.services import AgentServices
from chain_agents.summary.data_contract import FixtureDataAPI
from examples.summary import FixtureExtractor

class SummaryModuleTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((Path(__file__).resolve().parents[1] / 'examples/summary_fixture.json').read_text(encoding='utf-8'))
        self.reader = FixtureDataAPI(self.fixture['api_responses'])
        self.extractor = FixtureExtractor(self.fixture['synthetic_extraction'])

    def test_returns_six_typed_items_without_mutating_input(self):
        before = copy.deepcopy(self.fixture)
        audit = []
        services = AgentServices(data_api=self.reader, extractor=self.extractor, input_observer=audit.append)
        out = invoke(self.fixture['request'], None, services)
        self.assertEqual(out['schema_version'], 'summary-items/v1')
        self.assertEqual(len(out['items']), 6)
        self.assertTrue(out['mock_only'])
        self.assertEqual(self.fixture, before)
        self.assertEqual(audit[0]['metadata']['coverage'], 'complete')
        self.assertTrue(audit[0]['resources'])

    def test_missing_source_raises_instead_of_returning_success(self):
        with self.assertRaises(ValueError):
            invoke(self.fixture['request'], None, AgentServices(data_api=FixtureDataAPI({}), extractor=self.extractor))

    def test_missing_extractor_is_rejected(self):
        with self.assertRaises(ValueError):
            invoke(self.fixture['request'], None, AgentServices(data_api=self.reader))

    def test_summary_request_is_not_tied_to_workflow_state(self):
        request = self.fixture['request']
        self.assertNotIn('trigger', request)
        out = invoke(request, None, AgentServices(data_api=self.reader, extractor=self.extractor))
        self.assertEqual(len(out['items']), 6)

    def test_snapshot_binding_is_checked_when_snapshot_is_supplied(self):
        request = dict(self.fixture['request'], input_snapshot_id='snapshot-a')
        with self.assertRaisesRegex(ValueError, 'Snapshot binding mismatch'):
            invoke(request, {'snapshot_id': 'snapshot-b'}, AgentServices(data_api=self.reader, extractor=self.extractor))

    def test_local_extractor_has_default_gpu_for_medgemma(self):
        with patch('chain_agents.summary.extractor.LocalModel') as local_model:
            LocalSummaryExtractor('medgemma15_4b_it', '/models/medgemma-1.5-4b-it')
        local_model.assert_called_once_with(
            'medgemma15_4b_it',
            '/models/medgemma-1.5-4b-it',
            gpu_index='1',
            max_new_tokens=8192,
        )
