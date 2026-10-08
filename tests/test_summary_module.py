"""Direct S1 integration boundary; no HTTP service or GPU required."""
import copy
import json
from pathlib import Path
import unittest
from chain_agents.summary.agent import invoke_s1
from chain_agents.summary.data_contract import FixtureDataAPI
from examples.summary_s1 import FixtureExtractor

class SummaryModuleTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((Path(__file__).resolve().parents[1] / 'examples/summary_s1_fixture.json').read_text(encoding='utf-8'))
        self.reader = FixtureDataAPI(self.fixture['api_responses'])
        self.extractor = FixtureExtractor(self.fixture['synthetic_extraction'])

    def test_s1_returns_six_typed_items_without_mutating_input(self):
        before = copy.deepcopy(self.fixture)
        audit = []
        out = invoke_s1(self.fixture['request'], data_api=self.reader, extractor=self.extractor, input_observer=audit.append)
        self.assertEqual(out['schema_version'], 'summary-s1-fields/v1')
        self.assertEqual(len(out['items']), 6)
        self.assertTrue(out['mock_only'])
        self.assertEqual(self.fixture, before)
        self.assertEqual(audit[0]['metadata']['coverage'], 'complete')
        self.assertTrue(audit[0]['resources'])

    def test_missing_source_raises_instead_of_returning_success(self):
        with self.assertRaises(ValueError):
            invoke_s1(self.fixture['request'], data_api=FixtureDataAPI({}), extractor=self.extractor)

    def test_missing_extractor_is_rejected(self):
        with self.assertRaises(ValueError):
            invoke_s1(self.fixture['request'], data_api=self.reader)

    def test_invalid_trigger_is_rejected(self):
        for trigger in (None, 'S1', {}, {'state_enter': 'S2'}):
            with self.subTest(trigger=trigger):
                request = dict(self.fixture['request'], trigger=trigger)
                with self.assertRaises(ValueError):
                    invoke_s1(request, data_api=self.reader, extractor=self.extractor)
