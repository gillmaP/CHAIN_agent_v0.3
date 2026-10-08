"""Execution provenance, kept outside the clinical/domain output contract."""
import copy
import hashlib
import json
import platform
from importlib.metadata import PackageNotFoundError, version
from datetime import datetime, timezone
from pathlib import Path

from .history_s1_contract import QUESTION_CATALOG, REQUEST_ALIASES, canonical_questions


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return 'sha256:' + hashlib.sha256(raw.encode()).hexdigest()


def question_plan(questions):
    resolved = canonical_questions(questions)
    return {'requested': list(questions), 'resolved': resolved,
            'aliases': {q: list(REQUEST_ALIASES[q]) for q in questions if q in REQUEST_ALIASES},
            'automatically_included': ['antiplatelet_use'] if 'anticoagulant_use' in questions
                and 'antiplatelet_use' not in questions else [],
            'catalog_hash': digest(QUESTION_CATALOG), 'policy_version': 's1-question-plan/v1'}


def implementation_fingerprint(extractor):
    root = Path(__file__).parent
    names = ('agent.py', 'logic.py', 'history_s1_summary.py', 'history_s1_contract.py',
             'mock_contract.py', 'history_s1_extractor.py', 'experiment.py',
             'input_audit.py', 'api_service.py', 'api_adapter.py')
    packages = {}
    for name in ('torch', 'transformers', 'accelerate', 'bitsandbytes'):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {'python_version': platform.python_version(), 'packages': packages,
            'files': {name: 'sha256:' + hashlib.sha256((root/name).read_bytes()).hexdigest()
                      for name in names if (root/name).is_file()},
            'model_key': getattr(extractor, 'model_key', None),
            'method': getattr(extractor, 'method', None),
            'model_artifact_revision': getattr(extractor, 'model_revision', None),
            'model_revision_note': 'null means the weight revision was not independently recorded; model_key is not a weight hash.'}


class InputResolutionError(ValueError):
    """No clinical result is permitted when a requested resource failed."""


class InputAudit:
    def __init__(self, request, extractor):
        self.request = copy.deepcopy(request)
        self.resources = {}
        self.metadata = {'schema_version': 'summary-execution-audit/v1',
                         'question_plan': question_plan(request['questions']),
                         'implementation': implementation_fingerprint(extractor),
                         'input_policy': 'all_requested_resources_required',
                         'retrieval_started_at': now(), 'retrieval_completed_at': None,
                         'coverage': 'incomplete', 'sources': [], 'input_snapshot_hash': None,
                         'requested_references': list(request['input_references']),
                         'time_policy': 'captured_at_retrieval; no historical as_of guarantee; sequential reads are not an atomic upstream snapshot'}

    def record(self, ref, resource, started):
        self.resources[ref] = copy.deepcopy(resource)
        self.metadata['sources'].append({'source_ref': ref, 'status': 'validated',
            'retrieval_started_at': started, 'retrieved_at': now(), 'content_hash': digest(resource),
            'source_metadata': {k: copy.deepcopy(resource[k]) for k in
                ('version', 'as_of', 'source_time', 'known_at', 'saved_time', 'updated_at') if k in resource}})

    def failed(self, ref, stage):
        self.metadata['sources'].append({'source_ref': ref, 'status': 'failed', 'stage': stage})
        self.metadata['retrieval_completed_at'] = now()

    def complete(self):
        self.metadata.update(coverage='complete', retrieval_completed_at=now(),
            input_snapshot_hash=digest({'patient_id': self.request['patient_id'],
                'encounter_id': self.request['encounter_id'], 'episode_id': self.request['episode_id'],
                'questions': self.metadata['question_plan']['resolved'], 'resources': self.resources}))

    def snapshot(self):
        return {'metadata': copy.deepcopy(self.metadata), 'resources': copy.deepcopy(self.resources)}
