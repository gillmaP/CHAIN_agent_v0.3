"""Offline tests of rejected Qwen/Gemma/MedGemma JSON: no weights or GPU."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chain_agents.screening.prototype import ScreeningResponseError, screen_documents
from scripts import screening_experiment

CASE = json.loads((Path(__file__).resolve().parents[1] / 'examples/screening_case.json').read_text(encoding='utf-8'))


class BadLLM:
    model_key = 'qwen35_9b'
    model_revision = 'test-double'

    def generate(self, messages):
        return json.dumps({'findings': [{
            'code': 'weakness_in_arm', 'status': 'positive',
            'source_ref': 'document:DOC-2610060412@1',
            'quote': 'Motor: Rt. U/E G2, Rt. L/E G3, Lt. side G5',
        }]})


class ScreeningDiagnosticsTests(unittest.TestCase):
    def test_rejected_enums_preserve_raw_response(self):
        with self.assertRaisesRegex(ScreeningResponseError, r"code='weakness_in_arm', status='positive'") as ctx:
            screen_documents(BadLLM(), CASE['documents'])
        self.assertIn('weakness_in_arm', ctx.exception.raw_response)

    def test_result_path_is_accepted_under_results(self):
        root = screening_experiment.ROOT
        self.assertEqual(screening_experiment.output_destination(
            root/'results/qwen35_9b_result.json', 'qwen35_9b', 'run'),
            root/'results/qwen35_9b_result.json')
        self.assertEqual(screening_experiment.output_destination(
            root/'results', 'qwen35_9b', 'run'),
            root/'results/qwen35_9b_result.json')
        with self.assertRaisesRegex(ValueError, 'only under'):
            screening_experiment.output_destination(root/'unsafe.json', 'qwen35_9b', 'run')

    def test_error_creates_private_raw_report_not_validated_report(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'result.json'
            with patch.object(screening_experiment, 'LocalScreeningModel', return_value=BadLLM()):
                with self.assertRaisesRegex(ScreeningResponseError, 'weakness_in_arm'):
                    screening_experiment.main([
                        'run', '--model', 'qwen35_9b', '--output', str(target)])
            self.assertFalse(target.exists())
            invalid = Path(folder)/'result.invalid_raw.json'
            self.assertTrue(invalid.is_file())
            report = json.loads(invalid.read_text(encoding='utf-8'))
            self.assertIn('weakness_in_arm', report['validation_error'])
            self.assertIn('weakness_in_arm', report['raw_llm_response'])
            if os.name != 'nt':
                self.assertEqual(os.stat(invalid).st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
