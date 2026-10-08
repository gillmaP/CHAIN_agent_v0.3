"""No GPU or Hub access: inspect pinned model packaging and local-verification path."""
import json
import inspect
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chain_agents.screening.local_model import LocalScreeningModel, model_location, model_root, verify_local_model
from chain_agents.screening.prototype import MODELS


class ScreeningModelPackagingTests(unittest.TestCase):
    def test_three_models_and_pinned_checkpoints(self):
        expected = {
            'qwen35_9b': ('Qwen/Qwen3.5-9B', 'c202236235762e1c871ad0ccb60c8ee5ba337b9a'),
            'gemma4_12b_it': ('google/gemma-4-12B-it', '707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7'),
            'medgemma15_4b_it': ('google/medgemma-1.5-4b-it', '91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b'),
        }
        self.assertEqual({name: (spec['repo_id'], spec['revision']) for name, spec in MODELS.items()}, expected)

    def test_manifest_validation_for_each_model(self):
        with tempfile.TemporaryDirectory() as work:
            with patch.dict(os.environ, {'CHAIN_SCREENING_MODEL_ROOT': work}):
                for key, spec in MODELS.items():
                    location = model_location(key)
                    location.mkdir()
                    (location / 'config.json').write_text('{}', encoding='utf-8')
                    manifest = Path(work) / f'{key}.manifest.json'
                    manifest.write_text(json.dumps({'model_id': spec['repo_id'], 'revision': spec['revision']}), encoding='utf-8')
                    self.assertEqual(verify_local_model(key), location)
                    manifest.write_text(json.dumps({'model_id': spec['repo_id'], 'revision': 'WRONG'}), encoding='utf-8')
                    with self.assertRaises(ValueError):
                        verify_local_model(key)

    def test_no_implicit_team_or_server_model_root(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'CHAIN_SCREENING_MODEL_ROOT'):
                model_root()

    def test_requirements_are_shared_by_both_llm_agents(self):
        path = Path(__file__).resolve().parents[1] / 'requirements-llm.txt'
        req = path.read_text(encoding='utf-8')
        self.assertIn('transformers==5.19.0', req)
        self.assertIn('huggingface_hub==1.33.0', req)

    def test_screening_default_generation_limit_matches_model_runner(self):
        self.assertEqual(
            inspect.signature(LocalScreeningModel).parameters['max_new_tokens'].default,
            8192,
        )


if __name__ == '__main__':
    unittest.main()
