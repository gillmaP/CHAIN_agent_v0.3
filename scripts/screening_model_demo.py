#!/usr/bin/env python3
"""Run the Screening Agent entrypoint with a local model and synthetic case."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chain_agents.common import canonical_hash
from chain_agents.screening.agent import invoke
from chain_agents.screening.prototype import ScreeningLLMBackend
from chain_agents.services import AgentServices


def load_case(path: Path) -> tuple[dict, dict]:
    case = json.loads(path.read_text(encoding='utf-8'))
    facts = {}
    refs = []
    saved_times = []
    for document in case['documents']:
        doc_id, version = document['document_id'], document['version']
        key = f'document:{doc_id}@{version}'
        saved_at = document['saved_time']
        saved_times.append(saved_at)
        refs.append({
            'system': 'SYNTHETIC_EMR', 'record_id': doc_id,
            'version': version, 'field': 'text',
        })
        facts[key] = {
            'value': {
                'document_id': doc_id, 'version': version,
                'document_type': document['document_type'],
                'saved_time': saved_at, 'text': document['text'],
            },
            'status': 'AVAILABLE', 'source_ref': refs[-1],
            'source_time': saved_at, 'known_at': saved_at,
        }
    known_at = max(saved_times)
    for name, value in case['structured_facts'].items():
        source_ref = {
            'system': 'SYNTHETIC_EMR', 'record_id': case['case_id'],
            'version': 1, 'field': name,
        }
        refs.append(source_ref)
        facts[name] = {
            'value': value, 'status': 'AVAILABLE', 'source_ref': source_ref,
            'source_time': known_at, 'known_at': known_at,
        }
    snapshot = {'known_at': known_at, 'facts': facts}
    snapshot['snapshot_id'] = canonical_hash(snapshot)
    request = {
        'request_id': 'SCREENING-SYNTHETIC-DEMO',
        'input_snapshot_id': snapshot['snapshot_id'],
        'scope': sorted(facts),
        'dependencies': refs,
        'evaluated_at': datetime.now(timezone.utc).isoformat(),
    }
    return request, snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=['qwen35_9b', 'gemma4_12b_it', 'medgemma15_4b_it'], default='qwen35_9b')
    parser.add_argument('--gpu', default='2')
    parser.add_argument('--model-root', type=Path)
    parser.add_argument('--case', type=Path, default=ROOT / 'examples' / 'screening_case.json')
    parser.add_argument('--max-new-tokens', type=int, default=8192)
    args = parser.parse_args()
    if args.model_root is not None:
        os.environ['CHAIN_SCREENING_MODEL_ROOT'] = str(args.model_root.resolve())
    from chain_agents.screening.local_model import LocalScreeningModel

    model = LocalScreeningModel(args.model, gpu=args.gpu, max_new_tokens=args.max_new_tokens)
    request, snapshot = load_case(args.case)
    result = invoke(request, snapshot, AgentServices(backend=ScreeningLLMBackend(model)))
    print(json.dumps({'agent': 'stroke_screening', 'result': result}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
