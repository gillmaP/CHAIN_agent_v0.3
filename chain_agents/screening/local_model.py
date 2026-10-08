"""Team 1 standalone local-GPU checkpoint loader with pinned revisions."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .prototype import MODELS

# No default path into another team's directory. The runner must configure
# a model root it owns or explicitly has permission to read.


def model_root() -> Path:
    configured = os.environ.get('CHAIN_SCREENING_MODEL_ROOT')
    if not configured or not configured.strip():
        raise ValueError('Set CHAIN_SCREENING_MODEL_ROOT or pass --model-root /path/to/models (Team 1 standalone)')
    return Path(configured).expanduser().resolve()


def model_location(model_key: str) -> Path:
    if model_key not in MODELS:
        raise ValueError(f'Unsupported Screening model: {model_key}')
    return model_root() / MODELS[model_key]['directory']


def download_model(model_key: str):
    """Explicit opt-in network download: inference itself NEVER reaches the Hub."""
    spec = MODELS[model_key]
    from huggingface_hub import snapshot_download
    location = model_location(model_key)
    location.parent.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=spec['repo_id'], revision=spec['revision'], local_dir=str(location))
    (location.parent / f'{model_key}.manifest.json').write_text(json.dumps({
        'model_key': model_key, 'model_id': spec['repo_id'], 'revision': spec['revision'],
        'model_directory': str(location), 'downloaded_at_utc': datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return location


def verify_local_model(model_key: str) -> Path:
    location = model_location(model_key)
    if not (location / 'config.json').is_file():
        raise FileNotFoundError(f'Missing local model {location}; download first or change CHAIN_SCREENING_MODEL_ROOT')
    manifest = location.parent / f'{model_key}.manifest.json'
    if not manifest.exists():
        # Do not claim that local weights match the pinned revision without a manifest.
        raise FileNotFoundError(f'Missing revision manifest {manifest}; verify/download pinned weights first')
    obj = json.loads(manifest.read_text(encoding='utf-8'))
    spec = MODELS[model_key]
    if obj.get('model_id') != spec['repo_id'] or obj.get('revision') != spec['revision']:
        raise ValueError('Local model checkpoint revision does not match the pinned Screening revision')
    return location


class LocalScreeningModel:
    def __init__(self, model_key='qwen35_9b', gpu='0', max_new_tokens=8192):
        if model_key not in MODELS:
            raise ValueError('Unsupported Screening model')
        if not str(gpu).isdigit() or int(max_new_tokens) < 1:
            raise ValueError('Invalid GPU or generation length')
        location = verify_local_model(model_key)
        # Must be set before importing torch / transformers.
        os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu)
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        import torch
        from transformers import AutoProcessor, AutoModelForMultimodalLM
        if not torch.cuda.is_available():
            raise RuntimeError('GPU inference requested but CUDA is unavailable')
        self.model_key = model_key
        self.model_revision = MODELS[model_key]['revision']
        self.max_new_tokens = int(max_new_tokens)
        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(str(location), local_files_only=True)
        self.model = AutoModelForMultimodalLM.from_pretrained(
            str(location), local_files_only=True, device_map='auto',
            dtype='auto', low_cpu_mem_usage=True,
        )
        self.model.eval()

    def generate(self, messages):
        options = {'add_generation_prompt': True, 'tokenize': True,
                   'return_dict': True, 'return_tensors': 'pt'}
        if self.model_key == 'qwen35_9b':
            options['enable_thinking'] = False
        tokens = self.processor.apply_chat_template(messages, **options).to(self.model.device)
        with self.torch.inference_mode():
            answer = self.model.generate(**tokens, max_new_tokens=self.max_new_tokens,
                                         do_sample=False, use_cache=True)
        output = answer[0, tokens['input_ids'].shape[-1]:]
        # Record whether decoding reached the requested token budget. This is
        # diagnostics only; a syntactically invalid response is still rejected.
        self.last_generation_info = {
            'generated_tokens': int(output.shape[-1]),
            'max_new_tokens': self.max_new_tokens,
            'hit_token_limit': int(output.shape[-1]) >= self.max_new_tokens,
        }
        return self.processor.decode(output, skip_special_tokens=True).strip()
